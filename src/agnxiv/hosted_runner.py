from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .auto import build_auto_plan
from .build import build_python_environment
from .models import Claim
from .preprint import parse_arxiv_reference
from .provenance import detect_git_identity
from .service.security import validate_git_ref, validate_github_slug
from .spec import execute_verification_spec, load_verification_spec
from .zero_manifest import run_zero_manifest

_MAX_PAPER_BYTES = 50 * 1024 * 1024
_MAX_REPOSITORY_BYTES = 2 * 1024 * 1024 * 1024
_MAX_REPOSITORY_FILES = 20_000
_HOSTED_IMAGE_RE = re.compile(
    r"^python:3\.(?:10|11|12)(?:\.\d+)?-slim(?:-bookworm)?$"
)
_PDF_PARSER_IMAGE = "agnxiv-pdf-parser:trusted"
_MAX_PDF_PARSER_OUTPUT_BYTES = 16 * 1024 * 1024


class HostedRunnerError(RuntimeError):
    """A hosted verification runner failed safely."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "redirects are not allowed for arXiv paper downloads",
            headers,
            fp,
        )


_ARXIV_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _run(command: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HostedRunnerError(f"command failed to start: {command[0]}: {exc}") from exc

    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout)[-4000:]
        raise HostedRunnerError(
            f"command exited with {completed.returncode}: {command[0]}: {output}"
        )
    return completed


def _repository_stats(root: Path) -> tuple[int, int]:
    total = 0
    files = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        files += 1
        try:
            total += path.stat().st_size
        except OSError:
            continue
        if total > _MAX_REPOSITORY_BYTES or files > _MAX_REPOSITORY_FILES:
            break
    return total, files


def checkout_repository(slug: str, ref: str, destination: Path) -> None:
    safe_slug = validate_github_slug(slug)
    safe_ref = validate_git_ref(ref)
    url = f"https://github.com/{safe_slug}.git"

    _run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            url,
            str(destination),
        ],
        timeout=180,
    )
    _run(
        [
            "git",
            "-C",
            str(destination),
            "fetch",
            "--depth",
            "1",
            "origin",
            safe_ref,
        ],
        timeout=180,
    )
    _run(
        [
            "git",
            "-c",
            "filter.lfs.smudge=",
            "-c",
            "filter.lfs.process=",
            "-c",
            "filter.lfs.required=false",
            "-c",
            "submodule.recurse=false",
            "-C",
            str(destination),
            "checkout",
            "--detach",
            "FETCH_HEAD",
        ],
        timeout=60,
    )

    size, files = _repository_stats(destination)
    if size > _MAX_REPOSITORY_BYTES:
        raise HostedRunnerError(
            f"repository exceeds hosted size limit of {_MAX_REPOSITORY_BYTES} bytes"
        )
    if files > _MAX_REPOSITORY_FILES:
        raise HostedRunnerError(
            f"repository exceeds hosted file limit of {_MAX_REPOSITORY_FILES}"
        )


def download_arxiv_pdf(arxiv_id: str, destination: Path) -> None:
    reference = parse_arxiv_reference(arxiv_id)
    request = urllib.request.Request(
        reference.pdf_url,
        headers={"User-Agent": "AgnXiv-Hosted-Runner/1.0"},
    )

    try:
        with _ARXIV_OPENER.open(  # nosec B310 - fixed HTTPS arXiv origin, no redirects
            request,
            timeout=45,
        ) as response:
            content_type = response.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                raise HostedRunnerError(
                    f"arXiv returned unexpected content type: {content_type}"
                )

            with destination.open("wb") as handle:
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_PAPER_BYTES:
                        raise HostedRunnerError("arXiv PDF exceeds hosted size limit")
                    handle.write(chunk)
    except urllib.error.URLError as exc:
        raise HostedRunnerError(f"could not download arXiv PDF: {exc}") from exc



def _limit_pdf_parser_process() -> None:
    """Apply OS limits before the isolated PDF parser imports untrusted input."""
    import resource

    one_gib = 1024 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (one_gib, one_gib))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def _load_pdf_claim_payload(output: Path) -> list[Claim]:
    try:
        if output.stat().st_size > _MAX_PDF_PARSER_OUTPUT_BYTES:
            raise ValueError("parser output exceeds hosted size limit")
        payload = json.loads(output.read_text(encoding="utf-8"))
        raw_claims = payload.get("claims")
        if payload.get("ok") is not True or not isinstance(raw_claims, list):
            raise ValueError("parser output schema is invalid")
        if len(raw_claims) > 2_000:
            raise ValueError("parser returned too many claims")
        return [Claim.model_validate(item) for item in raw_claims]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HostedRunnerError(
            "isolated PDF parser returned invalid claim data"
        ) from exc


def _extract_pdf_claims_host_fallback(
    paper: Path,
    workspace: Path,
) -> list[Claim]:
    """Local/test fallback. Hosted production execution uses the Docker path."""
    if os.name != "posix":
        raise HostedRunnerError(
            "hosted PDF parsing requires POSIX resource-limit isolation"
        )
    output = workspace / "paper-claims.json"
    command = [
        sys.executable,
        "-s",
        "-m",
        "agnxiv.pdf_extract_worker",
        "--input",
        str(paper),
        "--output",
        str(output),
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=False,
            preexec_fn=_limit_pdf_parser_process,
            env={
                **os.environ,
                "PYTHONNOUSERSITE": "1",
                "PYTHONWARNINGS": "ignore",
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HostedRunnerError(
            f"isolated PDF claim extraction failed: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0 or not output.is_file():
        reason = "parser process failed"
        if output.is_file():
            try:
                payload = json.loads(output.read_text(encoding="utf-8"))
                reason = str(payload.get("error") or reason)[:1200]
            except (OSError, json.JSONDecodeError):
                pass
        raise HostedRunnerError(f"could not safely parse arXiv PDF: {reason}")
    return _load_pdf_claim_payload(output)


def extract_pdf_claims_isolated(
    paper: Path,
    workspace: Path,
    *,
    parser_image: str | None = None,
) -> list[Claim]:
    """Parse a PDF in a no-network unprivileged container for hosted runs."""
    if parser_image is None:
        return _extract_pdf_claims_host_fallback(paper, workspace)

    paper = paper.resolve()
    if not paper.is_file() or paper.is_symlink():
        raise HostedRunnerError("PDF input must be a regular non-symlink file")

    output_dir = workspace / "pdf-parser-output"
    output_dir.mkdir(mode=0o777)
    output_dir.chmod(0o777)
    output = output_dir / "claims.json"

    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--ipc",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "64",
        "--memory",
        "1024m",
        "--cpus",
        "1",
        "--user",
        "65534:65534",
        "--ulimit",
        "nofile=128:128",
        "--ulimit",
        "core=0:0",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--mount",
        f"type=bind,src={paper},dst=/input/paper.pdf,readonly",
        "--mount",
        f"type=bind,src={output_dir.resolve()},dst=/output",
        parser_image,
        "--input",
        "/input/paper.pdf",
        "--output",
        "/output/claims.json",
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HostedRunnerError(
            f"containerized PDF extraction failed: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0 or not output.is_file():
        raise HostedRunnerError("could not safely parse arXiv PDF in parser container")
    return _load_pdf_claim_payload(output)


def _validate_hosted_image(image: str) -> str:
    candidate = image.strip()
    if not _HOSTED_IMAGE_RE.fullmatch(candidate):
        raise HostedRunnerError(
            "hosted beta allows only approved official Python slim runtimes"
        )
    return candidate


def _pull_image(image: str) -> None:
    _run(["docker", "pull", image], timeout=600)


def execute_job(
    *,
    mode: str,
    repository: str,
    repository_ref: str,
    arxiv_id: str | None,
    spec_path: str | None,
) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory(prefix="agnxiv-hosted-") as temp:
        workspace = Path(temp)
        repo = workspace / "repository"
        checkout_repository(repository, repository_ref, repo)

        if mode in {"auto_plan", "auto_verify"}:
            if not arxiv_id:
                raise HostedRunnerError("AUTO mode requires an arXiv identifier")
            paper = workspace / "paper.pdf"
            download_arxiv_pdf(arxiv_id, paper)
            paper_claims = extract_pdf_claims_isolated(
                paper,
                workspace,
                parser_image=_PDF_PARSER_IMAGE,
            )
            identity = detect_git_identity(repo)
            if identity is None:
                raise HostedRunnerError("checked-out repository has no Git identity")

            if mode == "auto_plan":
                plan = build_auto_plan(
                    paper,
                    repo,
                    claims_override=paper_claims,
                )
                return "needs_review", {
                    "kind": "auto_plan",
                    "repository_commit": identity.commit,
                    "plan": plan.model_dump(mode="json"),
                }

            plan = build_auto_plan(
                paper,
                repo,
                claims_override=paper_claims,
            )
            # Do not create a network-capable or source-installing runtime.
            # Running the first execution requires safe plan prerequisites.
            required = {
                "paper_ingest", "claim_compilation", "repository_mapping",
                "environment_inference", "command_discovery",
                "workflow_ordering", "artifact_resolution",
            }
            completed = {stage.name for stage in plan.stages if stage.complete}
            if plan.blockers or not required.issubset(completed):
                return "needs_review", {
                    "kind": "auto_plan",
                    "repository_commit": identity.commit,
                    "plan": plan.model_dump(mode="json"),
                    "reason": "The plan did not pass execution prerequisites.",
                }

            base_image = _validate_hosted_image(plan.environment.base_image)
            _pull_image(base_image)
            build = build_python_environment(repo, base_image=base_image)
            outcome = run_zero_manifest(
                paper,
                repo,
                image=build.image_ref,
                claims_override=paper_claims,
                plan_override=plan,
            )

            if outcome.bundle is None:
                return "needs_review", {
                    "kind": "auto_plan",
                    "repository_commit": identity.commit,
                    "plan": outcome.plan.model_dump(mode="json"),
                    "reason": outcome.reason,
                }
            verdicts = [item.record.verdict.value for item in outcome.bundles]
            status = (
                "succeeded"
                if any(item in {"VERIFIED", "CONTRADICTED"} for item in verdicts)
                else "needs_review"
            )
            return status, {
                "kind": "verification",
                "zero_manifest": True,
                "build": build.model_dump(mode="json"),
                "discovery": outcome.frozen_locator.model_dump(mode="json"),
                "bundle": outcome.bundle.model_dump(mode="json"),
                "additional_verifications": [
                    {
                        "discovery": locator.model_dump(mode="json"),
                        "bundle": item.model_dump(mode="json"),
                    }
                    for locator, item in zip(
                        outcome.frozen_locators[1:], outcome.bundles[1:]
                    )
                ],
            }

        if mode == "verify_spec":
            if not spec_path:
                raise HostedRunnerError("VERIFY_SPEC requires spec_path")
            relative = Path(spec_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise HostedRunnerError("unsafe verification spec path")
            manifest_candidate = repo / relative
            if manifest_candidate.is_symlink():
                raise HostedRunnerError("verification spec symlinks are not allowed")
            manifest = manifest_candidate.resolve()
            try:
                manifest.relative_to(repo.resolve())
            except ValueError as exc:
                raise HostedRunnerError("verification spec escapes repository") from exc
            if not manifest.is_file() or manifest.is_symlink():
                raise HostedRunnerError("verification spec is not a regular file")

            spec = load_verification_spec(manifest)
            base_image = _validate_hosted_image(spec.runtime.image)
            spec_base = manifest.parent.resolve()
            candidate_repo = Path(spec.repository)
            if candidate_repo.is_absolute():
                raise HostedRunnerError(
                    "verification spec repository must be workspace-relative"
                )
            build_candidate = spec_base / candidate_repo
            if build_candidate.is_symlink():
                raise HostedRunnerError(
                    "verification spec repository symlinks are not allowed"
                )
            build_repository = build_candidate.resolve()
            try:
                build_repository.relative_to(spec_base)
            except ValueError as exc:
                raise HostedRunnerError(
                    "verification spec repository escapes its workspace"
                ) from exc
            if not build_repository.is_dir() or build_repository.is_symlink():
                raise HostedRunnerError(
                    "verification spec repository is not a regular directory"
                )

            _pull_image(base_image)
            build = build_python_environment(
                build_repository,
                base_image=base_image,
            )
            bundle = execute_verification_spec(
                manifest,
                image_override=build.image_ref,
            )
            verdict = bundle.record.verdict.value
            status = "succeeded" if verdict in {"VERIFIED", "CONTRADICTED"} else "needs_review"
            return status, {
                "kind": "verification",
                "build": build.model_dump(mode="json"),
                "bundle": bundle.model_dump(mode="json"),
            }

        raise HostedRunnerError(f"unsupported hosted job mode: {mode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-ref", required=True)
    parser.add_argument("--arxiv-id", default="")
    parser.add_argument("--spec-path", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    status = "failed"
    result: dict | None = None
    error: str | None = None

    try:
        status, result = execute_job(
            mode=args.mode,
            repository=args.repository,
            repository_ref=args.repository_ref,
            arxiv_id=args.arxiv_id or None,
            spec_path=args.spec_path or None,
        )
    except HostedRunnerError as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - top-level worker crash boundary
        error = f"unexpected runner failure: {type(exc).__name__}: {exc}"

    output = Path(args.output)
    output.write_text(
        json.dumps(
            {
                "status": status,
                "result": result,
                "error": error,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .auto import build_auto_plan
from .build import build_python_environment
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


class HostedRunnerError(RuntimeError):
    """A hosted verification runner failed safely."""


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
        with urllib.request.urlopen(request, timeout=45) as response:
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
            identity = detect_git_identity(repo)
            if identity is None:
                raise HostedRunnerError("checked-out repository has no Git identity")

            if mode == "auto_plan":
                plan = build_auto_plan(paper, repo)
                return "needs_review", {
                    "kind": "auto_plan",
                    "repository_commit": identity.commit,
                    "plan": plan.model_dump(mode="json"),
                }

            plan = build_auto_plan(paper, repo)
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
            outcome = run_zero_manifest(paper, repo, image=build.image_ref)

            if outcome.bundle is None:
                return "needs_review", {
                    "kind": "auto_plan",
                    "repository_commit": identity.commit,
                    "plan": outcome.plan.model_dump(mode="json"),
                    "reason": outcome.reason,
                }
            verdict = outcome.bundle.record.verdict.value
            status = (
                "succeeded" if verdict in {"VERIFIED", "CONTRADICTED"}
                else "needs_review"
            )
            return status, {
                "kind": "verification",
                "zero_manifest": True,
                "build": build.model_dump(mode="json"),
                "discovery": outcome.frozen_locator.model_dump(mode="json"),
                "bundle": outcome.bundle.model_dump(mode="json"),
            }

        if mode == "verify_spec":
            if not spec_path:
                raise HostedRunnerError("VERIFY_SPEC requires spec_path")
            relative = Path(spec_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise HostedRunnerError("unsafe verification spec path")
            manifest = (repo / relative).resolve()
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
            build_repository = (spec_base / candidate_repo).resolve()
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

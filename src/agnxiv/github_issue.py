from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hosted_runner import HostedRunnerError, execute_job
from .preprint import parse_arxiv_reference
from .service.security import validate_git_ref, validate_github_slug


_SECTION_RE = re.compile(
    r"^###\s+(.+?)\s*$\n+(.*?)(?=^###\s+|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class GitHubVerificationRequest:
    mode: str
    repository: str
    repository_ref: str
    arxiv_id: str | None
    spec_path: str | None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned in {"", "_No response_", "No response"}:
        return None
    return cleaned


def parse_issue_body(body: str) -> GitHubVerificationRequest:
    sections = {
        heading.strip().lower(): _clean(value)
        for heading, value in _SECTION_RE.findall(body or "")
    }

    mode_text = sections.get("mode") or ""
    if mode_text.lower().startswith("auto"):
        mode = "auto_plan"
    elif mode_text.lower().startswith("verify"):
        mode = "verify_spec"
    else:
        raise ValueError("Mode must be Auto-plan or Verify manifest.")

    repository_text = sections.get("public github repository")
    if not repository_text:
        raise ValueError("Public GitHub repository is required.")
    repository = validate_github_slug(repository_text)

    repository_ref = validate_git_ref(sections.get("git ref") or "main")

    arxiv_id = sections.get("arxiv id")
    if mode == "auto_plan":
        if not arxiv_id:
            raise ValueError("Auto-plan requires an arXiv ID.")
        arxiv_id = parse_arxiv_reference(arxiv_id).versioned_id

    spec_path = sections.get("verification manifest path")
    if mode == "verify_spec":
        if not spec_path:
            raise ValueError("Verify manifest requires a manifest path.")
        path = Path(spec_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Verification manifest path must stay inside the repository.")

    return GitHubVerificationRequest(
        mode=mode,
        repository=repository,
        repository_ref=repository_ref,
        arxiv_id=arxiv_id,
        spec_path=spec_path,
    )


def read_issue_event(path: str | Path) -> GitHubVerificationRequest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        raise TypeError("GitHub event does not contain an issue.")
    body = issue.get("body")
    if not isinstance(body, str):
        raise TypeError("Verification issue has no body.")
    return parse_issue_body(body)


def _summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "failed")
    result = payload.get("result")
    error = payload.get("error")
    request = payload.get("request") or {}

    lines = [
        "## AgnXiv result",
        "",
        f"**Status:** `{status}`",
        f"**Repository:** `{request.get('repository', 'unknown')}`",
        f"**Git ref:** `{request.get('repository_ref', 'unknown')}`",
    ]

    if error:
        lines.extend(["", f"**Error:** {error}"])
        return "\n".join(lines) + "\n"

    if not isinstance(result, dict):
        lines.extend(["", "No verification result was produced."])
        return "\n".join(lines) + "\n"

    if result.get("kind") == "auto_plan":
        plan = result.get("plan") or {}
        score = float(plan.get("automation_score") or 0.0) * 100.0
        stages = plan.get("stages") or []
        complete = sum(1 for stage in stages if stage.get("complete"))
        commit = result.get("repository_commit")
        lines.extend(
            [
                f"**Pinned commit:** `{commit or 'unknown'}`",
                f"**Automation:** {score:.1f}% ({complete}/{len(stages)} stages)",
                "",
            ]
        )
        blockers = plan.get("blockers") or []
        if blockers:
            lines.append("### Why AgnXiv stopped")
            lines.extend(f"- {item}" for item in blockers)
            lines.append("")
        if plan.get("safe_to_execute"):
            lines.append("The generated plan passed the automatic safety gate.")
        else:
            lines.append(
                "AgnXiv abstained from automatic certification where evidence "
                "or execution semantics remained ambiguous."
            )
        return "\n".join(lines) + "\n"

    if result.get("kind") == "verification":
        bundle = result.get("bundle") or {}
        record = bundle.get("record") or {}
        claim = bundle.get("claim") or {}
        git = (bundle.get("provenance") or {}).get("git") or {}
        lines.extend(
            [
                f"**Pinned commit:** `{git.get('commit', 'unknown')}`",
                f"**Verdict:** **{record.get('verdict', 'UNKNOWN')}**",
                f"**Claim:** {claim.get('text', 'Unknown claim')}",
                f"**Expected:** {record.get('expected')}",
                f"**Observed:** {record.get('observed_mean')}",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(["", "Unknown worker result kind."])
    return "\n".join(lines) + "\n"


def run_issue(event_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any]
    try:
        request = read_issue_event(event_path)
        status, result = execute_job(
            mode=request.mode,
            repository=request.repository,
            repository_ref=request.repository_ref,
            arxiv_id=request.arxiv_id,
            spec_path=request.spec_path,
        )
        payload = {
            "request": {
                "mode": request.mode,
                "repository": request.repository,
                "repository_ref": request.repository_ref,
                "arxiv_id": request.arxiv_id,
                "spec_path": request.spec_path,
            },
            "status": status,
            "result": result,
            "error": None,
        }
    except (ValueError, HostedRunnerError) as exc:
        payload = {
            "request": {},
            "status": "failed",
            "result": None,
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - workflow crash boundary
        payload = {
            "request": {},
            "status": "failed",
            "result": None,
            "error": f"unexpected workflow failure: {type(exc).__name__}: {exc}",
        }

    (output / "result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output / "summary.md").write_text(_summary(payload), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run_issue(args.event, args.output_dir)


if __name__ == "__main__":
    main()

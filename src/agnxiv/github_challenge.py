from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pydantic import BaseModel

from .network import ChallengeStatus, ScientificChallenge
from .service.security import validate_git_ref, validate_github_slug

_SECTION_RE = re.compile(
    r"^###\s+(.+?)\s*$\n+(.*?)(?=^###\s+|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)
_TARGET_RE = re.compile(r"^AX-GH-(\d+)$")


class GitHubChallengeRequest(BaseModel):
    target_attempt: str
    paper_id: str | None
    claim_text: str | None
    target_reported_result: str | None
    challenger_repository: str
    challenger_ref: str
    challenger_observed_result: str
    evidence_url: str | None
    rationale: str


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned in {"", "_No response_", "No response", "_See target attempt_"}:
        return None
    return cleaned


def parse_challenge_body(body: str) -> GitHubChallengeRequest:
    sections = {
        heading.strip().lower(): _clean(value)
        for heading, value in _SECTION_RE.findall(body or "")
    }

    target = sections.get("target agnxiv attempt")
    if not target or not _TARGET_RE.fullmatch(target):
        raise ValueError("Target AgnXiv attempt must look like AX-GH-26.")

    repository_text = sections.get("challenger evidence repository")
    if not repository_text:
        raise ValueError("Challenger evidence repository is required.")
    repository = validate_github_slug(repository_text)

    ref_text = sections.get("challenger git ref")
    if not ref_text:
        raise ValueError("Challenger Git ref is required.")
    repository_ref = validate_git_ref(ref_text)

    observed = sections.get("challenger observed result")
    if not observed:
        raise ValueError("Challenger observed result is required.")

    rationale = sections.get("what diverged?")
    if not rationale:
        raise ValueError("Challenge rationale is required.")

    return GitHubChallengeRequest(
        target_attempt=target,
        paper_id=sections.get("paper"),
        claim_text=sections.get("target claim"),
        target_reported_result=sections.get("target reported result"),
        challenger_repository=repository,
        challenger_ref=repository_ref,
        challenger_observed_result=observed,
        evidence_url=sections.get("evidence url"),
        rationale=rationale,
    )


def read_challenge_event(path: str | Path) -> tuple[int, GitHubChallengeRequest]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        raise TypeError("GitHub event does not contain an issue.")

    issue_number = issue.get("number")
    if not isinstance(issue_number, int):
        raise TypeError("Challenge issue has no numeric issue number.")

    body = issue.get("body")
    if not isinstance(body, str):
        raise TypeError("Challenge issue has no body.")
    return issue_number, parse_challenge_body(body)


def challenge_from_request(
    request: GitHubChallengeRequest,
    *,
    challenge_id: str,
) -> ScientificChallenge:
    return ScientificChallenge(
        challenge_id=challenge_id,
        paper_id=request.paper_id,
        claim_text=request.claim_text,
        attempt_id=request.target_attempt,
        target_reported_result=request.target_reported_result,
        challenger_repository=request.challenger_repository,
        challenger_ref=request.challenger_ref,
        challenger_observed_result=request.challenger_observed_result,
        status=ChallengeStatus.OPEN,
        rationale=request.rationale,
        challenger_evidence_url=request.evidence_url,
    )


def _summary(challenge: ScientificChallenge) -> str:
    lines = [
        "## AgnXiv challenge record",
        "",
        f"**Challenge ID:** {challenge.challenge_id}",
        f"**Status:** {challenge.status.value}",
        f"**Target attempt:** {challenge.attempt_id}",
    ]
    if challenge.paper_id:
        lines.append(f"**Paper:** arXiv:{challenge.paper_id}")
    if challenge.claim_text:
        lines.append(f"**Target claim:** {challenge.claim_text}")
    if challenge.target_reported_result:
        lines.append(f"**Target reported result:** {challenge.target_reported_result}")
    lines.extend(
        [
            f"**Evidence repository:** {challenge.challenger_repository}",
            f"**Evidence Git ref:** {challenge.challenger_ref}",
            f"**Observed result:** {challenge.challenger_observed_result}",
            "",
            "### What diverged",
            challenge.rationale,
            "",
            (
                "This record documents an evidence-specific divergence. It does not "
                "allege misconduct and does not by itself establish universal falsity."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def run_challenge(event_path: str | Path, output_dir: str | Path) -> ScientificChallenge:
    issue_number, request = read_challenge_event(event_path)
    challenge = challenge_from_request(
        request,
        challenge_id=f"AX-CH-{issue_number}",
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "challenge.json").write_text(
        json.dumps(challenge.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output / "summary.md").write_text(_summary(challenge), encoding="utf-8")
    return challenge


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run_challenge(args.event, args.output_dir)


if __name__ == "__main__":
    main()

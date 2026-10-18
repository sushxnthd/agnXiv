from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from agnxiv.auto import build_auto_plan
from agnxiv.research import load_research_cases


_PDF_META_RE = re.compile(
    r'<meta[^>]+name=["\\\']citation_pdf_url["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
    flags=re.IGNORECASE,
)
_PDF_META_RE_REVERSED = re.compile(
    r'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+name=["\\\']citation_pdf_url["\\\']',
    flags=re.IGNORECASE,
)


def _fetch_bytes(url: str) -> tuple[bytes, str]:
    http_request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AgnXiv-Research/0.1 (+https://github.com/sushxnthd/agnXiv)",
            "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.5",
        },
    )
    with urllib.request.urlopen(http_request, timeout=90) as response:
        data = response.read(60 * 1024 * 1024 + 1)
        final_url = response.geturl()
    if len(data) > 60 * 1024 * 1024:
        raise ValueError("paper download exceeds 60 MiB research limit")
    return data, final_url


class _ArticleTextParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)

    def text(self) -> str:
        return "\n".join(self.parts)


def _materialize_manuscript(
    url: str,
    root: Path,
) -> tuple[Path, str, str, str]:
    data, final_url = _fetch_bytes(url)
    if data.startswith(b"%PDF"):
        destination = root / "paper.pdf"
        destination.write_bytes(data)
        return destination, final_url, "pdf", hashlib.sha256(data).hexdigest()

    html = data[:5_000_000].decode("utf-8", errors="ignore")
    match = _PDF_META_RE.search(html) or _PDF_META_RE_REVERSED.search(html)
    if match:
        pdf_url = urllib.parse.urljoin(final_url, match.group(1))
        pdf_data, resolved_pdf_url = _fetch_bytes(pdf_url)
        if pdf_data.startswith(b"%PDF"):
            destination = root / "paper.pdf"
            destination.write_bytes(pdf_data)
            return (
                destination,
                resolved_pdf_url,
                "pdf",
                hashlib.sha256(pdf_data).hexdigest(),
            )

    parser = _ArticleTextParser()
    parser.feed(html)
    article_text = parser.text()
    lower = article_text.lower()
    blocked_markers = (
        "checking your browser",
        "access denied",
        "enable javascript and cookies",
        "captcha",
    )
    if len(article_text) >= 4000 and not any(
        marker in lower[:5000] for marker in blocked_markers
    ):
        destination = root / "paper.txt"
        destination.write_text(article_text, encoding="utf-8")
        digest = hashlib.sha256(article_text.encode("utf-8")).hexdigest()
        return destination, final_url, "html_text", digest

    raise ValueError(
        "paper URL resolved to neither PDF nor usable article HTML"
    )


def _clone_pinned(repository: str, commit: str, destination: Path) -> None:
    subprocess.run(["git", "init", str(destination)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(destination),
            "remote",
            "add",
            "origin",
            f"https://github.com/{repository}.git",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(destination),
            "fetch",
            "--depth=1",
            "origin",
            commit,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "--detach", "FETCH_HEAD"],
        check=True,
        capture_output=True,
    )


def run_case(manifest: Path, case_id: str, output_dir: Path) -> dict:
    cases = {case.case_id: case for case in load_research_cases(manifest)}
    case = cases.get(case_id)
    if case is None:
        raise ValueError(f"research case not found: {case_id}")
    if not case.repository or not case.commit:
        raise ValueError("diagnostic case requires repository and pinned commit")
    if not case.paper_url_versioned:
        raise ValueError("diagnostic case requires a versioned paper URL")

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="agnxiv-research-") as temp:
        root = Path(temp)
        repository = root / "repository"

        manuscript = None
        materialization_errors: list[str] = []
        candidate_urls = [case.paper_url_versioned, *case.paper_alternate_urls]
        for candidate_url in candidate_urls:
            try:
                (
                    manuscript,
                    resolved_paper_url,
                    manuscript_kind,
                    manuscript_sha256,
                ) = _materialize_manuscript(candidate_url, root)
                break
            except (OSError, ValueError) as exc:
                materialization_errors.append(f"{candidate_url}: {exc}")

        if manuscript is None:
            raise ValueError(
                "all manuscript sources failed: " + " | ".join(materialization_errors)
            )
        _clone_pinned(case.repository, case.commit, repository)

        plan = build_auto_plan(manuscript, repository)

    stage_map = {stage.name: stage.complete for stage in plan.stages}
    summary = {
        "schema_version": "agnxiv.research-diagnostic/1",
        "case_id": case.case_id,
        "source_suite": case.source_suite,
        "evaluation_role": case.evaluation_role,
        "repository": case.repository,
        "commit": case.commit,
        "resolved_paper_url": resolved_paper_url,
        "manuscript_source_candidates": candidate_urls,
        "manuscript_kind": manuscript_kind,
        "manuscript_sha256": manuscript_sha256,
        "automation_score": plan.automation_score,
        "safe_to_execute": plan.safe_to_execute,
        "candidate_claims": len(plan.claims),
        "candidate_commands": len(plan.commands),
        "top_claim": plan.claims[0].claim.text if plan.claims else None,
        "top_claim_score": plan.claims[0].score if plan.claims else None,
        "stages": stage_map,
        "blockers": plan.blockers,
        "warnings": plan.warnings,
    }

    (output_dir / "case.json").write_text(
        json.dumps(case.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "plan.json").write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="research/benchmarks/scicoqa-pilot-v0.jsonl")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    summary = run_case(
        Path(args.manifest),
        args.case_id,
        Path(args.output_dir),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

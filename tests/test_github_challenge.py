import json

from agnxiv.github_challenge import parse_challenge_body, run_challenge
from agnxiv.network import ChallengeStatus


def _body() -> str:
    return """### Target AgnXiv attempt

AX-GH-26

### Paper

1403.6652

### Target claim

Macro-F1 improves by 1%.

### Target reported result

77.0%

### Challenger evidence repository

owner/reproduction

### Challenger Git ref

abc123

### Challenger observed result

73.4 ± 0.3%

### Evidence URL

https://example.com/run

### What diverged?

Same dataset and evaluation protocol; observed result remained lower.

### Acknowledgement

- [x] Evidence-specific divergence only.
"""


def test_parse_challenge_body() -> None:
    request = parse_challenge_body(_body())

    assert request.target_attempt == "AX-GH-26"
    assert request.paper_id == "1403.6652"
    assert request.challenger_repository == "owner/reproduction"
    assert request.challenger_ref == "abc123"
    assert request.challenger_observed_result == "73.4 ± 0.3%"


def test_run_challenge_writes_machine_readable_record(tmp_path) -> None:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"issue": {"number": 41, "body": _body()}}),
        encoding="utf-8",
    )

    challenge = run_challenge(event, tmp_path / "out")

    assert challenge.challenge_id == "AX-CH-41"
    assert challenge.status == ChallengeStatus.OPEN
    saved = json.loads((tmp_path / "out" / "challenge.json").read_text())
    assert saved["schema_version"] == "agnxiv.challenge/1"
    assert saved["attempt_id"] == "AX-GH-26"


def test_rejects_unstructured_target() -> None:
    try:
        parse_challenge_body(_body().replace("AX-GH-26", "paper 26"))
    except ValueError as exc:
        assert "AX-GH" in str(exc)
    else:
        raise AssertionError("unstructured target was accepted")

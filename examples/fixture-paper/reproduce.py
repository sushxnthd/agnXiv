import json
from pathlib import Path


def main() -> None:
    artifact = Path("/agnxiv-artifacts/000-metric.json")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    print(json.dumps({"metrics": {"accuracy": payload["accuracy"]}}))


if __name__ == "__main__":
    main()

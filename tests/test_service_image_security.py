from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_service_image_keeps_digest_pin_and_repairs_observed_openssl_cve() -> None:
    dockerfile = (ROOT / "Dockerfile.service").read_text(encoding="utf-8")

    assert dockerfile.startswith("FROM python:")
    assert "@sha256:" in dockerfile.splitlines()[0]
    assert "--only-upgrade openssl libssl3" in dockerfile
    assert dockerfile.count("3.0.22-1~deb12u2") == 2
    assert 'dpkg-query -W -f=\'${Version}\' openssl' in dockerfile
    assert 'dpkg-query -W -f=\'${Version}\' libssl3' in dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in dockerfile


def test_service_image_scan_policy_is_not_weakened() -> None:
    workflow = (ROOT / ".github/workflows/service-image.yml").read_text(
        encoding="utf-8"
    )

    assert 'exit-code: "1"' in workflow
    assert 'ignore-unfixed: true' in workflow
    assert 'vuln-type: "os,library"' in workflow
    assert 'severity: "CRITICAL,HIGH"' in workflow
    assert "Record security package versions" in workflow

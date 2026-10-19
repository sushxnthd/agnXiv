from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from agnxiv.service.app import create_app
from agnxiv.service.config import ServiceConfig
from agnxiv.statement import generate_ed25519_keypair


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _config(
    database_url: str,
    *,
    active_private: bytes,
    retired_public: tuple[bytes, ...] = (),
    revoked_public: tuple[bytes, ...] = (),
) -> ServiceConfig:
    return ServiceConfig(
        database_url=database_url,
        api_keys=("k" * 48,),
        public_base_url="https://agnxiv.example",
        github_token="github-token",
        github_repository="sushxnthd/agnXiv",
        github_ref="main",
        github_workflow="hosted-verify.yml",
        max_active_jobs_per_key=3,
        max_jobs_per_hour=20,
        oidc_audience="https://agnxiv.example/github-actions",
        issuer_private_key_b64=_b64(active_private),
        issuer_previous_public_keys_b64=tuple(
            _b64(key) for key in retired_public
        ),
        issuer_revoked_public_keys_b64=tuple(
            _b64(key) for key in revoked_public
        ),
    )


def test_issuer_keyring_publishes_active_retired_and_revoked_keys(tmp_path) -> None:
    active_private, active_public, active_id = generate_ed25519_keypair()
    _, retired_public, retired_id = generate_ed25519_keypair()
    _, revoked_public, revoked_id = generate_ed25519_keypair()
    app = create_app(
        _config(
            f"sqlite:///{tmp_path / 'keyring.db'}",
            active_private=active_private,
            retired_public=(retired_public,),
            revoked_public=(revoked_public,),
        )
    )

    with TestClient(app) as client:
        response = client.get("/v1/issuer")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "agnxiv.issuer/2"
    assert body["key_id"] == active_id
    assert body["public_key_pem"].encode("ascii") == active_public

    keys = {entry["key_id"]: entry for entry in body["keys"]}
    assert set(keys) == {active_id, retired_id, revoked_id}
    assert keys[active_id]["status"] == "active"
    assert keys[active_id]["signs_new_records"] is True
    assert keys[active_id]["trusted_for_historical_records"] is True
    assert keys[retired_id]["status"] == "retired"
    assert keys[retired_id]["signs_new_records"] is False
    assert keys[retired_id]["trusted_for_historical_records"] is True
    assert keys[revoked_id]["status"] == "revoked"
    assert keys[revoked_id]["signs_new_records"] is False
    assert keys[revoked_id]["trusted_for_historical_records"] is False


def test_duplicate_active_and_retired_key_fails_readiness(tmp_path) -> None:
    active_private, active_public, _ = generate_ed25519_keypair()
    app = create_app(
        _config(
            f"sqlite:///{tmp_path / 'duplicate.db'}",
            active_private=active_private,
            retired_public=(active_public,),
        )
    )

    with TestClient(app) as client:
        readiness = client.get("/readyz")
        issuer = client.get("/v1/issuer")

    assert readiness.status_code == 503
    assert "issuer_key_invalid" in readiness.json()["detail"]["issues"]
    assert issuer.status_code == 503


def test_duplicate_retired_and_revoked_key_fails_readiness(tmp_path) -> None:
    active_private, _, _ = generate_ed25519_keypair()
    _, historical_public, _ = generate_ed25519_keypair()
    app = create_app(
        _config(
            f"sqlite:///{tmp_path / 'duplicate-status.db'}",
            active_private=active_private,
            retired_public=(historical_public,),
            revoked_public=(historical_public,),
        )
    )

    with TestClient(app) as client:
        readiness = client.get("/readyz")

    assert readiness.status_code == 503
    assert "issuer_key_invalid" in readiness.json()["detail"]["issues"]


def test_malformed_historical_key_fails_closed_without_leaking_value(tmp_path) -> None:
    active_private, _, _ = generate_ed25519_keypair()
    malformed = _b64(b"not-an-ed25519-public-key")
    config = _config(
        f"sqlite:///{tmp_path / 'malformed.db'}",
        active_private=active_private,
    )
    config = ServiceConfig(
        **{
            **config.__dict__,
            "issuer_previous_public_keys_b64": (malformed,),
        }
    )
    app = create_app(config)

    with TestClient(app) as client:
        readiness = client.get("/readyz")
        issuer = client.get("/v1/issuer")

    assert readiness.status_code == 503
    assert "issuer_key_invalid" in readiness.json()["detail"]["issues"]
    assert malformed not in readiness.text
    assert issuer.status_code == 503
    assert malformed not in issuer.text

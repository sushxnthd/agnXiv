from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from agnxiv.service.app import create_app
from agnxiv.service.config import ServiceConfig
from agnxiv.service.db import JobStore
from agnxiv.transparency import GENESIS_HASH, digest_json


def _config(database_url: str) -> ServiceConfig:
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
        issuer_private_key_b64=None,
    )


def _create_job(store: JobStore, *, suffix: str, api_hash: str = "private-api-hash"):
    return store.create_job(
        job_id=f"00000000-0000-0000-0000-{suffix:0>12}",
        api_key_hash=api_hash,
        mode="auto_verify",
        repository="owner/research",
        repository_ref="a" * 40,
        arxiv_id="2601.00001",
        spec_path=None,
    )


def test_verification_results_form_hash_chain(tmp_path) -> None:
    store = JobStore(f"sqlite:///{tmp_path / 'ledger.db'}")
    store.initialize()
    first_job = _create_job(store, suffix="1")
    second_job = _create_job(store, suffix="2")
    first_result = {
        "kind": "verification",
        "zero_manifest": True,
        "bundle": {"record": {"verdict": "VERIFIED"}},
    }
    second_result = {
        "kind": "verification",
        "zero_manifest": True,
        "bundle": {"record": {"verdict": "CONTRADICTED"}},
    }

    store.complete(
        first_job.id,
        status="succeeded",
        result=first_result,
        error=None,
    )
    store.complete(
        second_job.id,
        status="succeeded",
        result=second_result,
        error=None,
    )

    first = store.get_transparency_entry(1)
    second = store.get_transparency_entry(2)
    assert first is not None
    assert second is not None
    assert first.previous_hash == GENESIS_HASH
    assert first.result_sha256 == digest_json(first_result)
    assert second.previous_hash == first.entry_hash
    assert second.result_sha256 == digest_json(second_result)
    assert store.transparency_head() == (2, second.entry_hash)
    assert store.verify_transparency_chain() is True


def test_non_verification_results_do_not_enter_scientific_ledger(tmp_path) -> None:
    store = JobStore(f"sqlite:///{tmp_path / 'plans.db'}")
    store.initialize()
    job = _create_job(store, suffix="3")

    store.complete(
        job.id,
        status="needs_review",
        result={
            "kind": "auto_plan",
            "repository_commit": "a" * 40,
            "plan": {"safe_to_execute": False},
        },
        error=None,
    )

    assert store.transparency_head() == (0, GENESIS_HASH)
    assert store.list_transparency_entries() == []


def test_transparency_rows_reject_update_and_delete(tmp_path) -> None:
    store = JobStore(f"sqlite:///{tmp_path / 'append-only.db'}")
    store.initialize()
    job = _create_job(store, suffix="4")
    store.complete(
        job.id,
        status="succeeded",
        result={"kind": "verification", "value": 1},
        error=None,
    )

    with (
        pytest.raises(SQLAlchemyError, match="append-only"),
        store.engine.begin() as connection,
    ):
        connection.execute(
            text(
                "UPDATE agnxiv_transparency_entries "
                "SET status = 'forged' WHERE sequence = 1"
            )
        )

    with (
        pytest.raises(SQLAlchemyError, match="append-only"),
        store.engine.begin() as connection,
    ):
        connection.execute(
            text(
                "DELETE FROM agnxiv_transparency_entries "
                "WHERE sequence = 1"
            )
        )

    assert store.verify_transparency_chain() is True


def test_public_transparency_api_exposes_commitments_not_secrets(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'public-ledger.db'}"
    store = JobStore(database_url)
    store.initialize()
    job = _create_job(
        store,
        suffix="5",
        api_hash="super-secret-api-key-hash",
    )
    result = {
        "kind": "verification",
        "zero_manifest": True,
        "bundle": {
            "record": {"verdict": "VERIFIED"},
            "private_worker_detail": "not-published-through-ledger",
        },
    }
    store.complete(
        job.id,
        status="succeeded",
        result=result,
        error=None,
    )

    app = create_app(_config(database_url))
    with TestClient(app) as client:
        head = client.get("/v1/transparency/head")
        listing = client.get("/v1/transparency")
        entry = client.get("/v1/transparency/1")

    assert head.status_code == 200
    assert head.json()["sequence"] == 1
    assert head.json()["head_hash"] == entry.json()["entry_hash"]
    assert listing.status_code == 200
    assert len(listing.json()["entries"]) == 1
    assert entry.status_code == 200
    assert entry.json()["result_sha256"] == digest_json(result)
    assert "super-secret-api-key-hash" not in entry.text
    assert "not-published-through-ledger" not in entry.text

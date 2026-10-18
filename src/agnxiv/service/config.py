from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceConfig:
    database_url: str
    api_keys: tuple[str, ...]
    public_base_url: str
    github_token: str | None
    github_repository: str
    github_ref: str
    github_workflow: str
    max_active_jobs_per_key: int
    callback_secret: str
    issuer_private_key_b64: str | None

    @classmethod
    def from_env(cls) -> ServiceConfig:
        api_keys = tuple(
            item.strip()
            for item in os.getenv("AGNXIV_API_KEYS", "").split(",")
            if item.strip()
        )
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "sqlite:///./agnxiv-service.db",
            ),
            api_keys=api_keys,
            public_base_url=os.getenv(
                "AGNXIV_PUBLIC_BASE_URL",
                "http://localhost:8000",
            ).rstrip("/"),
            github_token=os.getenv("AGNXIV_GITHUB_TOKEN") or None,
            github_repository=os.getenv(
                "AGNXIV_GITHUB_REPOSITORY",
                "sushxnthd/agnXiv",
            ),
            github_ref=os.getenv("AGNXIV_GITHUB_REF", "main"),
            github_workflow=os.getenv(
                "AGNXIV_GITHUB_WORKFLOW",
                "hosted-verify.yml",
            ),
            max_active_jobs_per_key=max(
                1,
                int(os.getenv("AGNXIV_MAX_ACTIVE_JOBS_PER_KEY", "3")),
            ),
            callback_secret=os.getenv(
                "AGNXIV_CALLBACK_SECRET",
                "development-only-change-me",
            ),
            issuer_private_key_b64=os.getenv("AGNXIV_ISSUER_PRIVATE_KEY_B64") or None,
        )

    @property
    def production_ready(self) -> bool:
        return (
            self.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
            and bool(self.api_keys)
            and bool(self.github_token)
            and self.callback_secret != "development-only-change-me"
            and self.public_base_url.startswith("https://")
            and bool(self.issuer_private_key_b64)
        )

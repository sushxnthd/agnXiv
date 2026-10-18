from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


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
    max_jobs_per_hour: int
    oidc_audience: str
    issuer_private_key_b64: str | None
    job_stale_minutes: int = 45
    min_api_key_length: int = 32

    @classmethod
    def from_env(cls) -> ServiceConfig:
        api_keys = tuple(
            item.strip()
            for item in os.getenv("AGNXIV_API_KEYS", "").split(",")
            if item.strip()
        )
        public_base_url = os.getenv(
            "AGNXIV_PUBLIC_BASE_URL",
            "http://localhost:8000",
        ).rstrip("/")
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "sqlite:///./agnxiv-service.db",
            ),
            api_keys=api_keys,
            public_base_url=public_base_url,
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
            max_jobs_per_hour=max(
                1,
                int(os.getenv("AGNXIV_MAX_JOBS_PER_HOUR", "20")),
            ),
            oidc_audience=os.getenv(
                "AGNXIV_OIDC_AUDIENCE",
                public_base_url + "/github-actions",
            ),
            issuer_private_key_b64=os.getenv("AGNXIV_ISSUER_PRIVATE_KEY_B64") or None,
            job_stale_minutes=max(
                5,
                int(os.getenv("AGNXIV_JOB_STALE_MINUTES", "45")),
            ),
            min_api_key_length=max(
                16,
                int(os.getenv("AGNXIV_MIN_API_KEY_LENGTH", "32")),
            ),
        )

    @property
    def production_issues(self) -> list[str]:
        issues: list[str] = []
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            issues.append("database_not_postgresql")
        if not self.api_keys:
            issues.append("api_keys_missing")
        elif any(len(key) < self.min_api_key_length for key in self.api_keys):
            issues.append("api_key_too_short")
        elif len(set(self.api_keys)) != len(self.api_keys):
            issues.append("duplicate_api_keys")
        if not self.github_token:
            issues.append("github_dispatch_token_missing")
        public = urlparse(self.public_base_url)
        if (
            public.scheme != "https"
            or not public.hostname
            or public.hostname in {"localhost", "127.0.0.1"}
        ):
            issues.append("public_https_url_invalid")
        audience = urlparse(self.oidc_audience)
        if audience.scheme != "https" or not audience.hostname:
            issues.append("oidc_audience_invalid")
        if not self.issuer_private_key_b64:
            issues.append("issuer_key_missing")
        return issues

    @property
    def production_ready(self) -> bool:
        return not self.production_issues

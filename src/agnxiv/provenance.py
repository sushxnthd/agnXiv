from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

_DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
}


class FileFingerprint(BaseModel):
    path: str
    sha256: str
    size_bytes: int = Field(ge=0)


class DocumentFingerprint(BaseModel):
    name: str
    sha256: str
    size_bytes: int = Field(ge=0)


class ArtifactFingerprint(BaseModel):
    name: str
    kind: Literal["file", "directory"]
    sha256: str
    size_bytes: int = Field(ge=0)
    file_count: int = Field(ge=1)


class ProvenanceManifest(BaseModel):
    algorithm: str = "sha256"
    tree_digest: str
    files: list[FileFingerprint]
    file_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_document(path: str | Path) -> DocumentFingerprint:
    """Fingerprint an exact manuscript or supplementary document."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError(f"document path is not a file: {file_path}")
    return DocumentFingerprint(
        name=file_path.name,
        sha256=sha256_file(file_path),
        size_bytes=file_path.stat().st_size,
    )


def fingerprint_tree(
    root: str | Path,
    *,
    excludes: set[str] | None = None,
) -> ProvenanceManifest:
    """Create a stable content fingerprint for a research repository."""
    base = Path(root)
    if not base.is_dir():
        raise ValueError(f"repository path is not a directory: {base}")

    excluded = _DEFAULT_EXCLUDES if excludes is None else excludes
    files: list[FileFingerprint] = []

    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        rel = path.relative_to(base)
        if any(part in excluded for part in rel.parts):
            continue
        try:
            size = path.stat().st_size
            digest = sha256_file(path)
        except OSError:
            continue
        files.append(
            FileFingerprint(
                path=rel.as_posix(),
                sha256=digest,
                size_bytes=size,
            )
        )

    tree_hasher = hashlib.sha256()
    for file in files:
        tree_hasher.update(file.path.encode("utf-8"))
        tree_hasher.update(b"\0")
        tree_hasher.update(file.sha256.encode("ascii"))
        tree_hasher.update(b"\0")
        tree_hasher.update(str(file.size_bytes).encode("ascii"))
        tree_hasher.update(b"\n")

    return ProvenanceManifest(
        tree_digest=tree_hasher.hexdigest(),
        files=files,
        file_count=len(files),
        total_bytes=sum(file.size_bytes for file in files),
    )


def fingerprint_artifact(path: str | Path) -> ArtifactFingerprint:
    """Fingerprint a declared external dataset, checkpoint, or artifact."""
    artifact_path = Path(path)

    if artifact_path.is_file():
        return ArtifactFingerprint(
            name=artifact_path.name,
            kind="file",
            sha256=sha256_file(artifact_path),
            size_bytes=artifact_path.stat().st_size,
            file_count=1,
        )

    if artifact_path.is_dir():
        tree = fingerprint_tree(artifact_path, excludes=set())
        if tree.file_count == 0:
            raise ValueError(f"artifact directory is empty: {artifact_path}")
        return ArtifactFingerprint(
            name=artifact_path.name,
            kind="directory",
            sha256=tree.tree_digest,
            size_bytes=tree.total_bytes,
            file_count=tree.file_count,
        )

    raise ValueError(f"artifact path does not exist: {artifact_path}")

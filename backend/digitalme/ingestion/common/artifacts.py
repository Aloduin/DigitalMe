"""Immutable content-addressed storage for imported source artifacts."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    sha256: str
    relative_path: str
    size_bytes: int
    media_type: str | None


class ArtifactStore:
    """Store immutable artifacts by SHA-256 using atomic filesystem writes."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def put_file(
        self,
        source_path: Path,
        *,
        source_type: str,
        media_type: str | None = None,
    ) -> ArtifactDescriptor:
        """Copy a file into the store without ever exposing a partial destination."""

        source_path = source_path.expanduser().resolve(strict=True)
        self.root.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        size_bytes = 0
        temporary_path: Path | None = None
        try:
            with (
                source_path.open("rb") as source,
                tempfile.NamedTemporaryFile(
                    mode="wb", dir=self.root, prefix=".artifact-", delete=False
                ) as temporary,
            ):
                temporary_path = Path(temporary.name)
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                    size_bytes += len(chunk)
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())

            sha256 = digest.hexdigest()
            suffix = source_path.suffix.lower()
            relative_path = Path(source_type) / sha256[:2] / sha256 / f"artifact{suffix}"
            destination = self.root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                temporary_path.unlink()
            else:
                temporary_path.replace(destination)
            return ArtifactDescriptor(
                sha256=sha256,
                relative_path=relative_path.as_posix(),
                size_bytes=size_bytes,
                media_type=media_type,
            )
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

    def resolve(self, relative_path: str) -> Path:
        """Resolve a stored path while preventing traversal outside the store."""

        candidate = (self.root / relative_path).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Artifact path escapes the configured raw store")
        return candidate

    def copy_to(self, descriptor: ArtifactDescriptor, destination: Path) -> None:
        """Copy an artifact to a caller-owned path."""

        shutil.copyfile(self.resolve(descriptor.relative_path), destination)

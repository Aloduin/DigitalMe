"""Bounded streaming request-body storage for local ingestion APIs."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import Request


class UploadTooLargeError(ValueError):
    """Raised when a request body exceeds the configured local upload limit."""


class EmptyUploadError(ValueError):
    """Raised when an ingestion request contains no bytes."""


def declared_content_length(request: Request) -> int | None:
    """Parse Content-Length strictly when a client provides it."""

    raw_value = request.headers.get("content-length")
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError("Content-Length must be an integer") from exc
    if value < 0:
        raise ValueError("Content-Length must not be negative")
    return value


async def store_request_body(
    request: Request,
    directory: Path,
    *,
    max_bytes: int,
) -> Path:
    """Stream an HTTP body to a server-named file and remove partial writes on failure."""

    directory = directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix=".chatgpt-upload-",
        suffix=".zip",
        dir=directory,
    )
    path = Path(raw_path)
    total = 0
    try:
        with os.fdopen(descriptor, "wb") as destination:
            async for chunk in request.stream():
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLargeError(
                        f"Upload exceeds the configured limit of {max_bytes} bytes"
                    )
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if total == 0:
            raise EmptyUploadError("Upload body is empty")
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise

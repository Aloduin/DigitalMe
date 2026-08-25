from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from digitalme.api.uploads import UploadTooLargeError, store_request_body
from fastapi import Request


@pytest.mark.asyncio
async def test_streaming_limit_removes_partial_upload_without_content_length(
    tmp_path: Path,
) -> None:
    request = _streaming_request([b"123", b"45"])

    with pytest.raises(UploadTooLargeError, match="4 bytes"):
        await store_request_body(request, tmp_path / "incoming", max_bytes=4)

    assert list((tmp_path / "incoming").glob("*")) == []


def _streaming_request(chunks: list[bytes]) -> Request:
    messages = [{"type": "http.request", "body": chunk, "more_body": True} for chunk in chunks]
    messages.append({"type": "http.request", "body": b"", "more_body": False})

    async def receive() -> dict[str, Any]:
        return messages.pop(0)

    receive_callable: Callable[[], Awaitable[dict[str, Any]]] = receive
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/upload",
            "raw_path": b"/upload",
            "query_string": b"",
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 80),
        },
        receive_callable,
    )

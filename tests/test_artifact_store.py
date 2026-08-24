from pathlib import Path

import pytest
from digitalme.ingestion.common import ArtifactStore


def test_artifact_store_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "export.zip"
    source.write_bytes(b"stable artifact bytes")
    store = ArtifactStore(tmp_path / "raw")

    first = store.put_file(source, source_type="chatgpt", media_type="application/zip")
    second = store.put_file(source, source_type="chatgpt", media_type="application/zip")

    assert first == second
    assert first.size_bytes == len(b"stable artifact bytes")
    assert store.resolve(first.relative_path).read_bytes() == b"stable artifact bytes"
    assert len(list((tmp_path / "raw").rglob("artifact.zip"))) == 1


def test_artifact_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "raw")

    with pytest.raises(ValueError, match="escapes"):
        store.resolve("../outside")

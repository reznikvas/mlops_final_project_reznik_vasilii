"""Повреждённые артефакты отклоняются до десериализации."""

import json
from pathlib import Path

import pytest

from src.features import FEATURES
from src.loaded_models import ModelBundle


def test_bad_checksum_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_VERSION", "unit-test")
    (tmp_path / "ranker.pkl").write_bytes(b"invalid pickle")
    manifest = {
        "schema_version": "1",
        "features": FEATURES,
        "version": "unit-test",
        "files": {"ranker.pkl": {"sha256": "0" * 64}},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="целостность"):
        ModelBundle(tmp_path)


def test_wrong_release_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_VERSION", "expected")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"schema_version": "1", "features": FEATURES, "version": "different"}
        )
    )
    with pytest.raises(ValueError, match="Версия"):
        ModelBundle(tmp_path)

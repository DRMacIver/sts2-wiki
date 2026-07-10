"""Tests for the version single-source module."""

import pytest

from scripts.versions import all_versions, latest_version, version_key


def test_version_key_numeric_sort() -> None:
    assert version_key("v0.98.2") < version_key("v0.99.1") < version_key("v0.100.0")


def test_version_key_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        version_key("not-a-version")


def test_all_versions_from_dirs(tmp_path) -> None:
    for name in ["v0.100.0", "v0.98.2", "v0.99.1", "not-a-version"]:
        (tmp_path / name).mkdir()
    (tmp_path / "v0.97.0.json").write_text("{}")  # files are ignored
    assert all_versions(str(tmp_path)) == ["v0.98.2", "v0.99.1", "v0.100.0"]
    assert latest_version(str(tmp_path)) == "v0.100.0"

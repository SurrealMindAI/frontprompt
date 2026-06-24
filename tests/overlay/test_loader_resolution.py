"""Overlay-bundle resolution: embedded package-data first, dev source-tree fallback.

Guards the wheel-self-containment contract: an installed tool resolves
``frontprompt/_overlay/`` (shipped in the wheel); a dev checkout falls back to
``frontend/dist/``; neither present → a hard FileNotFoundError with build hint.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from frontprompt.overlay import loader


def test_resolve_prefers_embedded_over_dev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the embedded package copy exists, the dev path is never consulted."""
    embedded = tmp_path / "embedded.js"
    embedded.write_text("/*embedded*/", encoding="utf-8")
    dev = tmp_path / "dev.js"
    dev.write_text("/*dev*/", encoding="utf-8")

    monkeypatch.setattr(loader, "_embedded", lambda name: embedded)

    resolved = loader._resolve(loader._BUNDLE_NAME, dev)
    assert resolved == embedded


def test_resolve_falls_back_to_dev_when_no_embedded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No embedded copy → the dev source-tree path is used (if it exists)."""
    dev = tmp_path / "dev.js"
    dev.write_text("/*dev*/", encoding="utf-8")

    monkeypatch.setattr(loader, "_embedded", lambda name: None)

    resolved = loader._resolve(loader._BUNDLE_NAME, dev)
    assert resolved == dev


def test_resolve_none_when_neither_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither embedded nor dev → None (callers raise a hinted FileNotFoundError)."""
    monkeypatch.setattr(loader, "_embedded", lambda name: None)
    missing = tmp_path / "does-not-exist.js"

    assert loader._resolve(loader._BUNDLE_NAME, missing) is None


def test_load_overlay_bundle_missing_raises_with_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing bundle surfaces the canonical build hint, not a bare error."""
    monkeypatch.setattr(loader, "_resolve", lambda name, dev: None)

    with pytest.raises(FileNotFoundError, match=r"frontprompt\.build"):
        loader.load_overlay_bundle()


def test_load_build_manifest_parses_from_resolved_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A well-formed manifest at the resolved path is parsed into the dataclass."""
    payload = {
        "build_session": "sess-1",
        "build_version": "0.0.1",
        "build_git_sha": "deadbeef",
        "schema_version": "0.7.0",
        "generated_at_iso": "2026-06-06T00:00:00Z",
        "bundle_size_bytes": 42,
        "bundle_path_relative": "frontend/dist/overlay.iife.js",
    }
    manifest_file = tmp_path / "build-manifest.json"
    manifest_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(loader, "_resolve", lambda name, dev: manifest_file)

    manifest = loader.load_build_manifest()
    assert manifest.build_session == "sess-1"
    assert manifest.schema_version == "0.7.0"
    assert manifest.bundle_size_bytes == 42


def test_load_build_manifest_malformed_raises_valueerror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A manifest missing required keys raises ValueError with the build hint."""
    manifest_file = tmp_path / "build-manifest.json"
    manifest_file.write_text(json.dumps({"build_session": "x"}), encoding="utf-8")
    monkeypatch.setattr(loader, "_resolve", lambda name, dev: manifest_file)

    with pytest.raises(ValueError, match="malformed"):
        loader.load_build_manifest()

"""Overlay-Bundle Loader — read-only.

Canonical build pipeline (see ARCHITECTURE.md): keine auto-rebuild magic mehr. Liest pre-built bundle + manifest;
failed hart wenn fehlend mit klarer Hinweis-Message.

Build erfolgt ausschließlich via ``python -m frontprompt.build``.

Resolution order (first hit wins):

1. **Embedded package data** — ``frontprompt/_overlay/{overlay.iife.js,build-manifest.json}``.
   This is what ships inside the wheel (``frontprompt.build`` copies the vite
   output here before packaging). An installed tool (``uv tool install``) has
   ONLY this copy — there is no source tree.
2. **Dev source tree** — ``<repo>/frontend/dist/{overlay.iife.js,build-manifest.json}``.
   Fallback for a working clone where ``frontprompt.build`` produced the vite
   output but the package was not (re-)installed. Keeps ``uv run`` dev-loops fast.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import structlog

_LOG = structlog.get_logger(__name__)

#: Project-Root: loader.py liegt bei src/frontprompt/overlay/, parents[3].
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

#: Dev fallback — the raw vite output in the source tree.
_DEV_BUNDLE_PATH: Path = _PROJECT_ROOT / "frontend" / "dist" / "overlay.iife.js"
_DEV_MANIFEST_PATH: Path = _PROJECT_ROOT / "frontend" / "dist" / "build-manifest.json"

#: Embedded package-data subdir name (under the ``frontprompt`` package).
_PACKAGE_OVERLAY_DIR = "_overlay"
_BUNDLE_NAME = "overlay.iife.js"
_MANIFEST_NAME = "build-manifest.json"

_BUILD_HINT: str = (
    "Run `python -m frontprompt.build` to (re-)build + embed the overlay bundle. "
    "See ARCHITECTURE.md (canonical build pipeline)."
)


def _embedded(name: str) -> Traversable | None:
    """Return the embedded package-data resource for ``name`` if it exists.

    ``None`` when the package was installed/run without an embedded overlay
    (e.g. a dev checkout that has never run ``frontprompt.build``).
    """
    try:
        resource = resources.files("frontprompt") / _PACKAGE_OVERLAY_DIR / name
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    return resource if resource.is_file() else None


def _resolve(name: str, dev_path: Path) -> Traversable | Path | None:
    """Resolve a bundle artifact by name: embedded package-data first, dev second."""
    embedded = _embedded(name)
    if embedded is not None:
        return embedded
    if dev_path.is_file():
        return dev_path
    return None


@dataclass(frozen=True)
class BuildManifest:
    """Strukturierte Sicht auf ``build-manifest.json``."""

    build_session: str
    build_version: str
    build_git_sha: str
    schema_version: str
    generated_at_iso: str
    bundle_size_bytes: int
    bundle_path_relative: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> BuildManifest:
        return cls(
            build_session=str(raw["build_session"]),
            build_version=str(raw["build_version"]),
            build_git_sha=str(raw["build_git_sha"]),
            schema_version=str(raw["schema_version"]),
            generated_at_iso=str(raw["generated_at_iso"]),
            bundle_size_bytes=int(raw["bundle_size_bytes"]),
            bundle_path_relative=str(raw["bundle_path_relative"]),
        )


def load_overlay_bundle() -> str:
    """Lade overlay.iife.js als String (embedded package-data, sonst dev source tree).

    Raises:
        FileNotFoundError: wenn das Bundle weder eingebettet noch im Dev-Tree liegt.
            Hinweis-Message verweist auf ``python -m frontprompt.build``.
    """
    resource = _resolve(_BUNDLE_NAME, _DEV_BUNDLE_PATH)
    if resource is None:
        raise FileNotFoundError(
            f"Overlay bundle nicht gefunden (embedded frontprompt/{_PACKAGE_OVERLAY_DIR}/{_BUNDLE_NAME} "
            f"noch dev {_DEV_BUNDLE_PATH}).\n{_BUILD_HINT}"
        )
    _LOG.info("overlay_loader.bundle.read", path=str(resource))
    return resource.read_text(encoding="utf-8")


def load_build_manifest() -> BuildManifest:
    """Lade build-manifest.json als typed dataclass (embedded, sonst dev source tree).

    Raises:
        FileNotFoundError: wenn manifest fehlt.
        ValueError: wenn manifest malformed.
    """
    resource = _resolve(_MANIFEST_NAME, _DEV_MANIFEST_PATH)
    if resource is None:
        raise FileNotFoundError(
            f"Build manifest nicht gefunden (embedded frontprompt/{_PACKAGE_OVERLAY_DIR}/{_MANIFEST_NAME} "
            f"noch dev {_DEV_MANIFEST_PATH}).\n{_BUILD_HINT}"
        )
    raw = json.loads(resource.read_text(encoding="utf-8"))
    try:
        manifest = BuildManifest.from_dict(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Build manifest at {resource} is malformed: {exc}.\n{_BUILD_HINT}") from exc
    _LOG.info(
        "overlay_loader.manifest.read",
        build_session=manifest.build_session,
        schema_version=manifest.schema_version,
        bundle_size_bytes=manifest.bundle_size_bytes,
    )
    return manifest


__all__ = ["BuildManifest", "load_build_manifest", "load_overlay_bundle"]

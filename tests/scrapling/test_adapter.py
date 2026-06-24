"""Integration-Tests für ScraplingAdapter.

Requires: ``uv run playwright install chromium``
          Chromium-Binary muss installiert sein.

Die Tests gegen AsyncDynamicSession sind mit ``pytest.mark.integration``
markiert — können in CI ohne Chromium via ``pytest -m "not integration"``
übersprungen werden. Lokal müssen sie grün sein.

Warum ``pytest.mark.integration`` statt ``pytest.mark.skip``?
    Skip = immer ignoriert. Integration = übersprungbar in resource-limited
    Umgebungen, aber im vollen lokalen Run mandatory. So können wir Chromium-
    Pflicht dokumentieren ohne CI-Block für resource-limited Runtimes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from frontprompt.scrapling.adapter import (
    BrowserLaunchError,
    NavigateResult,
    PageLoadTimeoutError,
    ScraplingAdapter,
    ScraplingNavigateError,
    SubstrateBlockedError,
)
from frontprompt.scrapling.substrate_router import SubstrateRouter
from frontprompt.types import PageSessionId

# ---- Fixtures ---------------------------------------------------------------


def _make_mock_user_data_dir_manager(tmp_path: Path) -> MagicMock:
    """Erstellt einen UserDataDirManager-Mock der einen tmp_path zurückgibt."""
    mock = MagicMock()
    mock.allocate.return_value = tmp_path / "browser-data"
    return mock


# ---- Sync-Tests (kein Chromium) ---------------------------------------------


def test_navigate_result_is_pydantic_model() -> None:
    """NavigateResult ist ein Pydantic BaseModel mit den Pflichtfeldern."""
    result = NavigateResult(
        url="file:///tmp",
        status_code=200,
        dom_snapshot_hash="sha256-abc123",
    )
    assert result.url == "file:///tmp"
    assert result.status_code == 200
    assert result.dom_snapshot_hash == "sha256-abc123"


def test_navigate_result_status_code_optional() -> None:
    """status_code darf None sein (AsyncFetcherSession gibt ggf. None zurück)."""
    result = NavigateResult(
        url="file:///tmp",
        status_code=None,
        dom_snapshot_hash="sha256-0000",
    )
    assert result.status_code is None


def test_scrapling_navigate_error_hierarchy() -> None:
    """ScraplingNavigateError-Hierarchie ist korrekt vererbt."""
    assert issubclass(BrowserLaunchError, ScraplingNavigateError)
    assert issubclass(PageLoadTimeoutError, ScraplingNavigateError)
    assert issubclass(SubstrateBlockedError, ScraplingNavigateError)
    assert issubclass(ScraplingNavigateError, Exception)


def test_scrapling_adapter_instantiable(tmp_path: Path) -> None:
    """ScraplingAdapter lässt sich mit gemockten Dependencies instanziieren."""
    mock_uddm = _make_mock_user_data_dir_manager(tmp_path)
    router = SubstrateRouter()
    adapter = ScraplingAdapter(
        user_data_dir_manager=mock_uddm,
        substrate_router=router,
    )
    assert adapter is not None


# ---- Integration-Tests (Chromium required) ----------------------------------


@pytest.mark.anyio
@pytest.mark.integration
async def test_adapter_dynamic_file_uri(tmp_path: Path) -> None:
    """ScraplingAdapter.navigate() mit file://-URI via AsyncDynamicSession gibt NavigateResult zurück.

    Requires: playwright install chromium.

    Verwendet eine lokale HTML-Datei um Netzwerk-Abhängigkeit zu eliminieren.
    AsyncDynamicSession öffnet real Chromium — das ist der erste E2E-Smoke
    durch den gesamten Scrapling-Integration-Stack.
    """
    # Arrange — lokale HTML-Datei erstellen
    html_file = tmp_path / "test.html"
    html_file.write_text(
        "<html><head><title>Test</title></head><body><p>Hello</p></body></html>",
        encoding="utf-8",
    )
    file_uri = html_file.as_uri()

    mock_uddm = _make_mock_user_data_dir_manager(tmp_path)
    mock_uddm.allocate.return_value = tmp_path / "browser-data"
    (tmp_path / "browser-data").mkdir(parents=True, exist_ok=True)

    router = SubstrateRouter()
    adapter = ScraplingAdapter(
        user_data_dir_manager=mock_uddm,
        substrate_router=router,
    )

    # Act
    result = await adapter.navigate(
        url=file_uri,
        dns_domain="localhost",
        page_session_id=PageSessionId("test-ps-001"),
        substrate_hint="dynamic",
    )

    # Assert
    assert isinstance(result, NavigateResult)
    assert result.url == file_uri or result.url.startswith("file://")
    assert isinstance(result.dom_snapshot_hash, str)
    assert len(result.dom_snapshot_hash) == 64  # SHA-256 hex = 64 chars


@pytest.mark.anyio
@pytest.mark.integration
async def test_adapter_typed_error_on_unreachable_file_uri(tmp_path: Path) -> None:
    """ScraplingAdapter.navigate() mit nicht-existenter URI raises PageLoadTimeoutError.

    Kein raw playwright.TimeoutError oder OSError verlässt den Adapter —
    der MCP-tools-Contract codiert gegen die typisierte Hierarchie.

    Die URI zeigt auf ein nicht-existentes Verzeichnis. Scrapling's
    AsyncDynamicSession wirft playwright.TimeoutError (oder ähnlich) —
    der Adapter wraps das in PageLoadTimeoutError.
    """
    mock_uddm = _make_mock_user_data_dir_manager(tmp_path)
    mock_uddm.allocate.return_value = tmp_path / "browser-data"
    (tmp_path / "browser-data").mkdir(parents=True, exist_ok=True)

    router = SubstrateRouter()
    adapter = ScraplingAdapter(
        user_data_dir_manager=mock_uddm,
        substrate_router=router,
    )

    with pytest.raises(ScraplingNavigateError):
        await adapter.navigate(
            url="file:///nonexistent/path/that/does/not/exist/at/all",
            dns_domain="localhost",
            page_session_id=PageSessionId("test-ps-002"),
            substrate_hint="dynamic",
        )

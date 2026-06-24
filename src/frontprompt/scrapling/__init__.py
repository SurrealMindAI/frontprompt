"""frontprompt.scrapling — Scrapling-Integration-Package.

Öffentliche Re-Exports für alle Downstream-Konsumenten (MCP-tools-Bundle):

    from frontprompt.scrapling import (
        ScraplingAdapter,
        NavigateResult,
        ScraplingNavigateError,
        BrowserLaunchError,
        PageLoadTimeoutError,
        SubstrateBlockedError,
        SubstrateRouter,
        SubstrateName,
        SubstrateHint,
        UserDataDirManager,
    )
"""

from __future__ import annotations

# Adapter + router exports
from frontprompt.scrapling.adapter import (
    BrowserLaunchError,
    NavigateResult,
    PageLoadTimeoutError,
    ScraplingAdapter,
    ScraplingNavigateError,
    SubstrateBlockedError,
)
from frontprompt.scrapling.substrate_router import (
    SUBSTRATE_DYNAMIC,
    SUBSTRATE_FETCHER,
    SUBSTRATE_STEALTHY,
    SubstrateHint,
    SubstrateName,
    SubstrateRouter,
)

# UserDataDirManager export
from frontprompt.scrapling.user_data_dir import UserDataDirManager

__all__ = [
    "SUBSTRATE_DYNAMIC",
    "SUBSTRATE_FETCHER",
    "SUBSTRATE_STEALTHY",
    "BrowserLaunchError",
    "NavigateResult",
    "PageLoadTimeoutError",
    "ScraplingAdapter",
    "ScraplingNavigateError",
    "SubstrateBlockedError",
    "SubstrateHint",
    "SubstrateName",
    "SubstrateRouter",
    "UserDataDirManager",
]

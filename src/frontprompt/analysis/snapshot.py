"""PageSnapshot — a parsed, TTL-aware snapshot of live DOM content.

Holds the parsed HTML document (via the scrapling bridge) and tracks
validity. Does NOT import scrapling directly — it holds the ParsedDocument
opaque type from the bridge.

Lifecycle:
    1. PageAnalyzer.snapshot() calls page.content(), passes HTML to
       the bridge's parse_html(), wraps result in a PageSnapshot.
    2. Snapshot is cached on the analyzer instance.
    3. Snapshot is invalidated by navigate(), eval_js(mutating=True),
       dom_patch(), or explicit invalidate_snapshot().
    4. TTL expiry: if now() - created_at > ttl_seconds, snapshot() auto-
       refreshes on next call.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class PageSnapshot:
    """Parsed snapshot of a live page at a point in time.

    ``snapshot_id`` is a UUID4 string used as a correlation key for
    OutlineRef expiry checks.

    ``parsed_document`` is the opaque ParsedDocument returned by the
    scrapling bridge. Callers outside ``_impl/`` must not reach into it.
    """

    def __init__(
        self,
        html: str,
        parsed_document: Any,
        ttl_seconds: float,
        url: str = "",  # capture page url at snapshot-time
        title: str = "",  # capture page title at snapshot-time
    ) -> None:
        self._html = html
        self._parsed_document = parsed_document
        self._ttl_seconds = ttl_seconds
        self._created_at: float = time.monotonic()
        self._snapshot_id: str = str(uuid.uuid4())
        self._url: str = url
        self._title: str = title
        self._ref_table: dict[str, Any] = {}  # OutlineBuilder populates this

    @property
    def snapshot_id(self) -> str:
        return self._snapshot_id

    @property
    def html(self) -> str:
        return self._html

    @property
    def parsed_document(self) -> Any:
        """Opaque ParsedDocument — only scrapling_bridge.py should read this."""
        return self._parsed_document

    @property
    def url(self) -> str:
        """Page URL at snapshot-time."""
        return self._url

    @property
    def title(self) -> str:
        """Page title at snapshot-time."""
        return self._title

    @property
    def ref_table(self) -> dict[str, Any]:
        """OutlineBuilder reads+writes this. Cleared on invalidate."""
        return self._ref_table

    @property
    def is_expired(self) -> bool:
        """True if the snapshot has exceeded its TTL."""
        return (time.monotonic() - self._created_at) > self._ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self._created_at

    def expires_at_ms(self) -> int:
        """Epoch-ms timestamp when this snapshot expires (for OutlineRef.expires_at_ms)."""
        import time as _time

        created_wall = _time.time() - self.age_seconds
        return int((created_wall + self._ttl_seconds) * 1000)

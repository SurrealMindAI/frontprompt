"""Ready-line format for MCP-daemon ↔ show-child discovery.

Per the per-daemon browser-session isolation model: the show-child prints a
minimal machine-readable line on stdout right after socket-open. The MCP-daemon
parses it to learn its child's session-id, then reads session.json for the rest.
"""

from __future__ import annotations

from frontprompt.ipc.session import format_ready_line, parse_ready_line


def test_format_ready_line() -> None:
    assert format_ready_line("20260523T143045-a1b2c3d4") == "frontprompt:ready 20260523T143045-a1b2c3d4"


def test_parse_ready_line_roundtrip() -> None:
    sid = "20260523T143045-a1b2c3d4"
    assert parse_ready_line(format_ready_line(sid)) == sid


def test_parse_ready_line_strips_trailing_newline() -> None:
    sid = "20260523T143045-a1b2c3d4"
    assert parse_ready_line(format_ready_line(sid) + "\n") == sid
    assert parse_ready_line(format_ready_line(sid) + "\r\n") == sid


def test_parse_ready_line_returns_none_for_unrelated() -> None:
    assert parse_ready_line("some other log line") is None
    assert parse_ready_line("") is None
    assert parse_ready_line("frontprompt:ready ") is None  # empty id after prefix
    assert parse_ready_line("frontprompt:ready") is None  # missing separator

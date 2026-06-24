"""Tests for PageSnapshot — TTL, expiry, id uniqueness."""

from __future__ import annotations

import time
import uuid

import pytest

from frontprompt.analysis.snapshot import PageSnapshot


@pytest.fixture
def minimal_snapshot() -> PageSnapshot:
    sentinel = object()
    return PageSnapshot(html="<html/>", parsed_document=sentinel, ttl_seconds=30.0)


def test_fresh_snapshot_not_expired(minimal_snapshot: PageSnapshot) -> None:
    assert not minimal_snapshot.is_expired


def test_snapshot_expires_after_ttl() -> None:
    snap = PageSnapshot(html="<html/>", parsed_document=None, ttl_seconds=0.001)
    time.sleep(0.01)
    assert snap.is_expired


def test_snapshot_id_is_unique() -> None:
    a = PageSnapshot(html="x", parsed_document=None, ttl_seconds=30.0)
    b = PageSnapshot(html="x", parsed_document=None, ttl_seconds=30.0)
    assert a.snapshot_id != b.snapshot_id


def test_snapshot_id_is_uuid4(minimal_snapshot: PageSnapshot) -> None:
    parsed = uuid.UUID(minimal_snapshot.snapshot_id, version=4)
    assert str(parsed) == minimal_snapshot.snapshot_id


def test_html_property(minimal_snapshot: PageSnapshot) -> None:
    assert minimal_snapshot.html == "<html/>"


def test_parsed_document_identity(minimal_snapshot: PageSnapshot) -> None:
    sentinel = object()
    snap = PageSnapshot(html="x", parsed_document=sentinel, ttl_seconds=30.0)
    assert snap.parsed_document is sentinel


def test_expires_at_ms_is_future(minimal_snapshot: PageSnapshot) -> None:
    now_ms = int(time.time() * 1000)
    assert minimal_snapshot.expires_at_ms() > now_ms


def test_age_seconds_grows_monotonically() -> None:
    snap = PageSnapshot(html="x", parsed_document=None, ttl_seconds=30.0)
    first = snap.age_seconds
    time.sleep(0.01)
    second = snap.age_seconds
    assert second > first

"""Unit-Tests für SubstrateRouter — sync, kein anyio."""

from __future__ import annotations

from frontprompt.scrapling.substrate_router import (
    SUBSTRATE_DYNAMIC,
    SUBSTRATE_FETCHER,
    SUBSTRATE_STEALTHY,
    SubstrateRouter,
)


def test_substrate_router_explicit_hint_stealthy_wins() -> None:
    router = SubstrateRouter()
    assert router.choose(dns_domain="example.com", substrate_hint="stealthy") == SUBSTRATE_STEALTHY


def test_substrate_router_explicit_hint_dynamic_wins() -> None:
    router = SubstrateRouter()
    assert router.choose(dns_domain="nowsecure.nl", substrate_hint="dynamic") == SUBSTRATE_DYNAMIC


def test_substrate_router_explicit_hint_fetcher_wins() -> None:
    router = SubstrateRouter()
    assert router.choose(dns_domain="api.example.com", substrate_hint="fetcher") == SUBSTRATE_FETCHER


def test_substrate_router_no_hint_defaults_to_dynamic() -> None:
    router = SubstrateRouter()
    assert router.choose(dns_domain="google.com", substrate_hint=None) == SUBSTRATE_DYNAMIC


def test_substrate_router_different_domains_same_default() -> None:
    router = SubstrateRouter()
    r1 = router.choose(dns_domain="a.example.com", substrate_hint=None)
    r2 = router.choose(dns_domain="b.example.com", substrate_hint=None)
    assert r1 == r2 == SUBSTRATE_DYNAMIC

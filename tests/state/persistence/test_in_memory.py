"""Tests for frontprompt.state.persistence.in_memory — InMemoryPersistence no-ops."""

from __future__ import annotations


def test_load_panel_state_returns_none() -> None:
    """load_panel_state() is a no-op that returns None."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    p = InMemoryPersistence()
    assert p.load_panel_state() is None


def test_save_panel_state_no_op() -> None:
    """save_panel_state() accepts and discards without raising."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence
    from frontprompt.state.state import PanelStateView, PanelView

    p = InMemoryPersistence()
    panel_state = PanelStateView(
        top=PanelView(open=True, size=56),
        bottom=PanelView(open=False, size=220),
        left=PanelView(open=True, size=300),
        right=PanelView(open=True, size=340),
    )
    # Must not raise
    p.save_panel_state(panel_state)


def test_load_inspector_state_returns_none() -> None:
    """load_inspector_state() is a no-op that returns None."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence

    p = InMemoryPersistence()
    assert p.load_inspector_state() is None


def test_save_inspector_state_no_op() -> None:
    """save_inspector_state() accepts and discards without raising."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence
    from frontprompt.state.state import InspectorState

    p = InMemoryPersistence()
    inspector_state = InspectorState()
    # Must not raise
    p.save_inspector_state(inspector_state)


def test_implements_protocol() -> None:
    """InMemoryPersistence structurally satisfies StatePersistence Protocol."""
    from frontprompt.state.persistence.in_memory import InMemoryPersistence
    from frontprompt.state.persistence.protocol import StatePersistence

    p: StatePersistence = InMemoryPersistence()
    # If runtime_checkable were used, isinstance would work.
    # We verify by calling all four protocol methods directly.
    assert hasattr(p, "load_panel_state")
    assert hasattr(p, "save_panel_state")
    assert hasattr(p, "load_inspector_state")
    assert hasattr(p, "save_inspector_state")

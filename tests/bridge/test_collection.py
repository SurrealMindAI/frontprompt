"""Exhaustiveness-Tests für die Wire-Message-Sammlung in messages.py.

Garantiert dass bei jedem add/rename einer Envelope ALLE Stellen synchron
gehalten werden:
    1. Klasse mit ``Literal[...]``-discriminator existiert
    2. Klasse ist in :data:`OutboundMessage` / :data:`InboundMessage` Union
    3. Klasse ist in :data:`__codegen_roots__` (sonst kein TS-Type)
    4. Klasse ist in :data:`__all__` (sonst kein re-export)

Wenn ein Test fehlschlägt → die offending Klasse anhand der Fehlermeldung
in den genannten Listen registrieren, ODER (falls intentional nicht in der
Union) den Test mit ``# noqa: collection`` als bewussten Bruch markieren.

Konvention: Envelopes "die outbound sein sollen" enden auf ``Requested``
ODER sind explizit als :class:`OverlayReady` / :class:`HeartbeatAck` benannt
(lifecycle-signals). Inbound enden auf ``Message`` oder sind
:class:`Heartbeat`.
"""

from __future__ import annotations

import inspect
from typing import Annotated, Literal, get_args, get_origin

from pydantic import BaseModel

from frontprompt.bridge import messages
from frontprompt.bridge.messages import InboundMessage, OutboundMessage

# ---------------------------------------------------------------------------
# Helpers — extract concrete classes from a discriminated Annotated union
# ---------------------------------------------------------------------------


def _unwrap_union_members(annotated_union: object) -> list[type[BaseModel]]:
    """Extract concrete BaseModel-subclasses from an ``Annotated[A|B|..., Field(...)]``."""
    if get_origin(annotated_union) is Annotated:
        inner = get_args(annotated_union)[0]
    else:
        inner = annotated_union
    # inner is now a `A | B | ...` union
    args = get_args(inner)
    return [a for a in args if isinstance(a, type) and issubclass(a, BaseModel)]


def _all_basemodel_classes_in_module() -> list[type[BaseModel]]:
    """Scan messages module for top-level BaseModel-subclasses defined IN the module."""
    out: list[type[BaseModel]] = []
    for _name, obj in inspect.getmembers(messages):
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == messages.__name__
        ):
            out.append(obj)
    return out


def _discriminator_kind_value(cls: type[BaseModel]) -> str | None:
    """Return the Literal-default of ``kind`` field, or None if not present."""
    field = cls.model_fields.get("kind")
    if field is None:
        return None
    anno = field.annotation
    if get_origin(anno) is Literal:
        args = get_args(anno)
        if len(args) == 1 and isinstance(args[0], str):
            return args[0]
    return None


# Module-level discovery — sample fixtures for parametrize
_ALL_CLASSES = _all_basemodel_classes_in_module()
_DISCRIMINATED = [c for c in _ALL_CLASSES if _discriminator_kind_value(c) is not None]
_OUTBOUND_MEMBERS = set(_unwrap_union_members(OutboundMessage))
_INBOUND_MEMBERS = set(_unwrap_union_members(InboundMessage))

# Classes intentionally NOT in any wire union (none currently — but the test
# is future-proof: if you add e.g. nested sub-models inside an envelope and
# don't want them as standalone wire-messages, add them here).
_EXEMPT_FROM_UNIONS: set[type[BaseModel]] = set()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_every_discriminated_class_is_in_a_union() -> None:
    """Jede Klasse mit ``kind: Literal[...]`` MUSS in Outbound ODER Inbound sein."""
    missing: list[str] = []
    for cls in _DISCRIMINATED:
        if cls in _EXEMPT_FROM_UNIONS:
            continue
        if cls not in _OUTBOUND_MEMBERS and cls not in _INBOUND_MEMBERS:
            missing.append(cls.__name__)
    assert not missing, (
        f"Diskriminierte Klassen fehlen in OutboundMessage/InboundMessage Union: {missing}. "
        f"Fix: in messages.py die Klasse zur passenden Union (Annotated[..., discriminator]) hinzufügen."
    )


def test_every_outbound_union_member_is_in_codegen_roots() -> None:
    """Jede Outbound-Klasse MUSS in __codegen_roots__ sein (sonst kein TS-Type)."""
    missing: list[str] = []
    for cls in _OUTBOUND_MEMBERS:
        if cls.__name__ not in messages.__codegen_roots__:
            missing.append(cls.__name__)
    assert not missing, (
        f"OutboundMessage-Member fehlen in __codegen_roots__: {missing}. "
        f"Ohne diesen Eintrag emittiert pydantic-zod-codegen keine TS-Type → silent drift."
    )


def test_every_inbound_union_member_is_in_codegen_roots() -> None:
    missing: list[str] = []
    for cls in _INBOUND_MEMBERS:
        if cls.__name__ not in messages.__codegen_roots__:
            missing.append(cls.__name__)
    assert not missing, (
        f"InboundMessage-Member fehlen in __codegen_roots__: {missing}. "
        f"Ohne diesen Eintrag emittiert pydantic-zod-codegen keine TS-Type → silent drift."
    )


def test_every_union_member_is_in_all() -> None:
    """Jede Wire-Klasse MUSS in __all__ sein (sonst kein explizites re-export)."""
    missing: list[str] = []
    for cls in _OUTBOUND_MEMBERS | _INBOUND_MEMBERS:
        if cls.__name__ not in messages.__all__:
            missing.append(cls.__name__)
    assert not missing, (
        f"Wire-Klassen fehlen in __all__: {missing}. Fix: in messages.py __all__ den Klassen-Namen aufnehmen."
    )


def test_codegen_roots_dont_reference_unknown_names() -> None:
    """Jeder Eintrag in __codegen_roots__ MUSS einer existierenden Klasse im Modul entsprechen."""
    class_names = {c.__name__ for c in _ALL_CLASSES}
    unknown = [name for name in messages.__codegen_roots__ if name not in class_names]
    assert not unknown, (
        f"__codegen_roots__ referenziert Klassen die nicht in messages.py existieren: {unknown}. "
        f"Fix: Eintrag entfernen oder Klasse hinzufügen."
    )


def test_kind_literals_are_unique_across_outbound() -> None:
    """Wire-routing braucht eindeutige ``kind``-Werte — Doppel = ambiguous discriminator."""
    counts: dict[str, list[str]] = {}
    for cls in _OUTBOUND_MEMBERS:
        kind = _discriminator_kind_value(cls)
        assert kind is not None, f"{cls.__name__} hat keinen Literal[kind] obwohl in OutboundMessage"
        counts.setdefault(kind, []).append(cls.__name__)
    duplicates = {k: v for k, v in counts.items() if len(v) > 1}
    assert not duplicates, f"Doppelte kind-literals in Outbound: {duplicates}"


def test_kind_literals_are_unique_across_inbound() -> None:
    counts: dict[str, list[str]] = {}
    for cls in _INBOUND_MEMBERS:
        kind = _discriminator_kind_value(cls)
        assert kind is not None, f"{cls.__name__} hat keinen Literal[kind] obwohl in InboundMessage"
        counts.setdefault(kind, []).append(cls.__name__)
    duplicates = {k: v for k, v in counts.items() if len(v) > 1}
    assert not duplicates, f"Doppelte kind-literals in Inbound: {duplicates}"


def test_outbound_and_inbound_kinds_dont_collide() -> None:
    """Defense in depth: same kind in both directions würde Routing-Bugs ermöglichen."""
    out_kinds = {_discriminator_kind_value(c) for c in _OUTBOUND_MEMBERS}
    in_kinds = {_discriminator_kind_value(c) for c in _INBOUND_MEMBERS}
    overlap = out_kinds & in_kinds
    assert not overlap, (
        f"kind-literals kollidieren zwischen Outbound + Inbound: {overlap}. "
        f"Pydantic kann sie zwar trennen (über Type-Adapter), aber semantisch ist das ein Code-Smell."
    )


def test_every_envelope_carries_schema_version() -> None:
    """Wire-protocol-Vertrag: jede Envelope MUSS ``schema_version: str`` haben."""
    missing: list[str] = []
    for cls in _OUTBOUND_MEMBERS | _INBOUND_MEMBERS:
        field = cls.model_fields.get("schema_version")
        if field is None:
            missing.append(cls.__name__)
    assert not missing, (
        f"Envelopes ohne ``schema_version``-Field: {missing}. "
        f"Wire-protocol-Vertrag verletzt — siehe messages.py module-docstring."
    )

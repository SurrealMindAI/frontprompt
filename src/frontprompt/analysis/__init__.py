"""PageAnalyzer service layer — snapshot-based page analysis via Scrapling.

Public API: PageAnalyzer + all domain types from analysis/types.py.
Internal: PageSnapshot (used by PageAnalyzer internals, not exposed to
socket_server directly).

The ONLY file allowed to import scrapling.* is:
    src/frontprompt/analysis/_impl/scrapling_bridge.py

See: tests/arch/test_scrapling_isolation.py
"""

from frontprompt.analysis.analyzer import NullPageAnalyzer, PageAnalyzer
from frontprompt.analysis.snapshot import PageSnapshot
from frontprompt.analysis.types import (
    AddClass,
    CondensedHtml,
    CondensedHtmlOptions,
    DomPatchOp,
    ElementContext,
    FindByCss,
    FindByLabel,
    FindByRegex,
    FindByRole,
    FindByText,
    FindQuery,
    FindResult,
    InspectField,
    InspectResult,
    OutlineButton,
    OutlineForm,
    OutlineHeading,
    OutlineInput,
    OutlineLandmark,
    OutlineLink,
    OutlineOptions,
    OutlineRef,
    PageOutline,
    PathSegment,
    RelocationResult,
    RelocationStatus,
    RemoveAttribute,
    RemoveClass,
    RemoveElement,
    SetAttribute,
    SetText,
)

__all__ = [
    "AddClass",
    "CondensedHtml",
    "CondensedHtmlOptions",
    "DomPatchOp",
    "ElementContext",
    "FindByCss",
    "FindByLabel",
    "FindByRegex",
    "FindByRole",
    "FindByText",
    "FindQuery",
    "FindResult",
    "InspectField",
    "InspectResult",
    "NullPageAnalyzer",
    "OutlineButton",
    "OutlineForm",
    "OutlineHeading",
    "OutlineInput",
    "OutlineLandmark",
    "OutlineLink",
    "OutlineOptions",
    "OutlineRef",
    "PageAnalyzer",
    "PageOutline",
    "PageSnapshot",
    "PathSegment",
    "RelocationResult",
    "RelocationStatus",
    "RemoveAttribute",
    "RemoveClass",
    "RemoveElement",
    "SetAttribute",
    "SetText",
]

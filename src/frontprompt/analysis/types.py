"""Domain types for the PageAnalyzer service layer.

These are the types that cross the analysis/ package boundary. No scrapling
types leak out; the bridge handles the conversion internally.

All models use ``ConfigDict(extra="forbid")`` (same convention as ipc/protocol.py).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# FindQuery — discriminated union for snapshot-based element finders
# ---------------------------------------------------------------------------


class FindByText(BaseModel):
    """Find elements by visible text content."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
    text: str = Field(min_length=1)
    role: str | None = None
    exact: bool = False  # default: substring, case-insensitive


class FindByRegex(BaseModel):
    """Find elements where a field matches a regex pattern."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["regex"] = "regex"
    pattern: str = Field(min_length=1)
    field: Literal["text", "attribute", "any"] = "text"


class FindByLabel(BaseModel):
    """Find elements by accessible-name / aria-label."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["label"] = "label"
    label_text: str = Field(min_length=1)


class FindByRole(BaseModel):
    """Find elements by ARIA role, optionally filtered by accessible name."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["role"] = "role"
    role: str = Field(min_length=1)
    name: str | None = None


class FindByCss(BaseModel):
    """Low-level CSS selector finder. Prefer text/role/label when possible."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["css"] = "css"
    selector: str = Field(min_length=1)


FindQuery = Annotated[
    FindByText | FindByRegex | FindByLabel | FindByRole | FindByCss,
    Field(discriminator="kind"),
]
"""Discriminated union for snapshot-based element queries."""


# ---------------------------------------------------------------------------
# OutlineRef — opaque reference returned by get_page_outline
# ---------------------------------------------------------------------------


class OutlineRef(BaseModel):
    """Opaque reference to a single entry in a PageOutline.

    Short-lived: only valid within the snapshot that produced it.
    ``expires_at_ms`` is epoch-ms; clients may check before calling
    pick_from_ref.
    """

    model_config = ConfigDict(extra="forbid")

    ref_id: str  # e.g. "out:link:3"
    snapshot_id: str
    expires_at_ms: int  # epoch ms


# ---------------------------------------------------------------------------
# PageOutline entries
# ---------------------------------------------------------------------------


class OutlineHeading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: OutlineRef
    level: int = Field(ge=1, le=6)
    text: str


class OutlineLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: OutlineRef
    text: str
    href: str | None = None
    in_viewport: bool = False


class OutlineButton(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: OutlineRef
    text: str
    disabled: bool = False


class OutlineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: OutlineRef
    input_type: str = "text"
    name: str | None = None
    placeholder: str | None = None
    label: str | None = None


class OutlineForm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: OutlineRef
    action: str | None = None
    method: str | None = None
    input_count: int = 0


class OutlineLandmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: OutlineRef
    role: str  # "main", "nav", "aside", "header", "footer", etc.
    label: str | None = None


class PageOutline(BaseModel):
    """Token-optimised structural view of a page snapshot."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    title: str
    url: str
    headings: list[OutlineHeading] = Field(default_factory=list)
    links: list[OutlineLink] = Field(default_factory=list)
    buttons: list[OutlineButton] = Field(default_factory=list)
    inputs: list[OutlineInput] = Field(default_factory=list)
    forms: list[OutlineForm] = Field(default_factory=list)
    landmarks: list[OutlineLandmark] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# OutlineOptions / CondensedHtmlOptions — query configuration
# ---------------------------------------------------------------------------


class OutlineOptions(BaseModel):
    """Options for PageAnalyzer.outline()."""

    model_config = ConfigDict(extra="forbid")

    include_headings: bool = True
    include_links: bool = True
    include_buttons: bool = True
    include_inputs: bool = True
    include_forms: bool = True
    include_landmarks: bool = True
    max_items_per_kind: int = Field(default=50, ge=1, le=200)


class CondensedHtmlOptions(BaseModel):
    """Options for PageAnalyzer.condensed_html()."""

    model_config = ConfigDict(extra="forbid")

    strip_scripts: bool = True
    strip_styles: bool = True
    strip_comments: bool = True
    strip_svg: bool = True
    collapse_whitespace: bool = True
    max_chars: int = Field(default=50_000, ge=1_000, le=500_000)


class CondensedHtml(BaseModel):
    """Result of PageAnalyzer.condensed_html()."""

    model_config = ConfigDict(extra="forbid")

    html: str
    truncated: bool = False
    original_chars: int
    stripped_chars: int


# ---------------------------------------------------------------------------
# InspectField — requested fields for inspect()
# ---------------------------------------------------------------------------

InspectField = Literal[
    "text",
    "role",
    "visible",
    "enabled",
    "focused",
    "checked",
    "in_viewport",
    "accessible_name",
    "attributes",
    "html",
    "outline",
]

_DEFAULT_INSPECT_FIELDS: list[InspectField] = ["text", "role", "visible", "enabled"]


class InspectResult(BaseModel):
    """Per-element inspect result. Fields not requested are absent (None)."""

    model_config = ConfigDict(extra="forbid")

    pick_id: str
    error: Literal["stale_pick"] | None = None
    # static fields (from snapshot)
    text: str | None = None
    role: str | None = None
    accessible_name: str | None = None
    attributes: dict[str, str] | None = None
    html: str | None = None
    outline: dict[str, Any] | None = None
    # dynamic fields (from live page)
    visible: bool | None = None
    enabled: bool | None = None
    focused: bool | None = None
    checked: bool | None = None
    in_viewport: bool | None = None


# ---------------------------------------------------------------------------
# ElementContext + PathSegment — structural navigation
# ---------------------------------------------------------------------------


class PathSegment(BaseModel):
    """One node on the DOM path from root to a picked element."""

    model_config = ConfigDict(extra="forbid")

    tag: str
    role: str | None = None
    text_excerpt: str | None = None
    semantic_landmark: str | None = None


class ElementContext(BaseModel):
    """Structural neighbourhood of a picked element."""

    model_config = ConfigDict(extra="forbid")

    ancestors: list[PathSegment] = Field(default_factory=list)
    prev_sibling: dict[str, Any] | None = None
    next_sibling: dict[str, Any] | None = None
    in_form: bool = False
    in_table: bool = False
    semantic_landmark: str | None = None


# ---------------------------------------------------------------------------
# FindResult — multi-pick finder result
# ---------------------------------------------------------------------------


class FindResult(BaseModel):
    """Result of a multi-match finder (find_by_text, find_similar, etc.)."""

    model_config = ConfigDict(extra="forbid")

    pick_ids: list[str]
    total_matches: int
    captured: int


# ---------------------------------------------------------------------------
# RelocationResult — adaptive pick relocation
# ---------------------------------------------------------------------------

RelocationStatus = Literal["alive", "recovered", "stale"]


class RelocationResult(BaseModel):
    """Per-pick result of PageAnalyzer.relocate()."""

    model_config = ConfigDict(extra="forbid")

    pick_id: str
    status: RelocationStatus
    new_selector: str | None = None
    similarity: float | None = None


# ---------------------------------------------------------------------------
# DomPatchOp — discriminated union for dom_patch operations
# ---------------------------------------------------------------------------


class SetAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_attribute"] = "set_attribute"
    name: str = Field(min_length=1)
    value: str


class RemoveAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_attribute"] = "remove_attribute"
    name: str = Field(min_length=1)


class SetText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["set_text"] = "set_text"
    text: str


class AddClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add_class"] = "add_class"
    class_name: str = Field(min_length=1)


class RemoveClass(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_class"] = "remove_class"
    class_name: str = Field(min_length=1)


class RemoveElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_element"] = "remove_element"


DomPatchOp = Annotated[
    SetAttribute | RemoveAttribute | SetText | AddClass | RemoveClass | RemoveElement,
    Field(discriminator="op"),
]
"""Discriminated union for DOM patch operations."""


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
    # FindQuery variants
    "FindByText",
    "FindQuery",
    # Results
    "FindResult",
    # Inspect
    "InspectField",
    "InspectResult",
    "OutlineButton",
    "OutlineForm",
    "OutlineHeading",
    "OutlineInput",
    "OutlineLandmark",
    "OutlineLink",
    # Options
    "OutlineOptions",
    # OutlineRef + PageOutline
    "OutlineRef",
    "PageOutline",
    # Context + path
    "PathSegment",
    "RelocationResult",
    "RelocationStatus",
    "RemoveAttribute",
    "RemoveClass",
    "RemoveElement",
    # DomPatchOp variants
    "SetAttribute",
    "SetText",
]

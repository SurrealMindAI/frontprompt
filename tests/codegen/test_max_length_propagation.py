"""Permanent assertion: max_length propagation through the codegen pipeline.

Asserts that z.string().max(1000) is present in frontend/src/_generated/state.ts
for both Pick.comment and Region.note. This test:
- Protects against _strip_dead_duplicates regex in bridge/codegen.py accidentally
  removing the constraint in a future codegen-pipeline regression.
- Makes the codegen-pipeline end-to-end max_length invariant visible in CI.

The _generated/state.ts file is committed alongside state.py (codegen atomicity).
This test reads the committed file as text — no subprocess call needed.
"""

from __future__ import annotations

import pathlib

# Path relative to this test file: tests/codegen/ → ../../frontend/src/_generated/state.ts
_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_GENERATED_STATE_TS = _REPO_ROOT / "frontend" / "src" / "_generated" / "state.ts"


def test_pick_comment_max_length_propagated() -> None:
    """Pick.comment max(1000) must be present in generated Zod schema."""
    assert _GENERATED_STATE_TS.exists(), (
        f"Generated state.ts not found at {_GENERATED_STATE_TS}. "
        "Run `python -m frontprompt.build` and commit the result."
    )
    content = _GENERATED_STATE_TS.read_text(encoding="utf-8")
    assert "z.string().max(1000)" in content, (
        "z.string().max(1000) not found in generated state.ts for Pick.comment. "
        "The Phase-1 mitigation may have been silently dropped by the codegen pipeline."
    )


def test_region_note_max_length_propagated() -> None:
    """Region.note max(1000) must be present in generated Zod schema."""
    assert _GENERATED_STATE_TS.exists(), (
        f"Generated state.ts not found at {_GENERATED_STATE_TS}. "
        "Run `python -m frontprompt.build` and commit the result."
    )
    content = _GENERATED_STATE_TS.read_text(encoding="utf-8")
    # z.string().max(1000) must appear at least twice: once for Pick.comment, once for Region.note
    occurrences = content.count("z.string().max(1000)")
    assert occurrences >= 2, (
        f"Expected z.string().max(1000) to appear at least twice in generated state.ts "
        f"(once for Pick.comment, once for Region.note), but found {occurrences} occurrence(s). "
        "The Phase-1 mitigation may have been partially dropped by the codegen pipeline."
    )

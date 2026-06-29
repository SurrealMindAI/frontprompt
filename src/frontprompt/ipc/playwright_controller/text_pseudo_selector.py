"""Pseudo-selector wire format shared by the programmatic-pick encoder and the
PlaywrightPageController decoder.

``ProgrammaticPickService`` encodes a ``(text, role)`` query into a string
selector; ``PlaywrightPageController.query_selector_all`` decodes it back and
routes to Playwright's ``get_by_text`` / ``get_by_role`` for AND-semantics.
Keeping the prefixes + delimiter in one module prevents the encoder and decoder
from drifting apart (a silent split-brain contract otherwise).

The ``FakePageController`` test double uses the encoded string verbatim as a
dict key, so the wire format is pinned by tests — do not change the prefixes or
delimiter without updating those fixtures.
"""

from __future__ import annotations

#: Prefix for a text-only pseudo-selector: ``__text__:<text>``.
TEXT_PREFIX = "__text__:"
#: Prefix for a text+role pseudo-selector: ``__text_role__:<text>|<role>``.
TEXT_ROLE_PREFIX = "__text_role__:"
#: Delimiter between text and role in a ``__text_role__`` selector.
ROLE_DELIMITER = "|"


def encode_text_pseudo_selector(text: str, role: str | None) -> str:
    """Encode a ``(text, optional role)`` query into a pseudo-selector string."""
    if role:
        return f"{TEXT_ROLE_PREFIX}{text}{ROLE_DELIMITER}{role}"
    return f"{TEXT_PREFIX}{text}"


def is_text_pseudo_selector(selector: str) -> bool:
    """True if ``selector`` is a text / text-role pseudo-selector."""
    return selector.startswith(TEXT_PREFIX) or selector.startswith(TEXT_ROLE_PREFIX)


def decode_text_pseudo_selector(selector: str) -> tuple[str, str | None]:
    """Decode a pseudo-selector into ``(text, role | None)``.

    Round-trips :func:`encode_text_pseudo_selector` for the common case, but is
    NOT a total inverse: a ``text`` that itself contains the ``|`` delimiter would
    split at the first ``|`` (role := everything after it). This mirrors the
    original behaviour — picked text with a literal ``|`` is unsupported by the
    get_by_role routing.
    """
    if selector.startswith(TEXT_ROLE_PREFIX):
        text, role = selector[len(TEXT_ROLE_PREFIX) :].split(ROLE_DELIMITER, 1)
        return text, role
    return selector[len(TEXT_PREFIX) :], None


__all__ = [
    "ROLE_DELIMITER",
    "TEXT_PREFIX",
    "TEXT_ROLE_PREFIX",
    "decode_text_pseudo_selector",
    "encode_text_pseudo_selector",
    "is_text_pseudo_selector",
]

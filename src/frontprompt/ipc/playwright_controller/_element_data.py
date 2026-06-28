"""Shared element-descriptor JS — single source of truth for the in-page
fragment that turns a DOM element into a Pick-ready descriptor dict.

Consumed by both :mod:`xpath_query` (as the per-handle ``el.evaluate`` callback)
and :class:`controller.PlaywrightPageController` (the ``_handle_to_element_data``
helper and the ``query_selector_all`` ``capped.map(...)`` body). Lives in its own
module so neither consumer imports the other — ``controller`` already imports
``xpath_query`` in step 5, so the JS could not live in either without a cycle.

The descriptor shape MUST match :class:`state.state.ElementFingerprint` /
``ElementRect`` so ``ProgrammaticPickService`` can build Picks without knowing how
the element was found. ``color_index: i % 32`` mirrors the overlay's 32-slot
palette (kept as a JS literal — it is the in-page convention, not a Python const).
"""

from __future__ import annotations

#: Arrow function ``(el, i) => descriptor``. Usable directly as an
#: ``ElementHandle.evaluate`` callback or as an ``Array.prototype.map`` callback
#: (``.map`` passes ``(element, index)`` which matches ``(el, i)``).
ELEMENT_DESCRIPTOR_FN = """(el, i) => {
    const r = el.getBoundingClientRect();
    const attrs = Object.fromEntries(
        Array.from(el.attributes).map(a => [a.name, a.value])
    );
    const nthIdx = Array.from(
        el.parentElement
            ? el.parentElement.querySelectorAll(el.tagName)
            : [el]
    ).indexOf(el) + 1;
    const idPart = el.id ? `#${el.id}` : '';
    const tag = el.tagName.toLowerCase();
    const nth = `:nth-of-type(${nthIdx})`;
    const generatedSel = idPart ? `${tag}${idPart}` : `${tag}${nth}`;
    return {
        selector: generatedSel,
        fingerprint: {
            tag,
            attributes: attrs,
            text: (el.textContent || '').trim().slice(0, 500),
            path: [],
            parent_name: el.parentElement
                ? el.parentElement.tagName.toLowerCase() : null,
            parent_attribs: el.parentElement
                ? Object.fromEntries(
                    Array.from(el.parentElement.attributes)
                        .map(a => [a.name, a.value])
                  ) : {},
            parent_text: el.parentElement
                ? (el.parentElement.textContent || '').trim().slice(0, 500)
                : '',
            siblings: Array.from(
                el.parentElement
                    ? el.parentElement.children : []
            ).filter(c => c !== el).map(c => c.tagName.toLowerCase()),
            children: Array.from(el.children).map(
                c => c.tagName.toLowerCase()
            ),
        },
        rect: { x: r.x, y: r.y, width: r.width, height: r.height },
        text_snippet: (el.innerText || el.textContent || '').trim().slice(0, 120),
        color_index: i % 32,
    };
}"""

__all__ = ["ELEMENT_DESCRIPTOR_FN"]

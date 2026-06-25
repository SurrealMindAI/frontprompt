/**
 * QuickCommentMode — local-state store for the rapid "comment many elements
 * fast" loop (localState — pure UI-coordination, dies with the page).
 *
 * The mode collapses the whole overlay into a small hovering box; only
 * element-picking stays active (all normal panels hidden). The instant a user
 * picks an element, an inline comment input appears (auto-focused) near the
 * picked element so they can type a note and immediately move on to the next
 * element. Goal: comment many elements very fast.
 *
 * State shape:
 *   - ``active`` — is quick-comment mode on?
 *   - ``pending`` — the pick currently awaiting an inline comment (``{ pickId,
 *     rect }``) or null. ``rect`` is the picked element's viewport rect (from
 *     the Pick), used to position the inline input; null falls back to the
 *     hovering box.
 *
 * This store holds NO backend-counterpart and sends NO wire-messages — it only
 * orchestrates the UI. Persisting the typed comment goes through
 * ``backendState.inspector.updateComment`` (called by the component), and the
 * pick itself is submitted via the existing ``submitPick`` path.
 *
 * localState contract: nothing in ``local-state/`` imports the bridge. This store
 * obeys that — the rect type is duplicated locally rather than importing the
 * generated ``ElementRect`` to keep the module bridge/codegen-free, matching
 * the sibling stores (page-tool, pick-claim).
 */

/** Viewport rect of a picked element — mirror of the Pick's ``element.rect``. */
export interface QuickCommentRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** A pick awaiting its inline comment. */
export interface PendingQuickComment {
  /** The id of the just-submitted pick the inline input edits. */
  pickId: string;
  /** Where to anchor the inline input; null → anchor to the hovering box. */
  rect: QuickCommentRect | null;
}

class QuickCommentMode {
  /** Is quick-comment mode active? */
  active = $state(false);

  /** The pick currently awaiting an inline comment, or null. */
  pending = $state<PendingQuickComment | null>(null);

  /** Enter quick-comment mode. Clears any pending input. */
  enter(): void {
    this.active = true;
    this.pending = null;
  }

  /** Exit quick-comment mode. Clears pending. */
  exit(): void {
    this.active = false;
    this.pending = null;
  }

  /**
   * A pick was captured while in quick-comment mode — open the inline input for
   * it. No-op if the mode is inactive (defensive — picks outside the mode go
   * through the normal flow).
   */
  openInput(pickId: string, rect: QuickCommentRect | null): void {
    if (!this.active) return;
    this.pending = { pickId, rect };
  }

  /**
   * The user finished the inline input (Enter, or blur-with-text) — clear pending
   * so the next pick is ready. The actual persistence is the caller's job
   * (``updateComment``); this store only orchestrates the loop.
   */
  commitInput(): void {
    this.pending = null;
  }

  /** Discard the inline input without saving (Escape). Clears pending only. */
  cancelInput(): void {
    this.pending = null;
  }
}

export const quickCommentMode = new QuickCommentMode();

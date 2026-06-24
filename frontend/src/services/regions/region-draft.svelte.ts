/**
 * RegionDraft — localState für eine Region-im-Entstehen.
 *
 * localState (dies-mit-der-page) — beim Commit wird die Region
 * via backendState.inspector.submitRegion (wire-envelope) zur backend-
 * authoritative Region. Die member-picks werden vorher via
 * backendState.inspector.submitPick einzeln registered (Python-side dedupe
 * + fingerprint-hash).
 *
 * State-machine:
 *   idle
 *     ↓ start()    — User clickt Region-tool-button in LeftPanelTools
 *   drafting (rect=null)
 *     ↓ Pointer-down auf der Page (DrawRegionLayer) → setOrigin()
 *   dragging (origin=set, current=set)
 *     ↓ Pointer-move → updateCurrent()
 *     ↓ Pointer-up → commit()  — wenn rect "valid" (>5x5px)
 *   idle (Region persisted, member-picks generated)
 *
 *   ESC cancel()-bar in jedem state → idle.
 */
import type { ViewportRect } from './region-scanner';
import { scanRegion } from './region-scanner';
import { backendState } from '../../backend-state/backend-state.svelte';
import { analyzeDomRelations, type PickElementRef } from '../relations-analyzer';

class RegionDraft {
  /** True wenn das Region-tool aktiv ist UND wir auf pointer-down warten oder draggen. */
  drafting = $state(false);
  /** Origin der drag-bewegung (pointer-down position) — viewport-coords. */
  origin = $state<{ x: number; y: number } | null>(null);
  /** Aktuelle pointer-position während drag — viewport-coords. */
  current = $state<{ x: number; y: number } | null>(null);

  /** Live-rect berechnet aus origin + current (normalisiert positiv-orientiert). */
  rect = $derived<ViewportRect | null>(
    (() => {
      if (this.origin === null || this.current === null) return null;
      const x = Math.min(this.origin.x, this.current.x);
      const y = Math.min(this.origin.y, this.current.y);
      const width = Math.abs(this.current.x - this.origin.x);
      const height = Math.abs(this.current.y - this.origin.y);
      return { x, y, width, height };
    })()
  );

  /** Enter drafting-mode — DrawRegionLayer aktiviert sich, wartet auf pointer-down. */
  start(): void {
    this.drafting = true;
    this.origin = null;
    this.current = null;
  }

  /** Pointer-down auf der Page → start dragging. */
  setOrigin(x: number, y: number): void {
    this.origin = { x, y };
    this.current = { x, y };
  }

  /** Pointer-move während drag. */
  updateCurrent(x: number, y: number): void {
    if (this.origin === null) return;
    this.current = { x, y };
  }

  /** Exit drafting-mode ohne commit. */
  cancel(): void {
    this.drafting = false;
    this.origin = null;
    this.current = null;
  }

  /**
   * Pointer-up → commit. Scannt DOM-elements im rect, registriert sie als
   * picks (mit dedupe), erzeugt Region mit member_pick_ids.
   *
   * Wenn rect zu klein (<5x5px) oder leer (no elements found): silent cancel,
   * keine Region erzeugt.
   */
  commit(): void {
    const r = this.rect;
    if (r === null || r.width < 5 || r.height < 5) {
      this.cancel();
      return;
    }
    // Step 1: scan DOM → fresh Pick-objects + ihre DOM-elements. submitPick
    // dedupliziert via fingerprint-hash (existing picks behalten ihre ids,
    // neue werden appended). Wir tracken pickId↔element parallel für den
    // nachfolgenden DOM-relations-analyzer.
    const scanned = scanRegion(r, backendState.inspector.picks.length);
    const memberPickIds: string[] = [];
    const pickElementRefs: PickElementRef[] = [];
    for (const { pick, element } of scanned) {
      const id = backendState.inspector.submitPick(pick);
      if (!memberPickIds.includes(id)) memberPickIds.push(id);
      pickElementRefs.push({ pickId: id, element });
    }

    // Step 2: Region selbst persistieren. Drawn-rect ist während des drags
    // viewport-relative — wir konvertieren zu **page-absolute** (Schema 0.6.0+)
    // damit der drawn-intent scroll-invariant ist und screenshots direkt
    // page.screenshot({clip}) füttern können. Plus viewport_snapshot für
    // canvas-size context.
    const pageAbsoluteRect = {
      x: r.x + window.scrollX,
      y: r.y + window.scrollY,
      width: r.width,
      height: r.height,
    };
    backendState.inspector.submitRegion({
      region_id: crypto.randomUUID(),
      rect: pageAbsoluteRect,
      member_pick_ids: memberPickIds,
      note: null,
      timestamp_ms: Date.now(),
      viewport_snapshot: {
        scroll_x: window.scrollX,
        scroll_y: window.scrollY,
        viewport_w: window.innerWidth,
        viewport_h: window.innerHeight,
        document_w: document.documentElement.scrollWidth,
        document_h: document.documentElement.scrollHeight,
      },
    });

    // Step 3: Post-processing — DOM-relations zwischen den picks ableiten
    // und persistieren. Dedup gegen existing relations passiert im analyzer.
    const derivedRelations = analyzeDomRelations(pickElementRefs, backendState.inspector.relations);
    for (const relation of derivedRelations) {
      backendState.inspector.submitRelation(relation);
    }

    this.cancel();
  }
}

export const regionDraft = new RegionDraft();

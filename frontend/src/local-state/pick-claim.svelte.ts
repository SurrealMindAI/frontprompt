/**
 * PickClaim — globaler Coordination-Service für den Pick-Mode.
 *
 * Renamed von InspectClaim: "Pick" passt zur User-Aktion ("ein
 * Element auf der Page picken"). Die technische DOM-overlay-Surface
 * (``InspectorLayer``) behält ihren Namen — separate concern (Implementation-
 * detail, nicht user-verb).
 *
 * Problem: mehrere UI-buttons wollen den Pick-Mode starten — der globale
 * Toggle (LeftPanelTools) UND jeder PickPicker-pick-button (RelationsTab,
 * Phase-2-uses). Es darf aber nur EINER gleichzeitig aktiv sein, und jeder
 * Button braucht eigenen pick-callback (default-submit vs PickPicker-setValue).
 *
 * Lösung: ein zentraler Claim-Singleton in localState (dies-mit-der-
 * page, UI-coordination, kein backend-counterpart):
 *
 *   - ``current`` ist ein ``{ id, onPick, onCancel? }`` oder null
 *   - ``acquire(...)`` setzt den claim + triggert backendState.inspector.activate()
 *     (Panels retracten via derived inspector.active, page wird frei für Klicks)
 *   - ``release()`` clear claim + backendState.inspector.cancel()
 *   - ``isClaimedBy(id)`` — UI-buttons können check ob sie's sind
 *
 * Last-write-wins: ein neuer acquire ersetzt den existing claim, und der
 * verdrängte claim bekommt ``onCancel?.()`` als Notification.
 *
 * Rendering-rule für jeden PickButton:
 *   active   = pickClaim.isClaimedBy(myId)
 *   disabled = pickClaim.current !== null && !active
 *
 * App.svelte's InspectorLayer-mount ist die einzige Stelle die die Pick-mode-UI
 * rendert — onPickCaptured + onCancel routen via pickClaim, NICHT direkt zum
 * backend.
 */
import type { Pick } from '../_generated/state';
import { backendState } from '../backend-state/backend-state.svelte';

/** Default-id für den globalen Toggle (LeftPanelTools). */
export const GLOBAL_PICK_ID = 'pick:global';

export interface PickClaimRecord {
  /** Stable identifier for the claim — used by ``isClaimedBy(id)``. */
  id: string;
  /** Called with the captured pick on click. */
  onPick: (pick: Pick) => void;
  /** Called when the claim is released without a pick (ESC, preemption). */
  onCancel?: () => void;
}

class PickClaim {
  current = $state<PickClaimRecord | null>(null);

  /**
   * Take over the pick-mode. If something else was claiming, its onCancel
   * fires first (preemption-notification). Triggers backend
   * ``inspector.activate()`` so panels retract — visible to all UI-buttons via
   * the same derived state.
   */
  acquire(record: PickClaimRecord): void {
    const prev = this.current;
    this.current = record;
    if (prev && prev.id !== record.id) {
      prev.onCancel?.();
    }
    if (!backendState.inspector.active) {
      backendState.inspector.activate();
    }
  }

  /**
   * Release without firing the current claim. Used by InspectorLayer's
   * cancel-handler (ESC, click on nothing) — the caller already fired
   * onCancel before this is called.
   */
  releaseSilently(): void {
    this.current = null;
    if (backendState.inspector.active) {
      backendState.inspector.cancel();
    }
  }

  /** Caller wants to abort their own claim explicitly. */
  release(): void {
    const prev = this.current;
    this.current = null;
    prev?.onCancel?.();
    if (backendState.inspector.active) {
      backendState.inspector.cancel();
    }
  }

  /** True if the given id currently holds the claim. */
  isClaimedBy(id: string): boolean {
    return this.current?.id === id;
  }

  /**
   * Convenience: route the captured pick to the current claim and then
   * release. If no claim is set (defensive), this is a no-op — the pick is
   * dropped silently and pick-mode exits.
   *
   * Called by App.svelte's InspectorLayer-mount as onPickCaptured.
   */
  routePick(pick: Pick): void {
    const claim = this.current;
    this.releaseSilently();
    claim?.onPick(pick);
  }

  /**
   * Called by App.svelte's InspectorLayer-mount as onCancel (ESC, click on
   * nothing). Fires onCancel + clears + deactivates.
   */
  routeCancel(): void {
    const claim = this.current;
    this.releaseSilently();
    claim?.onCancel?.();
  }
}

export const pickClaim = new PickClaim();

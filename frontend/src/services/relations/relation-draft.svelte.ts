/**
 * RelationDraft — localState für eine Relation-im-Entstehen.
 *
 * "Draft" = Relation-Objekt das der User gerade zusammenbaut (source/target/
 * kind/note) aber noch nicht committed hat. Lebt in localState
 * (dies-mit-der-page, kein backend-counterpart) — beim Commit wird daraus eine
 * echte Relation via backendState.inspector.submitRelation.
 *
 * Schema 0.4.0: Endpoints sind heterogeneous (pick ODER region), discriminiert
 * via ``source_kind`` / ``target_kind``. Der Draft hält id+kind pro endpoint.
 * Region endpoints are fully supported in the UI via NodePicker (sub-plan 03)
 * — pick↔pick, pick↔region, region↔pick, and region↔region all work.
 *
 * State-machine:
 *   idle
 *     ↓ start()              — User clickt "+ Create relation"
 *   drafting (source=null, target=null)
 *     ↓ setSource({id, kind})    — via NodePicker (pick OR region endpoint)
 *   drafting (source=set, target=null)
 *     ↓ setTarget({id, kind})
 *   drafting (source=set, target=set, kind=relates_to, note='')
 *     ↓ user setzt kind + note via dropdown/textarea
 *     ↓ commit()             — User clickt "Create"
 *   idle (Relation submitted via backendState.inspector.submitRelation)
 *
 *   Jeder Schritt cancel()-bar → idle.
 */
import type { RelationEndpointKind, RelationKind } from '../../_generated/state';
import { backendState } from '../../backend-state/backend-state.svelte';

const DEFAULT_KIND: RelationKind = 'relates_to';

export interface EndpointRef {
  id: string;
  kind: RelationEndpointKind;
}

class RelationDraft {
  /** True wenn die Draft-UI im RelationsTab gerade geöffnet ist. */
  drafting = $state(false);
  /** Source endpoint (pick oder region) — oder null. */
  source = $state<EndpointRef | null>(null);
  /** Target endpoint (pick oder region) — oder null. */
  target = $state<EndpointRef | null>(null);
  /** Gewählter kind. Default relates_to. */
  kind = $state<RelationKind>(DEFAULT_KIND);
  /** Optionaler note-text. */
  note = $state('');

  /** Convenience: ist der "Create"-button enabled (beide endpoints gefüllt + nicht self-loop)? */
  canCommit = $derived(
    this.source !== null &&
      this.target !== null &&
      !(this.source.id === this.target.id && this.source.kind === this.target.kind)
  );

  /** Enter drafting-mode (vom "+ Create relation"-button). */
  start(): void {
    this.drafting = true;
    this.source = null;
    this.target = null;
    this.kind = DEFAULT_KIND;
    this.note = '';
  }

  /** Exit drafting-mode ohne commit (cancel-button oder ESC). */
  cancel(): void {
    this.drafting = false;
    this.source = null;
    this.target = null;
    this.note = '';
  }

  setSource(endpoint: EndpointRef | null): void {
    this.source = endpoint;
  }

  setTarget(endpoint: EndpointRef | null): void {
    this.target = endpoint;
  }

  setKind(kind: RelationKind): void {
    this.kind = kind;
  }

  setNote(note: string): void {
    this.note = note;
  }

  /**
   * Final commit → backendState.inspector.submitRelation → wire-envelope.
   * No-op wenn !canCommit (defensive — UI button ist disabled).
   */
  commit(): void {
    if (!this.canCommit) return;
    const relationId = crypto.randomUUID();
    backendState.inspector.submitRelation({
      relation_id: relationId,
      source_id: this.source!.id,
      source_kind: this.source!.kind,
      target_id: this.target!.id,
      target_kind: this.target!.kind,
      kind: this.kind,
      note: this.note.trim() === '' ? null : this.note.trim(),
      timestamp_ms: Date.now(),
    });
    this.cancel(); // reset
  }
}

export const relationDraft = new RelationDraft();

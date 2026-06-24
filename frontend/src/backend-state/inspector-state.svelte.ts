/**
 * InspectorState — overlay-mirror für backend-authoritative inspector-state.
 *
 * backendState category: Python's StateManager ist single-writer.
 * Overlay hält reactive mirror + sendet user-intents als
 * ``*Requested`` wire-messages outbound.
 *
 * Lifecycle:
 *   1. User clickt Inspector-toggle in LeftPanelTools
 *      → activate() setzt mirror.active = true optimistic
 *      → wire: inspector_activate_requested
 *      → Python mutiert + broadcastet snapshot
 *      → panels retract automatisch via panel-state.svelte.ts derived effectiveOpen
 *   2. User klickt Element in der Page (im InspectorLayer)
 *      → submitPick() appends + sets activePickId + setzt mirror.active = false
 *      → wire: inspector_pick_made_requested
 *      → Python atomic add_pick → snapshot
 *      → panels kommen automatisch via derived zurück
 *   3. User clickt anderen Pick in der Liste
 *      → selectPick() optimistic + wire pick_selected_requested
 *   4. User editiert Kommentar im Right-Panel + clickt Save
 *      → updateComment() optimistic + wire pick_comment_updated_requested
 */
import { bridge } from '../bridge/bridge.svelte';
import { nextColorIndex } from '../services/color-palette';
import { fingerprintHash } from '../services/element-locator';
import type {
  InspectorState as InspectorView,
  Pick,
  Region,
  Relation,
  RelationKind,
} from '../_generated/state';

const SCHEMA_VERSION = '0.5.0';

export class InspectorState {
  /** Mirror der backend-authoritative state. */
  active = $state(false);
  picks = $state<Pick[]>([]);
  activePickId = $state<string | null>(null);
  /** Schema 0.3.0+: directed edges zwischen Picks und/oder Regions. */
  relations = $state<Relation[]>([]);
  /** Schema 0.4.0+: räumliche Container über Picks. */
  regions = $state<Region[]>([]);
  /**
   * Welche Region ist im right-panel angezeigt? Mutually exclusive mit
   * activePickId (only one details-target).
   */
  activeRegionId = $state<string | null>(null);

  /** Convenience: der derzeit selektierte Pick, oder null wenn keiner. */
  activePick = $derived(this.picks.find((p) => p.pick_id === this.activePickId) ?? null);

  /** Convenience: die derzeit selektierte Region, oder null wenn keine. */
  activeRegion = $derived(this.regions.find((r) => r.region_id === this.activeRegionId) ?? null);

  /**
   * Hydrate mirror from authoritative backend snapshot.
   * Called by backend-state/sync.svelte.ts auf jedem StateSnapshot-receive.
   *
   * Tolerant gegen missing fields (codegen-emitted defaults bei optional).
   */
  hydrate(view: InspectorView): void {
    if (view.active !== undefined) this.active = view.active;
    if (view.picks !== undefined) this.picks = view.picks;
    if (view.active_pick_id !== undefined) this.activePickId = view.active_pick_id;
    if (view.relations !== undefined) this.relations = view.relations;
    if (view.regions !== undefined) this.regions = view.regions;
    if (view.active_region_id !== undefined) this.activeRegionId = view.active_region_id;
  }

  // ----- Intents (optimistic UI + wire-send) ----------------------------------

  /** User toggle ON. Optimistic mirror + wire-send. */
  activate(): void {
    this.active = true;
    void bridge.send({
      kind: 'inspector_activate_requested',
      schema_version: SCHEMA_VERSION,
    });
  }

  /** User pressed ESC oder click-outside. Optimistic mirror + wire-send. */
  cancel(): void {
    this.active = false;
    void bridge.send({
      kind: 'inspector_canceled_requested',
      schema_version: SCHEMA_VERSION,
    });
  }

  /**
   * User clickte ein Element im InspectorLayer.
   *
   * **Phase-1-Dedupe (frontend-side)**: vor der add-to-list-Mutation
   * berechnen wir einen canonical fingerprint-hash und vergleichen mit allen
   * existing picks. Wenn match: KEIN duplicate — wir setzen nur active_pick_id
   * auf den existing pick und senden ``pick_selected_requested`` (statt
   * ``inspector_pick_made_requested``).
   *
   * Wenn neu: Atomic-add (append + active_pick_id + inspector.active=false),
   * wire-send ``inspector_pick_made_requested``. Python reconciliert via
   * snapshot-broadcast.
   *
   * Returns: die pick_id die jetzt ``activePickId`` ist (entweder die existing-
   * matched id oder die neue uuid aus dem incoming pick). PickPicker nutzt das
   * um sein value zu setzen.
   */
  submitPick(pick: Pick): string {
    const newHash = fingerprintHash(pick.element.fingerprint);
    const existing = this.picks.find((p) => fingerprintHash(p.element.fingerprint) === newHash);
    if (existing) {
      // Same DOM-element already picked — reuse its identity, just select it.
      this.activePickId = existing.pick_id;
      this.active = false;
      void bridge.send({
        kind: 'pick_selected_requested',
        schema_version: SCHEMA_VERSION,
        pick_id: existing.pick_id,
      });
      return existing.pick_id;
    }
    // Fresh pick — assign next color from palette, append + activate.
    // color_index ist im Pick-Payload überschreibbar (region-scanner kann eigene
    // Logik haben), aber default ist running count → next color.
    const picked: Pick = {
      ...pick,
      color_index: pick.color_index ?? nextColorIndex(this.picks.length),
    };
    this.picks = [...this.picks, picked];
    this.activePickId = picked.pick_id;
    this.active = false;
    void bridge.send({
      kind: 'inspector_pick_made_requested',
      schema_version: SCHEMA_VERSION,
      pick: picked,
    });
    return picked.pick_id;
  }

  /** User clickte einen Pick in der left-panel-Liste. Clears active-region (mutually exclusive). */
  selectPick(pickId: string): void {
    this.activePickId = pickId;
    this.activeRegionId = null;
    void bridge.send({
      kind: 'pick_selected_requested',
      schema_version: SCHEMA_VERSION,
      pick_id: pickId,
    });
  }

  /** User clickte Save im CommentEditor. */
  updateComment(pickId: string, comment: string): void {
    const idx = this.picks.findIndex((p) => p.pick_id === pickId);
    if (idx >= 0) {
      const current = this.picks[idx]!;
      this.picks = [
        ...this.picks.slice(0, idx),
        { ...current, comment },
        ...this.picks.slice(idx + 1),
      ];
    }
    void bridge.send({
      kind: 'pick_comment_updated_requested',
      schema_version: SCHEMA_VERSION,
      pick_id: pickId,
      comment,
    });
  }

  /** User clickte Delete bei einem Pick. Optimistic + cascade-drop relations + region-member-cleanup. */
  deletePick(pickId: string): void {
    this.picks = this.picks.filter((p) => p.pick_id !== pickId);
    if (this.activePickId === pickId) this.activePickId = null;
    // Optimistic cascade — Python tut dasselbe in delete_pick + ein snapshot.
    // Drop nur Relations bei denen der Pick als pick-kind-endpoint mitspielt.
    // Pick mit gleicher id wie eine Region wäre forensisch kollidierend, aber
    // pick und region leben in getrennten ID-Räumen über die kind-discriminator.
    this.relations = this.relations.filter(
      (r) =>
        !(
          (r.source_kind === 'pick' && r.source_id === pickId) ||
          (r.target_kind === 'pick' && r.target_id === pickId)
        )
    );
    // Region itself stays — Region ist Container, kein owner.
    this.regions = this.regions.map((reg) => ({
      ...reg,
      member_pick_ids: reg.member_pick_ids?.filter((id) => id !== pickId) ?? [],
    }));
    void bridge.send({
      kind: 'pick_deleted_requested',
      schema_version: SCHEMA_VERSION,
      pick_id: pickId,
    });
  }

  // ----- Relations intents (Schema 0.3.0) -------------------------------------

  /** User finished die Creation-UI im RelationsTab. Optimistic-add + wire-send. */
  submitRelation(relation: Relation): void {
    // Last-write-wins by relation_id (analog submitPick).
    const idx = this.relations.findIndex((r) => r.relation_id === relation.relation_id);
    this.relations =
      idx >= 0
        ? [...this.relations.slice(0, idx), relation, ...this.relations.slice(idx + 1)]
        : [...this.relations, relation];
    void bridge.send({
      kind: 'relation_created_requested',
      schema_version: SCHEMA_VERSION,
      relation,
    });
  }

  /** User clickte Delete bei einer Relation. */
  deleteRelation(relationId: string): void {
    this.relations = this.relations.filter((r) => r.relation_id !== relationId);
    void bridge.send({
      kind: 'relation_deleted_requested',
      schema_version: SCHEMA_VERSION,
      relation_id: relationId,
    });
  }

  /**
   * User editierte kind und/oder note im inline-edit-popover.
   * Beide Felder reisen immer mit (single update-envelope).
   */
  updateRelation(relationId: string, kind: RelationKind, note: string | null): void {
    const idx = this.relations.findIndex((r) => r.relation_id === relationId);
    if (idx >= 0) {
      const current = this.relations[idx]!;
      this.relations = [
        ...this.relations.slice(0, idx),
        { ...current, kind, note },
        ...this.relations.slice(idx + 1),
      ];
    }
    void bridge.send({
      kind: 'relation_updated_requested',
      schema_version: SCHEMA_VERSION,
      relation_id: relationId,
      relation_kind: kind,
      note,
    });
  }

  // ----- Region intents (Schema 0.4.0) ----------------------------------------

  /**
   * User finished die Region-draw. Optimistic-add + setze active-region.
   * Last-write-wins by region_id (analog submitPick / submitRelation).
   */
  submitRegion(region: Region): void {
    const idx = this.regions.findIndex((r) => r.region_id === region.region_id);
    // Color-Index: caller darf vorgeben (z.B. wenn aus snapshot rehydratet),
    // sonst next color aus der Palette basierend auf running region count.
    const colored: Region = {
      ...region,
      color_index: region.color_index ?? nextColorIndex(this.regions.length),
    };
    this.regions =
      idx >= 0
        ? [...this.regions.slice(0, idx), colored, ...this.regions.slice(idx + 1)]
        : [...this.regions, colored];
    // Active-region setzen, active-pick clearen (mutually exclusive).
    this.activeRegionId = colored.region_id;
    this.activePickId = null;
    void bridge.send({
      kind: 'region_created_requested',
      schema_version: SCHEMA_VERSION,
      region: colored,
    });
  }

  /** User clickte Delete bei einer Region. Optimistic + cascade-drop relations involving region. */
  deleteRegion(regionId: string): void {
    this.regions = this.regions.filter((r) => r.region_id !== regionId);
    if (this.activeRegionId === regionId) this.activeRegionId = null;
    // Optimistic cascade — Python tut dasselbe in delete_region + ein snapshot.
    this.relations = this.relations.filter(
      (r) =>
        !(
          (r.source_kind === 'region' && r.source_id === regionId) ||
          (r.target_kind === 'region' && r.target_id === regionId)
        )
    );
    void bridge.send({
      kind: 'region_deleted_requested',
      schema_version: SCHEMA_VERSION,
      region_id: regionId,
    });
  }

  /** User editierte note einer Region. */
  updateRegion(regionId: string, note: string | null): void {
    const idx = this.regions.findIndex((r) => r.region_id === regionId);
    if (idx >= 0) {
      const current = this.regions[idx]!;
      this.regions = [
        ...this.regions.slice(0, idx),
        { ...current, note },
        ...this.regions.slice(idx + 1),
      ];
    }
    void bridge.send({
      kind: 'region_updated_requested',
      schema_version: SCHEMA_VERSION,
      region_id: regionId,
      note,
    });
  }

  /** User clickte eine Region in der Liste. Sets active-region, clears active-pick (mutually exclusive). */
  selectRegion(regionId: string): void {
    this.activeRegionId = regionId;
    this.activePickId = null;
    void bridge.send({
      kind: 'region_selected_requested',
      schema_version: SCHEMA_VERSION,
      region_id: regionId,
    });
  }
}

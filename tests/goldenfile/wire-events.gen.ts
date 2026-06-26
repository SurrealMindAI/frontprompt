/* eslint-disable */
/* AUTO-GENERATED — pydantic-zod-codegen pipeline output. DO NOT HAND-EDIT. */
import { z } from "zod";

export type RecordingStatus = "active" | "stopped";

export const RecordingStatus = z.union([z.literal("active"), z.literal("stopped")]);

export type TimelineEntryKind = "page_event" | "pick_ref" | "region_ref" | "relation_ref" | "navigation";

export const TimelineEntryKind = z.union([z.literal("page_event"), z.literal("pick_ref"), z.literal("region_ref"), z.literal("relation_ref"), z.literal("navigation")]);

/**
 * Eine erfasste Seiten-Interaktion (click, pointerdown, keydown).
 *
 * ``wheel``/``scroll`` sind bewusst ausgeschlossen (wire-economy: bis zu 60
 * Events/s würden den expose_function-Transport überlasten).
 * HUD-chrome-Events (isHudChrome=true) sind excluded — die eigenen Toolbar-
 * Clicks dürfen die Aufnahme nicht verschmutzen.
 */
export interface PageEventEntry {
  kind?: "page_event";
  /**
   * Monotoner Sequence-Counter, Python-seitig gestempelt.
   */
  seq: number;
  /**
   * Epoch ms zum Capture-Zeitpunkt.
   */
  timestamp_ms: number;
  /**
   * Event-Typ — nur durable relevante Interactions (wheel/scroll excluded).
   */
  event_type: "click" | "pointerdown" | "keydown";
  /**
   * tag#id.class descriptor des Zielelements.
   */
  target: string;
  /**
   * Tag-Sequenz root→Element (DOM-Pfad).
   */
  target_path?: string[];
  /**
   * Ob event.preventDefault() aufgerufen wurde.
   */
  default_prevented: boolean;
  /**
   * keydown only — gedrückte Taste.
   */
  key?: string | null;
}

export const PageEventEntry = z.object({
  kind: z.literal("page_event").default("page_event"),
  seq: z.number().int(),
  timestamp_ms: z.number().int(),
  event_type: z.enum(["click", "pointerdown", "keydown"]),
  target: z.string(),
  target_path: z.array(z.string()).optional(),
  default_prevented: z.boolean(),
  key: z.string().nullable().optional().default(null),
});

/**
 * Referenz auf einen Pick, der während dieser Aufnahme erstellt wurde.
 *
 * FK-Dehydration (ADR-012): ``pick_id`` ist ein bare UUID-Fremdschlüssel,
 * kein eingebettetes Objekt.
 */
export interface PickRefEntry {
  kind?: "pick_ref";
  seq: number;
  timestamp_ms: number;
  /**
   * FK → Pick.pick_id (client-generated uuid4).
   */
  pick_id: string;
}

export const PickRefEntry = z.object({
  kind: z.literal("pick_ref").default("pick_ref"),
  seq: z.number().int(),
  timestamp_ms: z.number().int(),
  pick_id: z.string(),
});

/**
 * Referenz auf eine Region, die während dieser Aufnahme gezeichnet wurde.
 */
export interface RegionRefEntry {
  kind?: "region_ref";
  seq: number;
  timestamp_ms: number;
  /**
   * FK → Region.region_id.
   */
  region_id: string;
}

export const RegionRefEntry = z.object({
  kind: z.literal("region_ref").default("region_ref"),
  seq: z.number().int(),
  timestamp_ms: z.number().int(),
  region_id: z.string(),
});

/**
 * Referenz auf eine Relation, die während dieser Aufnahme erstellt wurde.
 */
export interface RelationRefEntry {
  kind?: "relation_ref";
  seq: number;
  timestamp_ms: number;
  /**
   * FK → Relation.relation_id.
   */
  relation_id: string;
}

export const RelationRefEntry = z.object({
  kind: z.literal("relation_ref").default("relation_ref"),
  seq: z.number().int(),
  timestamp_ms: z.number().int(),
  relation_id: z.string(),
});

/**
 * Eine Page-Navigation, die vom Python-Session erfasst wurde.
 *
 * Cross-origin-Survival: Aufnahmen laufen über Navigationen hinweg —
 * NavigationEntry dokumentiert den Sprung für spätere Replay-Rekonstruktion.
 */
export interface NavigationEntry {
  kind?: "navigation";
  seq: number;
  timestamp_ms: number;
  /**
   * URL vor der Navigation.
   */
  from_url: string;
  /**
   * URL nach der Navigation.
   */
  to_url: string;
}

export const NavigationEntry = z.object({
  kind: z.literal("navigation").default("navigation"),
  seq: z.number().int(),
  timestamp_ms: z.number().int(),
  from_url: z.string(),
  to_url: z.string(),
});

export type TimelineEntry = PageEventEntry | PickRefEntry | RegionRefEntry | RelationRefEntry | NavigationEntry;

export const TimelineEntry = z.discriminatedUnion("kind", [PageEventEntry, PickRefEntry, RegionRefEntry, RelationRefEntry, NavigationEntry]);

/**
 * Leichtgewichtige Zusammenfassung eines Recordings — ohne ``entries``.
 *
 * Enthalten in jedem StateSnapshot-Broadcast (``RecordingsState.recordings``).
 * Wird im Recordings-Tab und im MCP-Listing-Tool verwendet.
 */
export interface RecordingMeta {
  /**
   * Client-generated uuid4.
   */
  recording_id: string;
  /**
   * User-vergebener Name.
   */
  name: string;
  /**
   * Optionale Beschreibung.
   */
  description?: string;
  status: "active" | "stopped";
  /**
   * Client-clock epoch ms zum Start.
   */
  started_at_ms: number;
  /**
   * None solange aktiv.
   */
  ended_at_ms?: number | null;
  /**
   * Anzahl Timeline-Einträge (≥0).
   */
  entry_count: number;
}

export const RecordingMeta = z.object({
  recording_id: z.string(),
  name: z.string(),
  description: z.string().default(""),
  status: z.enum(["active", "stopped"]),
  started_at_ms: z.number().int(),
  ended_at_ms: z.number().int().nullable().optional().default(null),
  entry_count: z.number().int().gte(0),
});

/**
 * Vollständiges Recording-Aggregat mit Timeline-Einträgen.
 *
 * Nicht in jedem StateSnapshot-Broadcast enthalten — nur in
 * ``RecordingsState.detail_recording`` wenn ``active_detail_recording_id``
 * gesetzt ist. ``entries`` sind append-only, geordnet nach ``seq``.
 *
 * ``origin_session`` folgt der steal-on-mutate-Provenance-Convention
 * von Pick/Region/Relation (sqlite-persistence).
 */
export interface Recording {
  /**
   * Client-generated uuid4 — Identität (keine UNIQUE auf name).
   */
  recording_id: string;
  name: string;
  description?: string;
  status: "active" | "stopped";
  /**
   * Client-clock epoch ms.
   */
  started_at_ms: number;
  ended_at_ms?: number | null;
  /**
   * Timeline-Einträge append-only, geordnet nach seq.
   */
  entries?: (PageEventEntry | PickRefEntry | RegionRefEntry | RelationRefEntry | NavigationEntry)[];
  /**
   * session_id of the session that last mutated this entity (steal-on-mutate provenance via sqlite-persistence). None until first persisted.
   */
  origin_session?: string | null;
}

export const Recording = z.object({
  recording_id: z.string(),
  name: z.string(),
  description: z.string().default(""),
  status: z.enum(["active", "stopped"]),
  started_at_ms: z.number().int(),
  ended_at_ms: z.number().int().nullable().optional().default(null),
  entries: z.array(z.discriminatedUnion("kind", [PageEventEntry, PickRefEntry, RegionRefEntry, RelationRefEntry, NavigationEntry])).optional(),
  origin_session: z.string().nullable().optional().default(null),
});

/**
 * Recording-feature Backend-State — Teil des StateSnapshot.
 *
 * ``active_recording_id`` überlebt cross-origin-Navigationen (backendState).
 * ``active_detail_recording_id`` ist ebenfalls backendState (analog zu
 * ``active_pick_id`` / ``active_region_id`` — right-panel Detail-Selektion
 * persistiert nach Nav). ADR-018 verbietet nur ephemere UI-States (hover,
 * drag), nicht durable Selektionszustände.
 *
 * ``detail_recording`` wird nur befüllt wenn ``active_detail_recording_id``
 * gesetzt ist — vollständige Timeline inklusive. Nicht in jedem Broadcast
 * enthalten wenn None.
 */
export interface RecordingsState {
  /**
   * ID der laufenden Aufnahme, None = nicht aufnehmend.
   */
  active_recording_id?: string | null;
  /**
   * Lightweight Zusammenfassungen aller Recordings.
   */
  recordings?: RecordingMeta[];
  /**
   * ID der im right-panel angezeigten Aufnahme (detail-Ansicht).
   */
  active_detail_recording_id?: string | null;
  /**
   * Vollständiges Recording mit Timeline (nur wenn active_detail_recording_id gesetzt).
   */
  detail_recording?: Recording | null;
}

export const RecordingsState = z.object({
  active_recording_id: z.string().nullable().optional().default(null),
  recordings: z.array(RecordingMeta).optional(),
  active_detail_recording_id: z.string().nullable().optional().default(null),
  detail_recording: Recording.nullable().optional().default(null),
});

/**
 * User klickte "Start Recording" im Recordings-Tab — neue Aufnahme beginnen.
 *
 * **User-Trigger**: Click auf den Start-Button im :svelte:`RecordingsTab`.
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.start_recording`
 * erstellt ein neues :class:`~frontprompt.state.state.Recording`-Aggregat
 * (uuid4 vom Client, status=active) + broadcastet snapshot.
 * **Atomicity**: eine Mutation (add-to-list + active_recording_id = new id).
 */
export interface RecordingStartRequested {
  kind?: "recording_start_requested";
  schema_version?: string;
  /**
   * Benutzer-vergebener Name der Aufnahme.
   */
  name?: string;
  /**
   * Optionale Beschreibung der Aufnahme.
   */
  description?: string;
}

export const RecordingStartRequested = z.object({
  kind: z.literal("recording_start_requested").default("recording_start_requested"),
  schema_version: z.string().default("0.8.0"),
  name: z.string().default("New Recording"),
  description: z.string().default(""),
});

/**
 * User klickte "Stop Recording" — aktive Aufnahme beenden.
 *
 * **User-Trigger**: Click auf den Stop-Button im :svelte:`RecordingsTab` oder
 * in der HUD-Toolbar während einer aktiven Aufnahme.
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.stop_recording`
 * setzt ``recording.status = 'stopped'``, ``ended_at_ms``, und clears
 * ``active_recording_id``. Ein snapshot-broadcast.
 * **Atomicity**: eine Mutation — stop + active_recording_id = None.
 */
export interface RecordingStopRequested {
  kind?: "recording_stop_requested";
  schema_version?: string;
  /**
   * UUID der zu stoppenden aktiven Aufnahme.
   */
  recording_id: string;
}

export const RecordingStopRequested = z.object({
  kind: z.literal("recording_stop_requested").default("recording_stop_requested"),
  schema_version: z.string().default("0.8.0"),
  recording_id: z.string(),
});

/**
 * User editierte Name/Beschreibung einer Aufnahme — Metadaten patchen.
 *
 * **User-Trigger**: Click auf "Save" im Edit-Dialog im :svelte:`RecordingsTab`.
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.rename_recording`
 * patcht ``name`` und ``description`` der Aufnahme. Beide Felder reisen
 * immer mit (kein partial-update-race). Kein-op + warning wenn id unbekannt.
 */
export interface RecordingRenameRequested {
  kind?: "recording_rename_requested";
  schema_version?: string;
  /**
   * UUID der zu umbenennenden Aufnahme.
   */
  recording_id: string;
  /**
   * Neuer Name.
   */
  name: string;
  /**
   * Neue Beschreibung (auch Leer-String gültig).
   */
  description: string;
}

export const RecordingRenameRequested = z.object({
  kind: z.literal("recording_rename_requested").default("recording_rename_requested"),
  schema_version: z.string().default("0.8.0"),
  recording_id: z.string(),
  name: z.string(),
  description: z.string(),
});

/**
 * User clickte eine Aufnahme in der Liste — Detail-Ansicht öffnen (oder deselect).
 *
 * **User-Trigger**: Click auf ein :svelte:`RecordingItem` in :svelte:`RecordingsTab`
 * (oder click auf den aktuell selektierten Eintrag zum Deselektieren).
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.select_recording`
 * setzt ``recordings_state.active_detail_recording_id``. Wenn ``recording_id``
 * None: deselect (active_detail_recording_id = None, detail_recording = None).
 */
export interface RecordingSelectedRequested {
  kind?: "recording_selected_requested";
  schema_version?: string;
  /**
   * UUID der zu selektierenden Aufnahme, oder None zum Deselektieren.
   */
  recording_id: string | null;
}

export const RecordingSelectedRequested = z.object({
  kind: z.literal("recording_selected_requested").default("recording_selected_requested"),
  schema_version: z.string().default("0.8.0"),
  recording_id: z.string().nullable(),
});

/**
 * Overlay erfasste ein Page-Event während einer aktiven Aufnahme.
 *
 * **User-Trigger**: click, pointerdown oder keydown auf ein nicht-HUD-chrome-
 * Element während ``recordings_state.active_recording_id`` gesetzt ist.
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.append_timeline_entry`
 * weist ``seq`` (len(recording.entries)) zu und appended den
 * :class:`~frontprompt.state.state.PageEventEntry` zur Aufnahme.
 * **seq-Semantik**: ``entry`` trägt KEIN ``seq`` auf dem Wire — Python
 * stampft seq Python-seitig als ``len(recording.entries)`` (reviewer Q1).
 * Das UNIQUE(recording_id, seq)-Constraint kann so nie verletzt werden
 * unabhängig von Message-Arrival-Reihenfolge.
 * **HUD-chrome-Filter**: isHudChrome=true-Events werden client-seitig
 * gefiltert und nie in diese Envelope gepackt.
 */
export interface RecordedEventCapturedRequested {
  kind?: "recorded_event_captured_requested";
  schema_version?: string;
  /**
   * UUID der Aufnahme, zu der der Event gehört.
   */
  recording_id: string;
  entry: PageEventEntry;
}

export const RecordedEventCapturedRequested = z.object({
  kind: z.literal("recorded_event_captured_requested").default("recorded_event_captured_requested"),
  schema_version: z.string().default("0.8.0"),
  recording_id: z.string(),
  entry: PageEventEntry,
});

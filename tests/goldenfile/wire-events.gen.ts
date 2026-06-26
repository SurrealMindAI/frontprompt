/* eslint-disable */
/* AUTO-GENERATED — pydantic-zod-codegen pipeline output. DO NOT HAND-EDIT. */
import { z } from "zod";

export type RecordingStatus = "active" | "stopped";

export const RecordingStatus = z.union([z.literal("active"), z.literal("stopped")]);

export type TimelineEntryKind = "page_event" | "pick_ref" | "region_ref" | "relation_ref" | "navigation" | "assertion" | "transcript_segment";

export const TimelineEntryKind = z.union([z.literal("page_event"), z.literal("pick_ref"), z.literal("region_ref"), z.literal("relation_ref"), z.literal("navigation"), z.literal("assertion"), z.literal("transcript_segment")]);

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

export type AssertionType = "selector_exists" | "text_equals" | "text_contains" | "visible" | "url_equals";

export const AssertionType = z.union([z.literal("selector_exists"), z.literal("text_equals"), z.literal("text_contains"), z.literal("visible"), z.literal("url_equals")]);

export type AssertionComparator = "equals" | "contains" | "regex" | "none";

export const AssertionComparator = z.union([z.literal("equals"), z.literal("contains"), z.literal("regex"), z.literal("none")]);

/**
 * Eine Assertion-Checkpoint in der Recording-Timeline (replay + assertions — sub-plan 01).
 *
 * Wird während Replay durch den ``AssertionEvaluator`` ausgewertet. Pass/Fail
 * wird im ``ReplayReport`` festgehalten. Kann nachträglich auf eine gespeicherte
 * Aufnahme via ``AddAssertionRequest`` oder bridge-Authoring hinzugefügt werden.
 *
 * ``assertion_id`` ist die Identität (kein UNIQUE auf description).
 * ``seq`` ist Python-seitig zugewiesen (monoton, analog allen anderen Varianten).
 * ``target`` ist ein CSS-Selektor für element-targeted assertions; leer für ``url_equals``.
 */
export interface AssertionEntry {
  kind?: "assertion";
  /**
   * Monotoner Sequence-Counter, Python-seitig gestempelt.
   */
  seq: number;
  /**
   * Epoch ms zum Erstellungszeitpunkt.
   */
  timestamp_ms: number;
  /**
   * Client-generated uuid4 — Identität.
   */
  assertion_id: string;
  /**
   * Art der Assertion.
   */
  assertion_type: "selector_exists" | "text_equals" | "text_contains" | "visible" | "url_equals";
  /**
   * CSS-Selektor für element-targeted assertions (tag#id.class descriptor). Leer für url_equals.
   */
  target?: string;
  /**
   * Typ des target — 'selector' für DOM-Assertions, 'url' für URL-Assertion.
   */
  target_kind: "selector" | "url";
  /**
   * Erwarteter Wert; None für selector_exists und visible.
   */
  expected?: string | null;
  /**
   * Vergleichsoperator; 'none' für selector_exists und visible.
   */
  comparator: "equals" | "contains" | "regex" | "none";
  /**
   * Human-readable Label für Report-Anzeige.
   */
  description?: string;
}

export const AssertionEntry = z.object({
  kind: z.literal("assertion").default("assertion"),
  seq: z.number().int(),
  timestamp_ms: z.number().int(),
  assertion_id: z.string(),
  assertion_type: z.enum(["selector_exists", "text_equals", "text_contains", "visible", "url_equals"]),
  target: z.string().default(""),
  target_kind: z.enum(["selector", "url"]),
  expected: z.string().nullable().optional().default(null),
  comparator: z.enum(["equals", "contains", "regex", "none"]),
  description: z.string().default(""),
});

/**
 * Ein transkribiertes Sprachsegment in der Recording-Timeline (voice-over — sub-plan 01).
 *
 * Wird nach der Transkription durch den Post-Processor via
 * ``StateManager.append_transcript_segments`` in Batches injiziert.
 * Ein einziger Broadcast am Ende des Batches (nicht pro-Segment — wire-economy).
 *
 * ``timestamp_ms = recording.started_at_ms + start_ms`` — sortiert korrekt
 * im chronologischen Timeline-Merge. ``seq`` ist Python-seitig gestempelt
 * (monotoner Zähler, gleiche Invariante wie alle anderen Varianten).
 * ``backend_id`` dokumentiert welches Backend das Segment erzeugt hat.
 */
export interface TranscriptSegmentEntry {
  kind?: "transcript_segment";
  /**
   * Monotoner Sequence-Counter, Python-seitig gestempelt.
   */
  seq: number;
  /**
   * Epoch ms = recording.started_at_ms + start_ms.
   */
  timestamp_ms: number;
  /**
   * Segmentbeginn relativ zum Aufnahmestart in ms.
   */
  start_ms: number;
  /**
   * Segmentende relativ zum Aufnahmestart in ms.
   */
  end_ms: number;
  /**
   * Transkribierter Text dieses Segments.
   */
  text: string;
  /**
   * Backend-ID das dieses Segment erzeugt hat (z.B. 'mlx_whisper').
   */
  backend_id: string;
}

export const TranscriptSegmentEntry = z.object({
  kind: z.literal("transcript_segment").default("transcript_segment"),
  seq: z.number().int(),
  timestamp_ms: z.number().int(),
  start_ms: z.number().int(),
  end_ms: z.number().int(),
  text: z.string(),
  backend_id: z.string(),
});

export type TimelineEntry =
  | PageEventEntry
  | PickRefEntry
  | RegionRefEntry
  | RelationRefEntry
  | NavigationEntry
  | AssertionEntry
  | TranscriptSegmentEntry;

export const TimelineEntry = z.discriminatedUnion("kind", [PageEventEntry, PickRefEntry, RegionRefEntry, RelationRefEntry, NavigationEntry, AssertionEntry, TranscriptSegmentEntry]);

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
  /**
   * True wenn eine Voice-Over-Aufnahme für dieses Recording vorliegt.
   */
  has_voice_over?: boolean;
  /**
   * Absoluter Pfad zur WAV-Datei. None bis Datei finalisiert.
   */
  audio_path?: string | null;
  /**
   * Transkriptions-Status der Voice-Over-Aufnahme.
   */
  transcription_status?: "none" | "pending" | "transcribing" | "done" | "failed";
}

export const RecordingMeta = z.object({
  recording_id: z.string(),
  name: z.string(),
  description: z.string().default(""),
  status: z.enum(["active", "stopped"]),
  started_at_ms: z.number().int(),
  ended_at_ms: z.number().int().nullable().optional().default(null),
  entry_count: z.number().int().gte(0),
  has_voice_over: z.boolean().default(false),
  audio_path: z.string().nullable().optional().default(null),
  transcription_status: z.enum(["none", "pending", "transcribing", "done", "failed"]).default("none"),
});

/**
 * Benannter Parameter-Deklaration auf einem Recording (replay sub-plan 01).
 *
 * Parameter werden zur Recording-Authoring-Zeit deklariert und beim Replay-Aufruf
 * an konkrete Werte gebunden. Substitutions-Syntax: ``{{param_name}}`` in
 * Navigations-URLs, keydown-Text-Werten und Assertion-Targets.
 *
 * ``name`` ist der Substitutions-Schlüssel (z.B. ``"login_url"``, ``"username"``).
 * Name-Eindeutigkeit wird vom ``StateManager.add_parameter()`` erzwungen.
 */
export interface ParameterDeclaration {
  /**
   * Substitutions-Schlüssel (eindeutig innerhalb der Aufnahme).
   */
  name: string;
  /**
   * Parameter-Typ.
   */
  param_type: "string" | "url" | "selector";
  /**
   * Human-readable Beschreibung.
   */
  description?: string;
  /**
   * Default-Wert wenn nicht beim Replay-Aufruf übergeben; None = kein Default.
   */
  default_value?: string | null;
}

export const ParameterDeclaration = z.object({
  name: z.string(),
  param_type: z.enum(["string", "url", "selector"]),
  description: z.string().default(""),
  default_value: z.string().nullable().optional().default(null),
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
  entries?: (
    | PageEventEntry
    | PickRefEntry
    | RegionRefEntry
    | RelationRefEntry
    | NavigationEntry
    | AssertionEntry
    | TranscriptSegmentEntry
  )[];
  /**
   * Benannte Parameter-Deklarationen für Replay-Parametrisierung (sub-plan 01). Additive field — alte Clients ignorieren unbekannte Felder. Name-Eindeutigkeit wird vom StateManager enforced.
   */
  parameters?: ParameterDeclaration[];
  /**
   * session_id of the session that last mutated this entity (steal-on-mutate provenance via sqlite-persistence). None until first persisted.
   */
  origin_session?: string | null;
  /**
   * True wenn eine Voice-Over-Aufnahme für dieses Recording vorliegt.
   */
  has_voice_over?: boolean;
  /**
   * Absoluter Pfad zur WAV-Datei im Session-Verzeichnis (~/.cache/frontprompt/sessions/<session_id>/recording-<recording_id>.wav). None bis Datei finalisiert.
   */
  audio_path?: string | null;
  /**
   * Transkriptions-Status — one-directional: none→pending→transcribing→done/failed.
   */
  transcription_status?: "none" | "pending" | "transcribing" | "done" | "failed";
  /**
   * Fehlermeldung wenn transcription_status='failed'. Nur auf Recording (nicht RecordingMeta).
   */
  transcription_error?: string | null;
}

export const Recording = z.object({
  recording_id: z.string(),
  name: z.string(),
  description: z.string().default(""),
  status: z.enum(["active", "stopped"]),
  started_at_ms: z.number().int(),
  ended_at_ms: z.number().int().nullable().optional().default(null),
  entries: z.array(z.discriminatedUnion("kind", [PageEventEntry, PickRefEntry, RegionRefEntry, RelationRefEntry, NavigationEntry, AssertionEntry, TranscriptSegmentEntry])).optional(),
  parameters: z.array(ParameterDeclaration).optional(),
  origin_session: z.string().nullable().optional().default(null),
  has_voice_over: z.boolean().default(false),
  audio_path: z.string().nullable().optional().default(null),
  transcription_status: z.enum(["none", "pending", "transcribing", "done", "failed"]).default("none"),
  transcription_error: z.string().nullable().optional().default(null),
});

export type ReplayStatus = "completed" | "failed" | "aborted";

export const ReplayStatus = z.union([z.literal("completed"), z.literal("failed"), z.literal("aborted")]);

/**
 * Per-step Ergebnis innerhalb eines ReplayReport.
 *
 * Ein Eintrag pro TimelineEntry-Versuch beim Replay.
 * ``ok=True AND assertion_passed=False`` ist valid — Schritt lief, aber Assertion schlug fehl.
 * ``ok=False`` bedeutet, dass der Schritt selbst nicht ausgeführt werden konnte.
 */
export interface ReplayStepResult {
  /**
   * seq des zugehörigen TimelineEntry.
   */
  seq: number;
  /**
   * kind des TimelineEntry (mirrors TimelineEntry.kind).
   */
  kind: string;
  /**
   * True = Schritt erfolgreich ausgeführt.
   */
  ok: boolean;
  /**
   * True für pick_ref/region_ref/relation_ref im MVP.
   */
  skipped: boolean;
  /**
   * Grund für das Überspringen.
   */
  skipped_reason?: string | null;
  /**
   * Fehlermeldung wenn ok=False.
   */
  error?: string | null;
  /**
   * None für Nicht-Assertions; True/False für Assertion-Schritte.
   */
  assertion_passed?: boolean | null;
  /**
   * Tatsächlicher Wert für Diagnose (nur bei assertion-Schritten).
   */
  assertion_actual?: string | null;
  /**
   * Ausführungszeit dieses Schritts in ms.
   */
  duration_ms: number;
}

export const ReplayStepResult = z.object({
  seq: z.number().int(),
  kind: z.string(),
  ok: z.boolean(),
  skipped: z.boolean(),
  skipped_reason: z.string().nullable().optional().default(null),
  error: z.string().nullable().optional().default(null),
  assertion_passed: z.boolean().nullable().optional().default(null),
  assertion_actual: z.string().nullable().optional().default(null),
  duration_ms: z.number().int(),
});

/**
 * Leichtgewichtiger Fortschritts-Snapshot während eines aktiven Replays.
 *
 * In RecordingsState.active_replay_progress während einer aktiven Replay-Ausführung.
 * Ermöglicht Live-Fortschrittsanzeige im Overlay ohne den vollen ReplayReport zu senden.
 * ``active_replay_progress`` ist backendState — Replay läuft über Cross-Origin-Navigationen
 * weiter; Progress muss Page-Destruction überleben.
 */
export interface ReplayProgress {
  /**
   * FK → ReplayReport.replay_id.
   */
  replay_id: string;
  /**
   * FK → Recording.recording_id.
   */
  recording_id: string;
  /**
   * seq des aktuell ausgeführten Schritts.
   */
  current_seq: number;
  /**
   * Gesamtzahl der Timeline-Schritte.
   */
  total_steps: number;
  passed_assertions: number;
  failed_assertions: number;
}

export const ReplayProgress = z.object({
  replay_id: z.string(),
  recording_id: z.string(),
  current_seq: z.number().int(),
  total_steps: z.number().int(),
  passed_assertions: z.number().int().gte(0),
  failed_assertions: z.number().int().gte(0),
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
  /**
   * Fortschritts-Snapshot eines aktiven Replay-Laufs (sub-plan 01, Schema 0.9.0+). None wenn kein Replay läuft. Additive field — alte Overlays ignorieren unbekannte Felder. backendState: Replay läuft über Cross-Origin-Navigationen weiter.
   */
  active_replay_progress?: ReplayProgress | null;
}

export const RecordingsState = z.object({
  active_recording_id: z.string().nullable().optional().default(null),
  recordings: z.array(RecordingMeta).optional(),
  active_detail_recording_id: z.string().nullable().optional().default(null),
  detail_recording: Recording.nullable().optional().default(null),
  active_replay_progress: ReplayProgress.nullable().optional().default(null),
});

export type TranscriptionStatus = "none" | "pending" | "transcribing" | "done" | "failed";

export const TranscriptionStatus = z.union([z.literal("none"), z.literal("pending"), z.literal("transcribing"), z.literal("done"), z.literal("failed")]);

/**
 * Ein einzelnes Eingabegerät aus dem sounddevice-Katalog.
 *
 * ``device_id`` ist der sounddevice-Index — stabil innerhalb einer laufenden
 * Sitzung, kann aber nach einem Geräte-Reconnect anders sein.
 */
export interface MicrophoneDevice {
  /**
   * sounddevice-Index des Mikrofons.
   */
  device_id: number;
  /**
   * Anzeigename des Geräts.
   */
  name: string;
  /**
   * Maximale Anzahl der Eingangskanäle.
   */
  channels: number;
  /**
   * Standard-Samplerate in Hz.
   */
  default_sample_rate: number;
}

export const MicrophoneDevice = z.object({
  device_id: z.number().int(),
  name: z.string(),
  channels: z.number().int(),
  default_sample_rate: z.number(),
});

/**
 * Aktueller Zustand der Mikrofon-Enumeration.
 *
 * ``devices`` und ``system_default_device_id`` sind In-Process-State —
 * re-enumeriert durch den Mic-Watcher-Task bei Topologie-Änderungen.
 * ``selected_device_id`` ist die dauerhafte User-Präferenz — persistiert
 * via ``StateManager.set_mic_device(device_id)`` in der ``settings``-Tabelle.
 *
 * Initial (vor dem ersten Watcher-Cycle): devices=[] ist valid.
 */
export interface MicrophoneState {
  /**
   * Alle verfügbaren Eingangsgeräte (leer bis erster Watcher-Cycle).
   */
  devices?: MicrophoneDevice[];
  /**
   * User-gewähltes Gerät (None = System-Default). Durable — Settings-Tabelle.
   */
  selected_device_id?: number | null;
  /**
   * Aktuelles System-Default-Gerät von sounddevice. Nicht durable.
   */
  system_default_device_id?: number | null;
}

export const MicrophoneState = z.object({
  devices: z.array(MicrophoneDevice).optional(),
  selected_device_id: z.number().int().nullable().optional().default(null),
  system_default_device_id: z.number().int().nullable().optional().default(null),
});

/**
 * Dauerhafte User-Einstellungen für das Voice-Over-Feature.
 *
 * Alle Felder sind durable — persistiert in der ``settings``-Key-Value-Tabelle.
 * ``selected_mic_device_id`` lebt NICHT hier sondern in
 * :class:`MicrophoneState`.selected_device_id (co-location von Mic-Concerns).
 */
export interface SettingsState {
  /**
   * Voice-Over-Feature aktiviert (User-Opt-In).
   */
  voice_over_enabled?: boolean;
  /**
   * Gewähltes Backend (None = Auto — erstes 'ready'-Backend).
   */
  selected_transcription_backend_id?: string | null;
}

export const SettingsState = z.object({
  voice_over_enabled: z.boolean().default(false),
  selected_transcription_backend_id: z.string().nullable().optional().default(null),
});

export type TranscriptionBackendStatus = "unavailable" | "missing_dep" | "needs_download" | "downloading" | "ready" | "error";

export const TranscriptionBackendStatus = z.union([z.literal("unavailable"), z.literal("missing_dep"), z.literal("needs_download"), z.literal("downloading"), z.literal("ready"), z.literal("error")]);

/**
 * Status-Info für ein Transkriptions-Backend (z.B. mlx_whisper).
 *
 * ``download_progress`` ist ephemer (In-Process, nicht in SQLite).
 * Das Overlay rendert eine Fortschrittsanzeige während des Downloads.
 */
export interface TranscriptionBackendInfo {
  /**
   * Backend-Bezeichner (z.B. 'mlx_whisper').
   */
  backend_id: string;
  /**
   * Lesbares Label (z.B. 'mlx-whisper (Apple Silicon)').
   */
  display_name: string;
  /**
   * Aktueller Verfügbarkeitsstatus.
   */
  status: "unavailable" | "missing_dep" | "needs_download" | "downloading" | "ready" | "error";
  /**
   * 0.0–1.0 während Download; None sonst. Ephemer (nicht persistiert).
   */
  download_progress?: number | null;
  /**
   * Fehlermeldung bei status='error'.
   */
  error_message?: string | null;
}

export const TranscriptionBackendInfo = z.object({
  backend_id: z.string(),
  display_name: z.string(),
  status: z.enum(["unavailable", "missing_dep", "needs_download", "downloading", "ready", "error"]),
  download_progress: z.number().nullable().optional().default(null),
  error_message: z.string().nullable().optional().default(null),
});

/**
 * Aggregierter Status aller bekannten Transkriptions-Backends.
 *
 * Python-authoritative — Backend bestimmt Verfügbarkeit via probe_status().
 * Nicht in SQLite persistiert (Neustart → erneutes Probing korrekt).
 */
export interface TranscriptionState {
  /**
   * Liste aller bekannten Backends mit ihrem Status.
   */
  backends?: TranscriptionBackendInfo[];
}

export const TranscriptionState = z.object({
  backends: z.array(TranscriptionBackendInfo).optional(),
});

/**
 * User klickte "Start Recording" im Recordings-Tab — neue Aufnahme beginnen.
 *
 * **User-Trigger**: Click auf den Start-Button im :svelte:`RecordingsTab`.
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.start_recording`
 * erstellt ein neues :class:`~frontprompt.state.state.Recording`-Aggregat
 * (uuid4 vom Client, status=active) + broadcastet snapshot.
 * **Atomicity**: eine Mutation (add-to-list + active_recording_id = new id).
 *
 * **Voice-Over-Extension (Schema 0.10.0, additive, backward-compat)**:
 * Wenn ``with_voice_over=True``, startet der Server zusätzlich den
 * :class:`~frontprompt.voice.audio_capture.AudioCaptureManager` und fängt
 * das Mikrofon-Audio in eine WAV-Datei. ``mic_device_id=None`` bedeutet
 * System-Default. Beide Felder haben Defaults — alte Overlays ohne Voice-Over
 * senden sie nicht und bekommen trotzdem das gewohnte Verhalten.
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
  /**
   * True = Voice-Over-Aufnahme starten (Mikrofon-Capture + Transkription).
   */
  with_voice_over?: boolean;
  /**
   * sounddevice-Index des zu verwendenden Mikrofons. None = System-Default.
   */
  mic_device_id?: number | null;
}

export const RecordingStartRequested = z.object({
  kind: z.literal("recording_start_requested").default("recording_start_requested"),
  schema_version: z.string().default("0.10.0"),
  name: z.string().default("New Recording"),
  description: z.string().default(""),
  with_voice_over: z.boolean().default(false),
  mic_device_id: z.number().int().nullable().optional().default(null),
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
  schema_version: z.string().default("0.10.0"),
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
  schema_version: z.string().default("0.10.0"),
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
  schema_version: z.string().default("0.10.0"),
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
  schema_version: z.string().default("0.10.0"),
  recording_id: z.string(),
  entry: PageEventEntry,
});

/**
 * User fügte eine Assertion zur Aufnahme hinzu (UI-Assertion-Authoring).
 *
 * **User-Trigger**: User klickt "Add Assertion" im :svelte:`AssertionAuthoringPanel`
 * und bestätigt die Assertion-Definition.
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.add_assertion_to_timeline`
 * weist ``seq`` zu (Python-seitig) und appended / inserted die neue Assertion.
 * **Atomicity**: eine Mutation — append/insert + seq-Stempel + snapshot-broadcast.
 *
 * ``assertion`` enthält alle Felder des :class:`~frontprompt.state.state.AssertionEntry`
 * **ohne** ``seq`` (Python stamps seq atomisch). ``insert_after_seq=None`` bedeutet
 * append (nach dem letzten bestehenden Eintrag); ein Integer-Wert bedeutet Insert
 * nach dem Eintrag mit dem entsprechenden ``seq``.
 */
export interface AssertionAddedToRecordingRequested {
  kind?: "assertion_added_to_recording_requested";
  schema_version?: string;
  /**
   * UUID der Aufnahme, zu der die Assertion hinzugefügt wird.
   */
  recording_id: string;
  /**
   * Assertion-Payload ohne ``seq`` — alle Felder aus AssertionEntry ausser seq (Python stamps seq). Enthält: assertion_id, assertion_type, target, target_kind, expected, comparator, description.
   */
  assertion: {
    [k: string]: unknown;
  };
  /**
   * None = append nach dem letzten Eintrag. Integer = insert nach dem Eintrag mit dem entsprechenden seq.
   */
  insert_after_seq?: number | null;
}

export const AssertionAddedToRecordingRequested = z.object({
  kind: z.literal("assertion_added_to_recording_requested").default("assertion_added_to_recording_requested"),
  schema_version: z.string().default("0.10.0"),
  recording_id: z.string(),
  assertion: z.object({}),
  insert_after_seq: z.number().int().nullable().optional().default(null),
});

/**
 * User entfernte eine Assertion aus der Aufnahme.
 *
 * **User-Trigger**: Click auf den x-button bei einer Assertion im
 * :svelte:`AssertionAuthoringPanel` oder in der Timeline-Ansicht.
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.delete_assertion`
 * entfernt den AssertionEntry aus ``recording.entries``. No-op + idempotente
 * rehydrate-broadcast wenn id unbekannt.
 */
export interface AssertionDeletedRequested {
  kind?: "assertion_deleted_requested";
  schema_version?: string;
  /**
   * UUID der Aufnahme, aus der die Assertion entfernt wird.
   */
  recording_id: string;
  /**
   * UUID der zu entfernenden Assertion.
   */
  assertion_id: string;
}

export const AssertionDeletedRequested = z.object({
  kind: z.literal("assertion_deleted_requested").default("assertion_deleted_requested"),
  schema_version: z.string().default("0.10.0"),
  recording_id: z.string(),
  assertion_id: z.string(),
});

/**
 * User aktualisierte Felder einer bestehenden Assertion (Partial-Patch).
 *
 * **User-Trigger**: User editiert eine Assertion im :svelte:`AssertionAuthoringPanel`
 * und klickt "Save".
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.update_assertion`
 * patcht nur die Felder, die nicht ``None`` sind (None = keine Änderung).
 * **Semantik**: ``None``-Felder im Payload sind Sentinel für "dieses Feld nicht
 * ändern" — ein Leer-String würde den Wert auf ``""`` setzen.
 */
export interface AssertionUpdatedRequested {
  kind?: "assertion_updated_requested";
  schema_version?: string;
  /**
   * UUID der Aufnahme, die die Assertion enthält.
   */
  recording_id: string;
  /**
   * UUID der zu patchenden Assertion.
   */
  assertion_id: string;
  /**
   * Neuer assertion_type; None = unverändert.
   */
  assertion_type?: ("selector_exists" | "text_equals" | "text_contains" | "visible" | "url_equals") | null;
  /**
   * Neuer target (CSS-Selektor oder URL-Pattern); None = unverändert.
   */
  target?: string | null;
  /**
   * Neuer expected-Wert; None = unverändert (kein Löschen-Sentinel).
   */
  expected?: string | null;
  /**
   * Neue human-readable Beschreibung; None = unverändert.
   */
  description?: string | null;
}

export const AssertionUpdatedRequested = z.object({
  kind: z.literal("assertion_updated_requested").default("assertion_updated_requested"),
  schema_version: z.string().default("0.10.0"),
  recording_id: z.string(),
  assertion_id: z.string(),
  assertion_type: z.enum(["selector_exists", "text_equals", "text_contains", "visible", "url_equals"]).nullable().optional().default(null),
  target: z.string().nullable().optional().default(null),
  expected: z.string().nullable().optional().default(null),
  description: z.string().nullable().optional().default(null),
});

/**
 * User wählte ein Mikrofon in den Settings — dauerhaft persistieren.
 *
 * **User-Trigger**: Auswahl eines Mikrofons im :svelte:`SettingsTab` (MicrophoneSelector).
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.set_mic_device`
 * persistiert ``selected_device_id`` in der ``settings``-Tabelle + broadcastet
 * ein Update von ``microphone_state.selected_device_id`` im nächsten Snapshot.
 * **Semantik**: ``mic_device_id=None`` bedeutet "System-Default verwenden" (User-
 * Reset auf die automatische Auswahl). Eine integer ID ist ein sounddevice-Index.
 */
export interface SetMicDeviceRequested {
  kind?: "set_mic_device_requested";
  schema_version?: string;
  /**
   * sounddevice-Index des zu setzenden Mikrofons. None = System-Default.
   */
  mic_device_id: number | null;
}

export const SetMicDeviceRequested = z.object({
  kind: z.literal("set_mic_device_requested").default("set_mic_device_requested"),
  schema_version: z.string().default("0.10.0"),
  mic_device_id: z.number().int().nullable(),
});

/**
 * User wählte ein Transkriptions-Backend in den Settings — dauerhaft persistieren.
 *
 * **User-Trigger**: Auswahl eines Backends im :svelte:`SettingsTab` (BackendSelector).
 * **Server-Wirkung**: :meth:`~frontprompt.state.StateManager.set_settings`
 * persistiert ``selected_transcription_backend_id`` in der ``settings``-Tabelle
 * + broadcastet ein Update von ``settings_state`` im nächsten Snapshot.
 * **Semantik**: ``backend_id=None`` bedeutet "Auto" (erstes ``ready``-Backend).
 * Ein String ist der ``backend_id`` eines :class:`~frontprompt.state.state.TranscriptionBackendInfo`.
 */
export interface SetTranscriptionBackendRequested {
  kind?: "set_transcription_backend_requested";
  schema_version?: string;
  /**
   * Backend-ID (z.B. 'mlx_whisper'). None = Auto (erstes 'ready'-Backend).
   */
  backend_id: string | null;
}

export const SetTranscriptionBackendRequested = z.object({
  kind: z.literal("set_transcription_backend_requested").default("set_transcription_backend_requested"),
  schema_version: z.string().default("0.10.0"),
  backend_id: z.string().nullable(),
});

/**
 * User clickte "Download" für ein Transkriptions-Backend — Modell-Download starten.
 *
 * **User-Trigger**: Click auf den Download-Button eines Backends im :svelte:`SettingsTab`.
 * **Server-Wirkung**: :meth:`~frontprompt.show_session.ShowSession._on_trigger_model_download`
 * startet ``TranscriptionBackend.ensure(progress_cb)`` als ``tg.start_soon``-Task.
 * ``ensure()`` spiegelt die ``ensure_chromium``-Pattern: probe-first, download-only-if-needed.
 * Fortschritt reist via ``StateManager.update_transcription_backend_status()`` → Snapshot-Broadcast.
 * **Semantik**: ``backend_id`` ist ein Pflicht-String — der User klickt auf ein spezifisches
 * Backend, kein Auto-Mode. Unbekannte ``backend_id`` → silent ignore + warning-log.
 */
export interface TriggerModelDownloadRequested {
  kind?: "trigger_model_download_requested";
  schema_version?: string;
  /**
   * Backend-ID für den Modell-Download (z.B. 'mlx_whisper'). Pflicht — kein None.
   */
  backend_id: string;
}

export const TriggerModelDownloadRequested = z.object({
  kind: z.literal("trigger_model_download_requested").default("trigger_model_download_requested"),
  schema_version: z.string().default("0.10.0"),
  backend_id: z.string(),
});

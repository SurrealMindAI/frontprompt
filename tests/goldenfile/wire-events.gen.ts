/* eslint-disable */
/* AUTO-GENERATED — pydantic-zod-codegen pipeline output. DO NOT HAND-EDIT. */
import { z } from "zod";

/**
 * Äußerer Container für alle Daemon→Tab Wire-Events (Channel 2).
 *
 * Enthält Daemon-Metadaten (`daemon_id`, `schema_version`,
 * `emitted_at_monotonic_ns`) plus den discriminated-union `payload`.
 *
 * Wire-Serialisierung: `model_dump(mode='json')` → JSON-RPC params-Objekt.
 * Wire-Deserialisierung: `EventEnvelope.model_validate(raw_dict)`.
 */
export interface EventEnvelope {
  schema_version: 1;
  daemon_id: string;
  emitted_at_monotonic_ns: number;
  payload: SessionStarted | PageNavigated | PickAcknowledged | AnnotationPersisted;
}
/**
 * Daemon→Tab: eine neue PageSession wurde im Daemon geöffnet.
 *
 * Wird emittiert wenn der Programmatic-Executor-BC eine neue PageSession
 * initialisiert (z.B. durch MCP navigate-Tool oder Scrapling-Substrate-Boot).
 */
export interface SessionStarted {
  type: "session_started";
  page_session_id: string;
  dns_domain: string;
  started_at_monotonic_ns: number;
}
/**
 * Daemon→Tab: die PageSession hat eine Navigation vollzogen.
 *
 * Emittiert nach jeder erfolgreichen Navigation (including forward/back).
 * dom_snapshot_hash ermöglicht dem Frontend Stale-DOM-Detection.
 */
export interface PageNavigated {
  type: "page_navigated";
  page_session_id: string;
  url: string;
  dom_snapshot_hash: string;
  navigated_at_monotonic_ns: number;
}
/**
 * Daemon→Tab: ein Pick wurde vom Interactive-Surface-BC akzeptiert.
 *
 * Der Daemon bestätigt dem Tab, dass der PickRequested-Mutation verarbeitet
 * wurde und der Pick persistiert ist.
 */
export interface PickAcknowledged {
  type: "pick_acknowledged";
  pick_id: string;
  pointing_session_id: string;
  acknowledged_at_monotonic_ns: number;
}
/**
 * Daemon→Tab: ein AnnotationDraft wurde vom Daemon persistiert.
 *
 * Der Daemon bestätigt dem Tab, dass der AnnotationDraftSubmitted-Mutation
 * verarbeitet und die Annotation im PointingSession-Aggregate gespeichert ist.
 */
export interface AnnotationPersisted {
  type: "annotation_persisted";
  annotation_id: string;
  pointing_session_id: string;
  persisted_at_monotonic_ns: number;
}

export const SessionStarted = z.object({
  type: z.literal("session_started"),
  page_session_id: z.string(),
  dns_domain: z.string(),
  started_at_monotonic_ns: z.number().int(),
});

export const PageNavigated = z.object({
  type: z.literal("page_navigated"),
  page_session_id: z.string(),
  url: z.string(),
  dom_snapshot_hash: z.string(),
  navigated_at_monotonic_ns: z.number().int(),
});

export const PickAcknowledged = z.object({
  type: z.literal("pick_acknowledged"),
  pick_id: z.string(),
  pointing_session_id: z.string(),
  acknowledged_at_monotonic_ns: z.number().int(),
});

export const AnnotationPersisted = z.object({
  type: z.literal("annotation_persisted"),
  annotation_id: z.string(),
  pointing_session_id: z.string(),
  persisted_at_monotonic_ns: z.number().int(),
});

export const EventEnvelope = z.object({
  schema_version: z.literal(1),
  daemon_id: z.string(),
  emitted_at_monotonic_ns: z.number().int(),
  payload: z.discriminatedUnion("type", [SessionStarted, PageNavigated, PickAcknowledged, AnnotationPersisted]),
});

/**
 * Äußerer Container für alle Tab→Daemon Wire-Mutations (Channel 3).
 *
 * Enthält Empfangs-Metadaten (`schema_version`, `received_at_monotonic_ns`)
 * plus den discriminated-union `payload`.
 *
 * Kein `daemon_id` hier — der Daemon empfängt die Mutation (er sendet sie
 * nicht). `received_at_monotonic_ns` wird vom HTTP-Endpoint beim
 * Deserialisieren gesetzt (Aufgabe des Endpoints, nicht des Envelope-Models).
 *
 * Wire-Deserialisierung: `MutationEnvelope.model_validate(raw_dict)`.
 */
export interface MutationEnvelope {
  schema_version: 1;
  received_at_monotonic_ns: number;
  payload: PickRequested | AnnotationDraftSubmitted;
}
/**
 * Tab→Daemon: Tab fordert einen Pick-Vorgang vom Daemon an.
 *
 * Der Daemon startet daraufhin den interaktiven Pick-Prozess:
 * eine neue Pick-Entity im PointingSession-Aggregate anlegen,
 * DOM-Capture via Scrapling triggern.
 */
export interface PickRequested {
  type: "pick_requested";
  pointing_session_id: string;
  selector: string;
  score: string;
  idempotency_key: string;
}
/**
 * Tab→Daemon: Tab reicht einen Annotations-Draft ein.
 *
 * Der Daemon validiert via ACL, persistiert die Annotation
 * im PointingSession-Aggregate, und emittiert AnnotationPersisted.
 *
 * Optionale dehydrated IDs (dehydrierte Identifier-Felder):
 * Alle None wenn der Tab keine Programmatic-Executor-Informationen hatte.
 */
export interface AnnotationDraftSubmitted {
  type: "annotation_draft_submitted";
  pointing_session_id: string;
  content: string;
  idempotency_key: string;
  page_session_id?: string | null;
  interaction_flow_step_id?: string | null;
  dom_snapshot_hash?: string | null;
}

export const PickRequested = z.object({
  type: z.literal("pick_requested"),
  pointing_session_id: z.string(),
  selector: z.string(),
  score: z.string(),
  idempotency_key: z.string(),
});

export const AnnotationDraftSubmitted = z.object({
  type: z.literal("annotation_draft_submitted"),
  pointing_session_id: z.string(),
  content: z.string(),
  idempotency_key: z.string(),
  page_session_id: z.string().nullable().optional().default(null),
  interaction_flow_step_id: z.string().nullable().optional().default(null),
  dom_snapshot_hash: z.string().nullable().optional().default(null),
});

export const MutationEnvelope = z.object({
  schema_version: z.literal(1),
  received_at_monotonic_ns: z.number().int(),
  payload: z.discriminatedUnion("type", [PickRequested, AnnotationDraftSubmitted]),
});

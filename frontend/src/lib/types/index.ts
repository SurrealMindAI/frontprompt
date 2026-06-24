/**
 * Domain-Identifier — Branded-Types (Mandatory Domain-Prefix).
 *
 * Platzhalter für die spätere pydantic-zod-codegen-Ausgabe. Wenn das
 * generierte Wire-Protocol live ist, werden diese Typen durch
 * generierte Zod-Schemas ersetzt. Bis dahin sind sie manuell definiert
 * und strukturell identisch mit dem Brand<K,T>-Pattern.
 *
 * Domain-Prefix-Regel: KEIN bare `id`, KEIN bare `session`, KEIN bare `domain`.
 * Jeder Identifier trägt seinen Domain-Qualifier im Typnamen.
 *
 * Constructor-Funktionen (pageSessionId, pointingSessionId, ...) sind für
 * Test-/Dev-Code gedacht. Produktions-Code empfängt validierte IDs vom
 * Server-Response und castet via `as PageSessionId` nach Zod-Parse.
 */

// `declare const __brand: unique symbol` ist mit verbatimModuleSyntax: true
// safe — der Symbol wird nicht re-exportiert, nur als Typ-Key in Brand<K,T> genutzt.
declare const __brand: unique symbol;

/** Interne Brand-Helfer-Typ. Nicht direkt verwenden. */
type Brand<K, T> = K & { readonly [__brand]: T };

/** ULID einer PageSession (Programmatic-Executor-BC). */
export type PageSessionId = Brand<string, 'PageSessionId'>;

/** ULID einer PointingSession (Interactive-Surface-BC). */
export type PointingSessionId = Brand<string, 'PointingSessionId'>;

/** ULID eines Picks innerhalb einer PointingSession. */
export type PickId = Brand<string, 'PickId'>;

/** ULID einer Annotation (Ergebnis eines abgeschlossenen Picks). */
export type AnnotationId = Brand<string, 'AnnotationId'>;

/** Identifier des laufenden Frontprompt-Daemon-Prozesses. */
export type DaemonId = Brand<string, 'DaemonId'>;

/** Idempotency-Key für HTTP-POST-Requests. */
export type IdempotencyKey = Brand<string, 'IdempotencyKey'>;

// ---------------------------------------------------------------------------
// Constructor-Funktionen für Test- und Dev-Code
// ---------------------------------------------------------------------------
// Produktions-Code sollte `as PageSessionId` nach validiertem Zod-Parse nutzen,
// nicht diese Funktionen — sie umgehen Typ-Safety bewusst für Fixtures.

/** Erstellt einen PageSessionId aus einem rohen String (nur Test/Dev). */
export const pageSessionId = (s: string): PageSessionId => s as PageSessionId;

/** Erstellt einen PointingSessionId aus einem rohen String (nur Test/Dev). */
export const pointingSessionId = (s: string): PointingSessionId => s as PointingSessionId;

/** Erstellt einen PickId aus einem rohen String (nur Test/Dev). */
export const pickId = (s: string): PickId => s as PickId;

/** Erstellt einen AnnotationId aus einem rohen String (nur Test/Dev). */
export const annotationId = (s: string): AnnotationId => s as AnnotationId;

/** Erstellt einen DaemonId aus einem rohen String (nur Test/Dev). */
export const daemonId = (s: string): DaemonId => s as DaemonId;

/** Erstellt einen IdempotencyKey aus einem rohen String (nur Test/Dev). */
export const idempotencyKey = (s: string): IdempotencyKey => s as IdempotencyKey;

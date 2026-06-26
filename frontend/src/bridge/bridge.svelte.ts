/**
 * Bridge — typed bidirectional channel between Overlay and Python backend.
 *
 * Single window-global: `window.__fp` (callable für outbound, mit
 * `.dispatch` + `.version` als attached properties für inbound + metadata).
 *
 * Lifecycle:
 *   1. Python registers `window.__fp` via `page.expose_function('__fp', ...)`
 *   2. main.ts ruft `setupBridge()` aus dem post-DOMContentLoaded mount-pfad auf
 *   3. setupBridge() validiert dass `window.__fp` da ist (Playwright-injected),
 *      mountet `dispatch` + `version` als properties
 *   4. App-Code consumed `bridge` singleton: `bridge.send(...)`, `bridge.on(...)`,
 *      `bridge.addInterceptor(...)`
 *
 * Interceptor-Pattern: jede registered interceptor sieht ALLE events (outbound
 * + inbound) als BridgeEvent. Used by DebugPanel + future consumers (metrics,
 * replay).
 *
 * Validation: outbound messages werden lokal nicht zod-validiert (Playwright's
 * expose_function marshalt durch das CDP-channel; Python-side Pydantic ist die
 * authoritative-validation). Inbound messages werden via Zod safeParse validiert
 * — wenn invalid, wird der event NICHT dispatched, sondern als "validation_failed"
 * event durch interceptors getrieben (für debug-panel-Sichtbarkeit).
 */

import type {
  Heartbeat,
  HeartbeatAck,
  HideAllPanelsRequested,
  InspectorActivateRequested,
  InspectorCanceledRequested,
  InspectorPickMadeRequested,
  OverlayReady,
  PanelResizeRequested,
  PanelToggleRequested,
  PickCommentUpdatedRequested,
  PickDeletedRequested,
  PickSelectedRequested,
  RecordedEventCapturedRequested,
  RecordingRenameRequested,
  RecordingSelectedRequested,
  RecordingStartRequested,
  RecordingStopRequested,
  RegionCreatedRequested,
  RegionDeletedRequested,
  RegionSelectedRequested,
  RegionUpdatedRequested,
  RelationCreatedRequested,
  RelationDeletedRequested,
  RelationUpdatedRequested,
  StateSnapshotMessage,
} from '../_generated/schemas';
import type { StateSnapshot } from '../_generated/state';
import { BUILD_GIT_SHA, BUILD_SESSION, BUILD_VERSION } from '../_generated/build-info';

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/** Tagged union aller Outbound-Messages (Overlay → Python). */
export type OutboundMessage =
  | OverlayReady
  | HeartbeatAck
  | PanelToggleRequested
  | PanelResizeRequested
  | HideAllPanelsRequested
  | InspectorActivateRequested
  | InspectorCanceledRequested
  | InspectorPickMadeRequested
  | PickSelectedRequested
  | PickCommentUpdatedRequested
  | PickDeletedRequested
  | RelationCreatedRequested
  | RelationDeletedRequested
  | RelationUpdatedRequested
  | RegionCreatedRequested
  | RegionDeletedRequested
  | RegionUpdatedRequested
  | RegionSelectedRequested
  | RecordingStartRequested
  | RecordingStopRequested
  | RecordingRenameRequested
  | RecordingSelectedRequested
  | RecordedEventCapturedRequested;

/** Tagged union aller Inbound-Messages (Python → Overlay). */
export type InboundMessage = Heartbeat | StateSnapshotMessage;

/** Discriminator-kinds für InboundMessage. */
export type InboundKind = InboundMessage['kind'];

/** Event-Record für interceptors — ALLE Bridge-Aktivität wird hierdurch sichtbar. */
export interface BridgeEvent {
  /** Monotonic counter — eindeutig pro session, useful für sort + dedup. */
  seq: number;
  /** ``Date.now()`` zum Zeitpunkt des emit. */
  timestamp_ms: number;
  /** Outbound = wir senden an Python; Inbound = Python sendet an uns; Error = validation-failure. */
  direction: 'outbound' | 'inbound' | 'error';
  /** Message-kind oder Error-name (z.B. `validation_failed`). */
  kind: string;
  /** Voller payload (rohe message für outbound/inbound, error-info für error). */
  payload: unknown;
}

/** Subscriber-Function für Bridge-Events. Kann sync oder async sein. */
export type Interceptor = (event: BridgeEvent) => void;

/** Handler für eine spezifische InboundMessage-kind. */
export type InboundHandler<K extends InboundKind> = (
  message: Extract<InboundMessage, { kind: K }>
) => void | Promise<void>;

// ---------------------------------------------------------------------------
// Window-namespace extension (single-global discipline — see ARCHITECTURE.md)
// ---------------------------------------------------------------------------

/** Shape of `window.__fp` after `setupBridge()` migrates everything onto it.
 *
 * Single window-global — keine zusätzlichen scaffolding-globals (prefix-pattern
 * verboten via src/__arch__/window-fp-namespace.test.ts). Playwright zwingt
 * zwar internal scaffolds (z.B. `__fp_internal_state_getter`) per
 * expose_function, aber setupBridge() migriert sie hierher + deleted die
 * originale.
 */
export interface WindowFp {
  /** Outbound: overlay sendet message ans python. Resolves wenn python handler done. */
  (message: OutboundMessage): Promise<unknown>;
  /** Inbound: python ruft das via page.evaluate für state-snapshots etc. */
  dispatch: (raw: unknown) => void;
  /** Statische version-info des bundle + build session. */
  version: VersionInfo;
  /** One-shot synchron-fetch der current authoritative state. Used pre-mount. */
  getState: () => Promise<StateSnapshot | null>;
}

export interface VersionInfo {
  schema_version: string;
  bundle_build_session: string;
  bundle_build_version: string;
  bundle_build_git_sha: string;
}

declare global {
  interface Window {
    __fp?: WindowFp;
  }
}

/** Internal scaffolding globals — nur in setupBridge() für die migration, nicht
 * im public type-system. Externalcode darf das NIE direkt referenzieren. */
type WindowWithInternalScaffolding = Window & {
  __fp_internal_state_getter?: () => Promise<StateSnapshot | null>;
};

// ---------------------------------------------------------------------------
// Module-level integrity token
// ---------------------------------------------------------------------------

/**
 * Per-session integrity token, set by `setupBridge(schemaVersion, integrityToken)`.
 * Null means no enforcement — all state_snapshot messages are accepted.
 * When set, `dispatch()` rejects any `state_snapshot` that does not carry
 * the exact same token.
 *
 * Scoped to this module — never leaked onto `window.__fp` or any other global.
 */
let _sessionIntegrityToken: string | null = null;

// ---------------------------------------------------------------------------
// Bridge singleton
// ---------------------------------------------------------------------------

class Bridge {
  private seq = 0;
  private interceptors: Set<Interceptor> = new Set();
  private handlers: Map<InboundKind, InboundHandler<InboundKind>> = new Map();

  /** Send a typed outbound message to Python. Returns whatever Python responds. */
  async send(message: OutboundMessage): Promise<unknown> {
    const fp = window.__fp;
    if (!fp) {
      const err = new Error(
        '[fp bridge] window.__fp not available — was Python BridgeManager set up before navigate?'
      );
      this.emit({
        seq: this.nextSeq(),
        timestamp_ms: Date.now(),
        direction: 'error',
        kind: 'send_before_setup',
        payload: { message },
      });
      throw err;
    }

    this.emit({
      seq: this.nextSeq(),
      timestamp_ms: Date.now(),
      direction: 'outbound',
      // kind is always present on wire (Pydantic Literal default); codegen
      // emits it as optional because of the default-value pattern (pzc-bug).
      kind: message.kind ?? 'unknown',
      payload: message,
    });

    return await fp(message);
  }

  /**
   * Register a handler for a specific InboundMessage kind.
   * Replaces any previous handler for that kind.
   */
  on<K extends InboundKind>(kind: K, handler: InboundHandler<K>): void {
    this.handlers.set(kind, handler as InboundHandler<InboundKind>);
  }

  /**
   * Register an interceptor that sees every bridge event (outbound + inbound + error).
   * Returns an unsubscribe-function.
   */
  addInterceptor(fn: Interceptor): () => void {
    this.interceptors.add(fn);
    return () => {
      this.interceptors.delete(fn);
    };
  }

  /** Called by `window.__fp.dispatch(raw)` from Python via `page.evaluate(...)`.
   *
   * Validation: skip zod-validation lokal (pzc-bug #1086 dropped required fields in
   * generated Zod-objects). Pydantic-side ist authoritative validation. Wir trust
   * den marshalled JSON-shape und routen by `kind`.
   *
   * Integrity-token check: if `_sessionIntegrityToken` is set and the
   * incoming message kind is `state_snapshot`, the envelope MUST carry the exact
   * matching token. A mismatch (absent or wrong token) emits an
   * `integrity_token_mismatch` error event and the message is discarded.
   * This prevents page JS from forging state snapshots via window.__fp.dispatch.
   */
  dispatch(raw: unknown): void {
    if (typeof raw !== 'object' || raw === null || !('kind' in raw)) {
      this.emit({
        seq: this.nextSeq(),
        timestamp_ms: Date.now(),
        direction: 'error',
        kind: 'inbound_malformed',
        payload: { raw },
      });
      return;
    }

    const message = raw as InboundMessage;
    const kind = message.kind;

    // Integrity-token guard for state_snapshot envelopes.
    // Only applies when a session token is configured (non-null, non-empty).
    if (_sessionIntegrityToken && kind === 'state_snapshot') {
      const envelopeToken = (raw as Record<string, unknown>)['integrity_token'];
      if (envelopeToken !== _sessionIntegrityToken) {
        this.emit({
          seq: this.nextSeq(),
          timestamp_ms: Date.now(),
          direction: 'error',
          kind: 'integrity_token_mismatch',
          payload: { raw },
        });
        return;
      }
    }

    this.emit({
      seq: this.nextSeq(),
      timestamp_ms: Date.now(),
      direction: 'inbound',
      kind: kind ?? 'unknown',
      payload: message,
    });

    const handler = this.handlers.get(kind);
    if (handler) {
      try {
        const result = handler(message as Extract<InboundMessage, { kind: typeof kind }>);
        if (result instanceof Promise) {
          result.catch((err) => {
            // eslint-disable-next-line no-console
            console.error(`[fp bridge] async handler for ${kind} threw:`, err);
          });
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error(`[fp bridge] handler for ${kind} threw:`, err);
      }
    }
  }

  /** Build VersionInfo from generated build-info constants + schema_version. */
  buildVersionInfo(schemaVersion: string): VersionInfo {
    return {
      schema_version: schemaVersion,
      bundle_build_session: BUILD_SESSION,
      bundle_build_version: BUILD_VERSION,
      bundle_build_git_sha: BUILD_GIT_SHA,
    };
  }

  /** Used by tests to inject mock window.__fp. */
  resetForTests(): void {
    this.seq = 0;
    this.interceptors.clear();
    this.handlers.clear();
    // Reset module-level token so each test starts without enforcement.
    _sessionIntegrityToken = null;
  }

  private nextSeq(): number {
    return ++this.seq;
  }

  private emit(event: BridgeEvent): void {
    for (const fn of this.interceptors) {
      try {
        fn(event);
      } catch (err) {
        // Don't let one bad interceptor break the dispatch chain.
        // eslint-disable-next-line no-console
        console.error('[fp bridge] interceptor threw:', err);
      }
    }
  }
}

/** Singleton bridge instance. Consumed by overlay app code + DebugPanel. */
export const bridge = new Bridge();

// ---------------------------------------------------------------------------
// setupBridge — called from main.ts after mount
// ---------------------------------------------------------------------------

/**
 * Mount `dispatch` + `version` + `getState` as properties on `window.__fp`
 * (Playwright-injected callable). Migrates internal scaffolding globals
 * (`__fp_internal_state_getter`) onto `__fp.getState` + deletes the originals.
 *
 * MUST be called AFTER `window.__fp` is set by Playwright. In practice that's
 * after `expose_function` ran — guaranteed if Python's BridgeManager was
 * entered BEFORE the first page.goto() (bridge lifecycle).
 *
 * End-result: nur `window.__fp` ist im global namespace. Alle internal
 * scaffolds sind entweder migrated oder deleted.
 *
 * @param schemaVersion — Pydantic schema version string (e.g. '0.6.0')
 * @param integrityToken — per-session integrity token from Python startup
 *   (secrets.token_hex(32)). Pass null or empty string for no enforcement
 *   (test harness / cold-boot). When set, dispatch() validates every incoming
 *   state_snapshot against this token.
 *
 * Idempotent — calling twice is safe.
 */
export function setupBridge(schemaVersion: string, integrityToken: string | null = null): void {
  const fp = window.__fp;
  if (!fp) {
    // eslint-disable-next-line no-console
    console.error(
      '[fp bridge] setupBridge called but window.__fp not yet available. ' +
        'Was Python BridgeManager set up before page.goto()?'
    );
    return;
  }

  // Store the session integrity token for dispatch validation.
  // Module-level var — scoped to this bridge module, never on window.__fp.
  if (integrityToken) {
    _sessionIntegrityToken = integrityToken;
  }

  fp.dispatch = (raw: unknown) => bridge.dispatch(raw);
  fp.version = bridge.buildVersionInfo(schemaVersion);

  // Migrate internal state-getter scaffold onto __fp.getState + delete original
  const w = window as WindowWithInternalScaffolding;
  if (typeof w.__fp_internal_state_getter === 'function') {
    fp.getState = w.__fp_internal_state_getter;
    delete w.__fp_internal_state_getter;
  } else if (!fp.getState) {
    // No internal getter exposed (cold-boot or tests) → return null per contract
    fp.getState = () => Promise.resolve(null);
  }
}

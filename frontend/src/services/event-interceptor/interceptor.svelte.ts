/**
 * EventInterceptor — diagnostic capture-phase tap auf key event types.
 *
 * Lebt als svelte5-$state-singleton. Listens am ``window`` mit ``capture: true``,
 * läuft also BEVOR jeder page-handler den event sieht. Per event:
 *   - target (tag#id.class — kurzer descriptor)
 *   - default_prevented BEFORE wir es sehen (= jemand hat in einem
 *     früheren capture-listener oder synchronously davor prevented)
 *   - in_fp_overlay flag (war's unsere HUD oder die echte page?)
 *   - type-specific fields (wheel deltas, scroll-y, keyboard key)
 *
 * Use-cases:
 *   - "warum scrollt die page nicht?" → wheel-events sehen, ihre defaultPrevented-
 *     state, ob ein scroll-event danach feuert oder nicht
 *   - "ist user click bei uns angekommen?" → click events mit target
 *   - "wie viele elemente hat die page?" → element-registry via MutationObserver
 *
 * Phase 1: read-only diagnostics, kein flow-modify. Phase 2 könnte aktiv
 * intervenieren (z.B. wheel preventDefault + manual forward).
 *
 * Memory: FIFO cap auf 500 events. Bei 60Hz wheel = ~8s buffer. Reicht für
 * "was war vorhin" debugging.
 */

import { backendState } from '../../backend-state/backend-state.svelte';
import { bridge } from '../../bridge/bridge.svelte';
import type { PageEventEntry } from '../../_generated/state';

const EVENT_TYPES = ['wheel', 'scroll', 'click', 'pointerdown', 'keydown'] as const;
export type InterceptedEventType = (typeof EVENT_TYPES)[number];

export interface InterceptedEvent {
  /** Monotonic sequence — sortable + dedupe-key. */
  seq: number;
  /** Date.now() zum Zeitpunkt der capture. */
  timestamp_ms: number;
  type: InterceptedEventType;
  /** ``tag#id.class.class`` — kurzer descriptor des deepest element in composedPath. */
  target: string;
  /**
   * DOM-ancestor-tags vom dokument-root → deepest target element (lowercase).
   * Matched für pick-filtering: pick.fingerprint.path ⊑ target_path bedeutet
   * der event happened ON OR INSIDE einer pick-Element-subtree. False-positives
   * möglich bei tag-only-paths (mehrere geschwister-divs sind ununterscheidbar);
   * user kann den filter abschalten wenn nötig.
   *
   * Excludes alles innerhalb der fp-overlay shadow-tree (HUD-noise raus aus
   * dem path um cross-matches mit page-elements zu vermeiden).
   */
  target_path: string[];
  /**
   * True wenn ANY ancestor in composedPath ist ``<fp-overlay>`` oder dessen
   * shadow-tree-descendant.
   *
   * NOTE: composedPath() crosst shadow-boundaries — daher sehen wir auch
   * elements INSIDE shadow root. event.target dagegen ist beim capture-phase
   * AUSSERHALB shadow retargeted auf den host (= fp-overlay element itself).
   */
  in_fp_overlay: boolean;
  /**
   * True wenn target innerhalb der InspectorLayer (``.inspector-layer``).
   * Semantik: technisch IST das in fp-overlay, aber **konzeptuell** ist die
   * inspector-layer ein passthrough für user-intent zur Page (z.B. wheel-
   * forwarding, clicks auf page-elements). Filter behandelt sie nicht als
   * HUD-noise.
   */
  in_inspector_layer: boolean;
  /** ``e.defaultPrevented`` zum Zeitpunkt unserer capture (= jemand davor hat preventDefault'd). */
  default_prevented: boolean;
  /** Nur für ``wheel``. */
  delta_x?: number;
  delta_y?: number;
  /** Nur für ``scroll`` — wo das scroll-target jetzt steht. */
  scroll_y?: number;
  /** Nur für ``keydown``. */
  key?: string;
}

/**
 * "HUD chrome" = events targeting unsere toolbar/panels (NICHT inspector-layer).
 * Default-filter im UI versteckt diese; inspector-layer-events bleiben sichtbar
 * weil sie user-intent zur Page repräsentieren.
 */
export function isHudChrome(e: InterceptedEvent): boolean {
  return e.in_fp_overlay && !e.in_inspector_layer;
}

/**
 * Check ob ein Event ein bestimmtes Pick-Element trifft (oder einen Descendant
 * davon). Path-prefix-match: ``pick.fingerprint.path ⊑ event.target_path``.
 *
 * False-positives möglich bei tag-only-paths (mehrere geschwister-divs sind
 * ununterscheidbar). Phase-2-Erweiterung: zusätzlich attribute/fingerprint-
 * hash-matching. Phase 1 KISS: user kann den filter abschalten wenn nötig.
 */
export function eventMatchesPickPath(
  event: InterceptedEvent,
  pickPath: readonly string[]
): boolean {
  if (pickPath.length === 0 || event.target_path.length === 0) return false;
  if (pickPath.length > event.target_path.length) return false;
  return pickPath.every((tag, i) => event.target_path[i] === tag);
}

const SCHEMA_VERSION = '0.8.0';

/**
 * Build a PageEventEntry payload from an InterceptedEvent for bridge forwarding.
 * seq is intentionally 0 — Python stamps seq atomically at append time (reviewer Q1).
 * Only called for click/pointerdown/keydown events (wheel/scroll are excluded by caller).
 */
function buildPageEventEntry(record: InterceptedEvent): PageEventEntry {
  return {
    kind: 'page_event',
    seq: 0, // Python-stamped
    timestamp_ms: record.timestamp_ms,
    event_type: record.type as 'click' | 'pointerdown' | 'keydown',
    target: record.target,
    target_path: record.target_path,
    default_prevented: record.default_prevented,
    key: record.key ?? null,
  };
}

const MAX_EVENTS = 500;

class EventInterceptor {
  events = $state<InterceptedEvent[]>([]);
  enabled = $state(true);
  elementsSeen = $state(0);
  elementsWithEvents = $state(0);

  /** Per type counter — survives clear(). Useful für "wie viel wheel passiert insgesamt". */
  countsByType = $state<Record<InterceptedEventType, number>>({
    wheel: 0,
    scroll: 0,
    click: 0,
    pointerdown: 0,
    keydown: 0,
  });

  private firedElements = new WeakSet<Element>();
  private seq = 0;
  private observer: MutationObserver | null = null;
  private listenerCleanups: Array<() => void> = [];
  private installed = false;

  /** Idempotent: kann mehrfach aufgerufen werden, installiert nur einmal. */
  start(): void {
    if (this.installed) return;
    this.installed = true;

    for (const type of EVENT_TYPES) {
      const handler = (e: Event): void => this._onEvent(type, e);
      window.addEventListener(type, handler, { capture: true, passive: true });
      this.listenerCleanups.push(() =>
        window.removeEventListener(type, handler, { capture: true })
      );
    }

    this._scanInitialDom();
    this.observer = new MutationObserver((records) => {
      for (const r of records) {
        for (const node of r.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            this._registerElementSubtree(node as Element);
          }
        }
      }
    });
    this.observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
    });
  }

  /** Voll-cleanup — listeners + observer. Für tests + hot-reload. */
  stop(): void {
    for (const off of this.listenerCleanups) off();
    this.listenerCleanups = [];
    this.observer?.disconnect();
    this.observer = null;
    this.installed = false;
  }

  /** UI-action: pause/resume capture (listeners bleiben dran, nur recording stoppt). */
  toggle(): void {
    this.enabled = !this.enabled;
  }

  /** UI-action: clear FIFO buffer. countsByType + elementsSeen bleiben. */
  clear(): void {
    this.events = [];
    // seq NICHT resetten — globally monotonic für ordering across clears
  }

  // ----- internal ---------------------------------------------------------

  private _scanInitialDom(): void {
    let n = 0;
    const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_ELEMENT);
    while (walker.nextNode()) n++;
    // include documentElement itself
    n += 1;
    this.elementsSeen = n;
  }

  private _registerElementSubtree(el: Element): void {
    let n = 1; // el itself
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_ELEMENT);
    while (walker.nextNode()) n++;
    this.elementsSeen += n;
  }

  private _onEvent(type: InterceptedEventType, e: Event): void {
    this.countsByType[type] += 1;
    if (!this.enabled) return;

    // composedPath() crosst shadow-boundaries — wir sehen den FULL path
    // inkl. elements inside <fp-overlay>'s shadow root. event.target dagegen
    // ist beim capture-OUTSIDE-shadow retargeted auf den host. Composed-path
    // gibt uns die wirkliche Quelle des events.
    const path = (typeof e.composedPath === 'function' ? e.composedPath() : []) as EventTarget[];

    let inFpOverlay = false;
    let inInspectorLayer = false;
    let deepestEl: Element | null = null;
    // path-stack: composedPath() ist deepest → root, wir wollen root → deepest
    // damit der path-prefix-match in EventsTab funktioniert (pick.path is
    // ebenfalls root → element). Stop sobald wir fp-overlay erreichen — alles
    // ÜBER der fp-overlay-grenze ist HUD-internal und nicht für pick-matching.
    const pathTags: string[] = [];

    for (const node of path) {
      if (node instanceof Element) {
        if (!deepestEl) deepestEl = node;
        if (node.tagName === 'FP-OVERLAY') {
          inFpOverlay = true;
          break;
        }
        if (node.classList?.contains('inspector-layer')) inInspectorLayer = true;
        pathTags.push(node.tagName.toLowerCase());
      }
    }
    pathTags.reverse();

    // Fallback wenn composedPath leer (sollte nie passieren in modernen browsern)
    if (!deepestEl) {
      deepestEl = e.target instanceof Element ? e.target : null;
      if (deepestEl && !inFpOverlay) {
        inFpOverlay = !!deepestEl.closest?.('fp-overlay');
      }
    }

    // elementsWithEvents trackt nur "user-intent-to-page" elements:
    // - echte page-elements (nicht in fp-overlay)
    // - inspector-layer events (= user trying to interact with page through us)
    // NICHT: toolbar/panels (hud-chrome) — das ist UI-noise
    const isUserIntent = !inFpOverlay || inInspectorLayer;
    if (deepestEl && isUserIntent) {
      if (!this.firedElements.has(deepestEl)) {
        this.firedElements.add(deepestEl);
        this.elementsWithEvents += 1;
      }
    }

    const record: InterceptedEvent = {
      seq: this.seq++,
      timestamp_ms: Date.now(),
      type,
      target: deepestEl ? _describeElement(deepestEl) : '(null)',
      target_path: pathTags,
      in_fp_overlay: inFpOverlay,
      in_inspector_layer: inInspectorLayer,
      default_prevented: e.defaultPrevented,
    };

    if (e instanceof WheelEvent) {
      record.delta_x = e.deltaX;
      record.delta_y = e.deltaY;
    }
    if (type === 'scroll') {
      record.scroll_y = window.scrollY;
    }
    if (e instanceof KeyboardEvent) {
      record.key = e.key;
    }

    // Recording forwarding (sub-plan 04): fire-and-forget bridge.send for qualifying events.
    // Guard: recording active + non-HUD-chrome + not wheel/scroll.
    // passive:true listener contract — void the send, no await (non-blocking).
    const activeRecordingId = backendState.recordings.activeRecordingId;
    if (
      activeRecordingId !== null &&
      !isHudChrome(record) &&
      type !== 'wheel' &&
      type !== 'scroll'
    ) {
      void bridge.send({
        kind: 'recorded_event_captured_requested',
        schema_version: SCHEMA_VERSION,
        recording_id: activeRecordingId,
        entry: buildPageEventEntry(record),
      });
    }

    // FIFO push mit cap
    const next =
      this.events.length >= MAX_EVENTS
        ? [...this.events.slice(this.events.length - (MAX_EVENTS - 1)), record]
        : [...this.events, record];
    this.events = next;
  }
}

function _describeElement(el: Element): string {
  const tag = el.tagName.toLowerCase();
  const id = el.id ? `#${el.id}` : '';
  const cls = el.classList.length > 0 ? `.${[...el.classList].slice(0, 2).join('.')}` : '';
  return `${tag}${id}${cls}`;
}

export const eventInterceptor = new EventInterceptor();

/**
 * interaction-blockers monitor.
 *
 * Detects page-level mechanisms blocking interaction with our overlay:
 *   - ``inert`` attribute on ancestors (HTML spec: makes whole subtree non-interactive)
 *   - ``aria-hidden="true"`` on ancestors (a11y-hiding)
 *   - focus theft (focus moves OUT of our overlay while we expected to keep it)
 *
 * Service is intent-neutral — page might block us for legit reasons (modal,
 * loading overlay) or unintentionally. We just observe + report.
 *
 * See README.md im service-dir für volle erklärung der signals + warum jeder
 * relevant ist.
 *
 * Lifecycle: ``startInteractionBlockersMonitor(host)`` installs periodic check
 * (every 2s) + focusin listener (capture-phase). Never explicit stop — lives
 * for page lifetime. Single interval + single listener — vernachlässigbarer
 * overhead.
 *
 * Logs only fire WHEN state changes since last check. Initial state = full
 * snapshot. Format: ``console.warn('[fp interaction-blockers]', {...})``.
 */

const LOG_PREFIX = '[fp interaction-blockers]';
const SNAPSHOT_INTERVAL_MS = 2000;

/**
 * One frame of detection-state. Compared field-by-field via JSON.stringify
 * for "did anything change since last frame".
 */
interface BlockerSnapshot {
  /** Ancestors of our host that have ``inert=true``. Empty wenn keine. */
  inertAncestors: string[];
  /** Ancestors mit ``aria-hidden="true"``. Empty wenn keine. */
  ariaHiddenAncestors: string[];
  /** Tag-descriptor des document.activeElement zum snapshot-zeitpunkt. */
  activeElementTag: string;
}

interface MonitorReport extends BlockerSnapshot {
  /** Count von focus-events die OUT-of-overlay gingen seit letztem report. */
  focusStolenEventsSinceLast: number;
  /** ISO timestamp des reports. */
  ts: string;
}

/**
 * Start monitoring + return cleanup-function. Idempotent NICHT — wenn mehrmals
 * gestartet, doppelte intervals/listeners. Caller ist für single-start
 * verantwortlich (typically main.ts).
 */
export function startInteractionBlockersMonitor(host: HTMLElement): () => void {
  let focusStolenEventsSinceLast = 0;
  let lastSnapshot: BlockerSnapshot | null = null;

  function snapshot(): void {
    const current = _collectSnapshot(host);
    const changed =
      lastSnapshot === null ||
      JSON.stringify(lastSnapshot) !== JSON.stringify(current) ||
      focusStolenEventsSinceLast > 0;

    if (changed) {
      const report: MonitorReport = {
        ...current,
        focusStolenEventsSinceLast,
        ts: new Date().toISOString(),
      };
      // eslint-disable-next-line no-console
      console.warn(LOG_PREFIX, report);
      lastSnapshot = current;
      focusStolenEventsSinceLast = 0;
    }
  }

  // Initial snapshot direkt nach mount
  snapshot();

  const intervalHandle = setInterval(snapshot, SNAPSHOT_INTERVAL_MS);

  function onFocusIn(e: FocusEvent): void {
    const target = e.target as Node | null;
    if (target && !host.contains(target)) {
      focusStolenEventsSinceLast += 1;
    }
  }
  document.addEventListener('focusin', onFocusIn, { capture: true });

  return () => {
    clearInterval(intervalHandle);
    document.removeEventListener('focusin', onFocusIn, { capture: true });
  };
}

// ---------------------------------------------------------------------------
// Internal: snapshot-collection logic
// ---------------------------------------------------------------------------

function _collectSnapshot(host: HTMLElement): BlockerSnapshot {
  const inertAncestors: string[] = [];
  const ariaHiddenAncestors: string[] = [];

  let node: Element | null = host;
  while (node) {
    // ``inert`` ist eine reflected HTMLElement-property — direkt boolean.
    if ((node as HTMLElement).inert) {
      inertAncestors.push(_describeElement(node));
    }
    if (node.getAttribute('aria-hidden') === 'true') {
      ariaHiddenAncestors.push(_describeElement(node));
    }
    node = node.parentElement;
  }

  const active = document.activeElement;
  const activeElementTag = active ? _describeElement(active) : 'null';

  return { inertAncestors, ariaHiddenAncestors, activeElementTag };
}

/** ``tag#id.class.class`` — kurzer descriptor des elements für log-output. */
function _describeElement(el: Element): string {
  const tag = el.tagName.toLowerCase();
  const id = el.id ? `#${el.id}` : '';
  const cls = el.classList.length > 0 ? `.${[...el.classList].slice(0, 2).join('.')}` : '';
  return `${tag}${id}${cls}`;
}

/**
 * localState — Umbrella-Singleton für alle local-only state stores.
 *
 * Stores in :mod:`local-state/*` werden hier zugefügt + via
 * ``localState.<store>`` consumed.
 *
 * Niemand in `local-state/` importiert die bridge ODER sendet wire-messages —
 * hard contract. Wenn ein state cross-navigation überleben muss, gehört es in
 * :mod:`backend-state/`.
 */

import { BridgeLog } from './bridge-log.svelte';

class LocalState {
  bridgeLog = new BridgeLog();
  // future: dragState, hoverState, animationProgress
}

export const localState = new LocalState();

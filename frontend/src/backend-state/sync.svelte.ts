/**
 * sync — registriert Bridge-Handler die StateSnapshots routen zu backendState.
 *
 * EINZIGES module in :mod:`backend-state/` das mit der bridge spricht.
 * Bei import-time wird der bridge.on('state_snapshot') handler registriert —
 * main.ts importiert dieses file für side-effect (analog zu CSS-imports).
 */

import type { StateSnapshotMessage } from '../_generated/schemas';
import { bridge } from '../bridge/bridge.svelte';
import { overlayContext } from '../services/context/overlay-context.svelte';
import { backendState } from './backend-state.svelte';

bridge.on('state_snapshot', (msg: StateSnapshotMessage) => {
  if (!msg.snapshot) {
    // eslint-disable-next-line no-console
    console.warn('[fp backend-state/sync] state_snapshot ohne snapshot field', msg);
    return;
  }
  backendState.hydrate(msg.snapshot);
  // Re-derive the OverlayContext on every snapshot. The state_snapshot envelope
  // does NOT carry current_session_id (only getState() does), so refresh() goes
  // back to getState() for it. This is the safety net for the stale-mount bug:
  // even if the very first mount-time read was null, the next snapshot recovers
  // the real session id and the render gate stops leaking foreign-session boxes.
  void overlayContext.refresh();
});

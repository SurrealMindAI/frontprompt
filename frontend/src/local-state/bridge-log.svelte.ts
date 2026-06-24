/**
 * BridgeLog — reactive buffer aller Bridge-Events (local-state).
 *
 * localState category — lebt nur im overlay, stirbt mit der page,
 * geht NIEMALS über die bridge. Pure diagnostic.
 *
 * Konsumiert :class:`Bridge` als interceptor (Interceptor-Pattern).
 * Cap auf ``MAX_EVENTS`` (älteste werden gedroppt) — verhindert
 * unbounded memory-growth bei langem Heartbeat-Stream.
 */

import type { BridgeEvent } from '../bridge/bridge.svelte';
import { bridge } from '../bridge/bridge.svelte';

/** Maximum events buffered. Ältere werden FIFO-gedropped. */
export const MAX_EVENTS: number = 200;

export class BridgeLog {
  events = $state<BridgeEvent[]>([]);

  constructor() {
    bridge.addInterceptor((event) => {
      this.events.push(event);
      if (this.events.length > MAX_EVENTS) {
        this.events.splice(0, this.events.length - MAX_EVENTS);
      }
    });
  }

  /** Empty the log. Triggered by user "clear" button in DebugPanel. */
  clear(): void {
    this.events = [];
  }

  /** Count events by direction — used für summary line im DebugPanel. */
  countByDirection = $derived.by(() => {
    let outbound = 0;
    let inbound = 0;
    let error = 0;
    for (const e of this.events) {
      if (e.direction === 'outbound') outbound++;
      else if (e.direction === 'inbound') inbound++;
      else error++;
    }
    return { outbound, inbound, error };
  });
}

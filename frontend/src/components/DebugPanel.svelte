<!--
  DebugPanel — bottom-panel content.
  Horizontal split:
    left (flex 1): scrollable event log, auto-scroll-to-bottom, monospace
    right (fixed ~260px): static version info

  Konsumiert bridgeLog (BridgeLog singleton) — der ist automatisch
  ein interceptor der bridge.
-->

<script lang="ts">
  import { bridge } from '../bridge/bridge.svelte';
  import { localState } from '../local-state/local-state.svelte';

  const bridgeLog = $derived(localState.bridgeLog);

  // Auto-scroll: nach jedem $derived-rerender (= events updated) scrollen
  // wir das log-container auf bottom. Used $effect for DOM side-effect.
  let logEl = $state<HTMLDivElement | undefined>(undefined);
  let autoScroll = $state(true);

  $effect(() => {
    // dependency: events.length — re-run wenn neue events
    bridgeLog.events.length;
    if (autoScroll && logEl) {
      // queueMicrotask: warte einen tick bis DOM-update durch ist
      queueMicrotask(() => {
        if (logEl) logEl.scrollTop = logEl.scrollHeight;
      });
    }
  });

  function formatTime(ms: number): string {
    const d = new Date(ms);
    return (
      d.toLocaleTimeString('en-GB', { hour12: false }) +
      '.' +
      String(d.getMilliseconds()).padStart(3, '0')
    );
  }

  function formatPayload(p: unknown): string {
    try {
      const json = JSON.stringify(p);
      return json.length > 120 ? json.slice(0, 117) + '...' : json;
    } catch {
      return String(p);
    }
  }

  function clearLog() {
    bridgeLog.clear();
  }

  // VersionInfo wird at-runtime aus window.__fp.version gelesen — wenn Bridge
  // schon up und setupBridge() durch, ist version da. Sonst fallback "(pending)".
  const versionInfo = $derived.by(() => {
    if (typeof window !== 'undefined' && window.__fp?.version) {
      return window.__fp.version;
    }
    return null;
  });
</script>

<div class="debug">
  <div class="log-section">
    <header class="log-header">
      <span class="title">bridge log</span>
      <span class="counts">
        ↑ <strong>{bridgeLog.countByDirection.outbound}</strong>
        ↓ <strong>{bridgeLog.countByDirection.inbound}</strong>
        {#if bridgeLog.countByDirection.error > 0}
          ⚠ <strong class="err">{bridgeLog.countByDirection.error}</strong>
        {/if}
      </span>
      <label class="autoscroll">
        <input type="checkbox" bind:checked={autoScroll} />
        autoscroll
      </label>
      <button type="button" class="clear" onclick={clearLog} aria-label="clear log"> clear </button>
    </header>

    <div class="log" bind:this={logEl} role="log" aria-live="polite">
      {#if bridgeLog.events.length === 0}
        <div class="empty">no bridge events yet — waiting for OverlayReady…</div>
      {:else}
        {#each bridgeLog.events as event (event.seq)}
          <div class="row row--{event.direction}">
            <span class="seq">#{event.seq}</span>
            <span class="time">{formatTime(event.timestamp_ms)}</span>
            <span class="dir">
              {#if event.direction === 'outbound'}↑{:else if event.direction === 'inbound'}↓{:else}⚠{/if}
            </span>
            <span class="kind">{event.kind}</span>
            <span class="payload">{formatPayload(event.payload)}</span>
          </div>
        {/each}
      {/if}
    </div>
  </div>

  <aside class="versions">
    <header class="versions-header">versions</header>
    {#if versionInfo}
      <dl class="kv">
        <dt>schema</dt>
        <dd>{versionInfo.schema_version}</dd>
        <dt>build</dt>
        <dd title={versionInfo.bundle_build_version}>
          {versionInfo.bundle_build_version.slice(0, 19).replace('T', ' ')}
        </dd>
        <dt>git</dt>
        <dd>{versionInfo.bundle_build_git_sha}</dd>
        <dt>session</dt>
        <dd title={versionInfo.bundle_build_session}>
          {versionInfo.bundle_build_session.slice(0, 8)}…
        </dd>
      </dl>
    {:else}
      <div class="versions-pending">window.__fp.version not mounted yet</div>
    {/if}

    <div class="bridge-state">
      <span class="state-label">bridge:</span>
      <span class="state-value">{bridge ? 'ready' : 'init'}</span>
    </div>
  </aside>
</div>

<style>
  .debug {
    display: flex;
    flex-direction: row;
    width: 100%;
    height: 100%;
    gap: 0;
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    font-size: 11px;
    color: var(--fp-color-text-primary);
    box-sizing: border-box;
  }

  /* --- log section --- */

  .log-section {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .log-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 10px;
    background: var(--fp-color-surface-secondary);
    border-bottom: 1px solid var(--fp-color-border-subtle);
    flex-shrink: 0;
  }

  .title {
    font-weight: 600;
    color: rgba(180, 200, 255, 0.85);
    letter-spacing: 0.02em;
  }

  .counts {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--fp-color-text-secondary);
  }

  .counts .err {
    color: rgba(255, 120, 120, 0.95);
  }

  .autoscroll {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-left: auto;
    cursor: pointer;
    user-select: none;
    color: var(--fp-color-text-secondary);
  }

  .autoscroll input {
    cursor: pointer;
  }

  .clear {
    background: none;
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-primary);
    font: inherit;
    padding: 2px 8px;
    border-radius: 3px;
    cursor: pointer;
    transition: background 120ms ease;
  }

  .clear:hover {
    background: var(--fp-color-surface-secondary);
  }

  .log {
    flex: 1 1 auto;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 4px 0;
  }

  .empty {
    padding: 16px;
    color: var(--fp-color-text-muted);
    font-style: italic;
    text-align: center;
  }

  .row {
    display: grid;
    grid-template-columns: 44px 110px 16px 140px 1fr;
    gap: 8px;
    padding: 2px 10px;
    align-items: baseline;
    border-bottom: 1px solid var(--fp-color-border-subtle);
  }

  .row--outbound {
    color: rgba(140, 220, 180, 0.92);
  }
  .row--inbound {
    color: rgba(140, 200, 255, 0.92);
  }
  .row--error {
    color: rgba(255, 140, 140, 0.92);
  }

  .seq {
    color: var(--fp-color-text-muted);
  }

  .time {
    color: var(--fp-color-text-muted);
  }

  .dir {
    text-align: center;
    font-weight: 700;
  }

  .kind {
    font-weight: 600;
  }

  .payload {
    color: var(--fp-color-text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }

  /* --- versions sidebar --- */

  .versions {
    flex: 0 0 240px;
    border-left: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    padding: 8px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    overflow: auto;
  }

  .versions-header {
    font-weight: 600;
    color: rgba(180, 200, 255, 0.85);
    letter-spacing: 0.04em;
    text-transform: lowercase;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    padding-bottom: 4px;
  }

  .kv {
    display: grid;
    grid-template-columns: 60px 1fr;
    gap: 2px 8px;
    margin: 0;
  }

  .kv dt {
    color: var(--fp-color-text-muted);
  }

  .kv dd {
    margin: 0;
    color: var(--fp-color-text-primary);
    word-break: break-all;
  }

  .versions-pending {
    color: var(--fp-color-text-muted);
    font-style: italic;
    font-size: 10px;
  }

  .bridge-state {
    margin-top: auto;
    padding-top: 6px;
    border-top: 1px solid var(--fp-color-border-subtle);
    display: flex;
    gap: 6px;
    font-size: 10px;
  }

  .state-label {
    color: var(--fp-color-text-muted);
  }

  .state-value {
    color: rgba(140, 220, 180, 0.95);
    font-weight: 600;
  }
</style>

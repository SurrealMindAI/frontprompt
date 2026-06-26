<!--
  RecordingsTab — List + timeline view for recordings in the left panel.

  Two views (same component):
    - List view (default, activeDetailRecordingId === null):
        Empty state or rows with name, status, entry_count.
        Active recordings show a pulsing red dot (.recording-indicator).
    - Timeline view (activeDetailRecordingId set):
        Per-entry rendering by TimelineEntry kind.
        pick_ref → inline lookup from backendState.inspector.picks (PIT-037: no local $state copy).
        Back button sends selectRecording(null) to deselect.

  Replay progress bar (inline sub-component):
    Shown when backendState.recordings.activeReplayProgress is non-null.
    Displays current_seq / total_steps + passed/failed assertion counts.
    Disappears when progress becomes null (replay completed/aborted).
-->

<script lang="ts">
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import type {
    AssertionEntry,
    PageEventEntry,
    PickRefEntry,
    RegionRefEntry,
    RelationRefEntry,
    NavigationEntry,
  } from '../../../_generated/state';

  // --- Reactive reads from backendState (PIT-037: inline, no local $state copy) ---

  const recordings = $derived(backendState.recordings.recordings);
  const activeDetailId = $derived(backendState.recordings.activeDetailRecordingId);
  const detailRecording = $derived(backendState.recordings.detailRecording);

  // Replay progress — null when no replay is running (PIT-037: inline derived)
  const activeReplayProgress = $derived(backendState.recordings.activeReplayProgress);

  // Timeline entries sorted by seq (entries are append-only / already sorted, but sort defensively).
  const sortedEntries = $derived(
    (detailRecording?.entries ?? []).slice().sort((a, b) => a.seq - b.seq)
  );

  // --- Actions ----------------------------------------------------------------

  function selectRecording(id: string | null): void {
    backendState.recordings.selectRecording(id);
  }

  // --- Helpers ----------------------------------------------------------------

  function formatRelativeTime(ms: number): string {
    const diff = ms - (detailRecording?.started_at_ms ?? ms);
    if (diff < 0) return '0s';
    const s = Math.floor(diff / 1000);
    const m = Math.floor(s / 60);
    if (m > 0) return `+${m}m${s % 60}s`;
    return `+${s}s`;
  }

  function hostnameOf(url: string): string {
    try {
      return new URL(url).hostname;
    } catch {
      return url;
    }
  }

  // Inline pick lookup — must stay inline to avoid PIT-037 stale copy.
  function pickSelectorFor(pickId: string): string {
    return (
      backendState.inspector.picks.find((p) => p.pick_id === pickId)?.element.selector ??
      `pick:${pickId.slice(0, 6)}`
    );
  }

  // Type-narrowing helpers for discriminated union (kind field may be optional in TS type,
  // but Zod default ensures it is always present at runtime).
  function isPageEvent(entry: unknown): entry is PageEventEntry {
    return (entry as PageEventEntry).kind === 'page_event';
  }

  function isPickRef(entry: unknown): entry is PickRefEntry {
    return (entry as PickRefEntry).kind === 'pick_ref';
  }

  function isRegionRef(entry: unknown): entry is RegionRefEntry {
    return (entry as RegionRefEntry).kind === 'region_ref';
  }

  function isRelationRef(entry: unknown): entry is RelationRefEntry {
    return (entry as RelationRefEntry).kind === 'relation_ref';
  }

  function isNavigation(entry: unknown): entry is NavigationEntry {
    return (entry as NavigationEntry).kind === 'navigation';
  }

  function isAssertion(entry: unknown): entry is AssertionEntry {
    return (entry as AssertionEntry).kind === 'assertion';
  }
</script>

<div class="recordings-tab-root">
  <!-- ── Replay progress bar (shown during active replay) ── -->
  {#if activeReplayProgress !== null}
    <div class="replay-progress-bar">
      <span class="replay-progress-label">replaying</span>
      <span class="replay-progress-steps">{activeReplayProgress.current_seq} / {activeReplayProgress.total_steps}</span>
      {#if activeReplayProgress.passed_assertions + activeReplayProgress.failed_assertions > 0}
        <span class="replay-progress-assertions">
          {activeReplayProgress.passed_assertions}✓ {activeReplayProgress.failed_assertions}✗
        </span>
      {/if}
    </div>
  {/if}

  {#if activeDetailId !== null && detailRecording !== null}
  <!-- ── Timeline view ── -->
  <div class="timeline-view">
    <div class="timeline-header">
      <button type="button" class="timeline-back-btn" onclick={() => selectRecording(null)}>
        ← Back
      </button>
      <span class="timeline-header__name">{detailRecording.name}</span>
    </div>

    {#if sortedEntries.length === 0}
      <div class="empty">
        <p class="empty__hint">No entries yet.</p>
      </div>
    {:else}
      <div class="timeline-list">
        {#each sortedEntries as entry (entry.seq)}
          <div class="timeline-entry">
            {#if isPageEvent(entry)}
              <span class="entry-kind page-event">{entry.event_type}</span>
              <span class="entry-target">{entry.target}</span>
              <span class="entry-time">{formatRelativeTime(entry.timestamp_ms)}</span>
            {:else if isPickRef(entry)}
              <span class="entry-kind pick-ref">pick</span>
              <span class="entry-target">{pickSelectorFor(entry.pick_id)}</span>
              <span class="entry-time">{formatRelativeTime(entry.timestamp_ms)}</span>
            {:else if isRegionRef(entry)}
              <span class="entry-kind region-ref">region</span>
              <span class="entry-target">region:{entry.region_id.slice(0, 6)}</span>
              <span class="entry-time">{formatRelativeTime(entry.timestamp_ms)}</span>
            {:else if isRelationRef(entry)}
              <span class="entry-kind relation-ref">relation</span>
              <span class="entry-target">relation:{entry.relation_id.slice(0, 6)}</span>
              <span class="entry-time">{formatRelativeTime(entry.timestamp_ms)}</span>
            {:else if isNavigation(entry)}
              <span class="entry-kind navigation">nav</span>
              <span class="entry-target">{hostnameOf(entry.from_url)} → {hostnameOf(entry.to_url)}</span>
              <span class="entry-time">{formatRelativeTime(entry.timestamp_ms)}</span>
            {:else if isAssertion(entry)}
              <span class="entry-kind assertion">✓ {entry.assertion_type}</span>
              <span class="entry-target">{entry.target}</span>
              <span class="entry-time">{formatRelativeTime(entry.timestamp_ms)}</span>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
{:else}
  <!-- ── List view ── -->
  <div class="recordings-tab">
    {#if recordings.length === 0}
      <div class="empty">
        <p class="empty__hint">No recordings yet.</p>
        <p class="empty__sub">
          Click <strong>record</strong> in the toolbar to start capturing.
        </p>
      </div>
    {:else}
      <div class="list">
        {#each recordings as rec (rec.recording_id)}
          <button
            type="button"
            class="recording-row"
            onclick={() => selectRecording(rec.recording_id)}
            title={rec.name}
          >
            <span class="recording-row__name">{rec.name}</span>
            <span class="recording-row__meta">
              {#if rec.status === 'active'}
                <span class="recording-indicator" aria-label="Recording active"></span>
              {:else}
                <span class="recording-row__count">{rec.entry_count}</span>
              {/if}
            </span>
          </button>
        {/each}
      </div>
    {/if}
  </div>
{/if}
</div>

<style>
  .recordings-tab-root {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .recordings-tab,
  .timeline-view {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  /* ---- Replay progress bar ---- */

  .replay-progress-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 10px;
    background: rgba(120, 180, 255, 0.08);
    border-bottom: 1px solid rgba(120, 180, 255, 0.2);
    flex-shrink: 0;
    font-size: 10px;
  }

  .replay-progress-label {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: rgba(120, 180, 255, 0.7);
    animation: pulse-recording 1s ease-in-out infinite;
  }

  .replay-progress-steps {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    color: var(--fp-color-text-primary);
    flex: 1 1 auto;
  }

  .replay-progress-assertions {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    color: var(--fp-color-text-secondary);
    font-size: 9px;
  }

  /* ---- Empty state ---- */

  .empty {
    padding: 16px 14px;
    color: var(--fp-color-text-secondary);
  }

  .empty__hint {
    margin: 0 0 4px 0;
    font-size: 12px;
    font-weight: 500;
  }

  .empty__sub {
    margin: 0;
    font-size: 11px;
    color: var(--fp-color-text-secondary);
    line-height: 1.5;
  }

  /* ---- List view ---- */

  .list {
    flex: 1 1 auto;
    overflow: auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .recording-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 7px 10px;
    border: none;
    background: transparent;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    cursor: pointer;
    font: inherit;
    text-align: left;
    color: var(--fp-color-text-primary);
    transition: background 120ms ease;
    min-width: 0;
  }

  .recording-row:hover {
    background: var(--fp-color-surface-secondary);
  }

  .recording-row__name {
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1 1 auto;
    min-width: 0;
  }

  .recording-row__meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
    margin-left: 8px;
  }

  .recording-row__count {
    font-size: 10px;
    color: var(--fp-color-text-muted);
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  }

  /* Pulsing red dot — active recording indicator */
  .recording-indicator {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: rgba(255, 80, 80, 0.9);
    animation: pulse-recording 1s ease-in-out infinite;
    flex-shrink: 0;
  }

  @keyframes pulse-recording {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  /* ---- Timeline view ---- */

  .timeline-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    background: var(--fp-color-surface-secondary);
    flex-shrink: 0;
  }

  .timeline-back-btn {
    background: transparent;
    border: none;
    color: var(--fp-color-text-secondary);
    font: inherit;
    font-size: 11px;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 3px;
    transition: background 120ms ease, color 120ms ease;
    flex-shrink: 0;
  }

  .timeline-back-btn:hover {
    background: var(--fp-color-surface-secondary);
    color: var(--fp-color-text-primary);
  }

  .timeline-header__name {
    font-size: 12px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1 1 auto;
    min-width: 0;
    color: var(--fp-color-text-primary);
  }

  .timeline-list {
    flex: 1 1 auto;
    overflow: auto;
    min-height: 0;
  }

  .timeline-entry {
    display: flex;
    align-items: baseline;
    gap: 6px;
    padding: 5px 10px;
    border-bottom: 1px solid var(--fp-color-border-subtle);
    font-size: 11px;
  }

  .entry-kind {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 7px;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    text-transform: lowercase;
    flex-shrink: 0;
    color: var(--fp-color-text-primary);
  }

  .page-event { background: rgba(120, 180, 255, 0.18); }
  .pick-ref { background: rgba(157, 255, 177, 0.18); }
  .region-ref { background: rgba(255, 220, 100, 0.18); }
  .relation-ref { background: rgba(255, 109, 209, 0.18); }
  .navigation { background: rgba(180, 120, 255, 0.18); }
  .assertion { background: rgba(100, 220, 150, 0.18); }

  .entry-target {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    color: var(--fp-color-text-primary);
  }

  .entry-time {
    font-size: 9px;
    color: var(--fp-color-text-muted);
    flex-shrink: 0;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
  }
</style>

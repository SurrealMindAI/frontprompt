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
    TranscriptSegmentEntry,
    Region,
    Relation,
  } from '../../../_generated/state';

  // --- Reactive reads from backendState (PIT-037: inline, no local $state copy) ---

  const recordings = $derived(backendState.recordings.recordings);
  const activeDetailId = $derived(backendState.recordings.activeDetailRecordingId);
  const detailRecording = $derived(backendState.recordings.detailRecording);

  // Replay progress — null when no replay is running (PIT-037: inline derived)
  const activeReplayProgress = $derived(backendState.recordings.activeReplayProgress);

  // Timeline entries sorted chronologically by timestamp_ms (primary), seq (tiebreak).
  // Transcript segments are appended at stop (highest seq) yet span the whole
  // recording — sorting by timestamp_ms interleaves the narration with the actions
  // it describes. seq is the deterministic tiebreak for entries sharing a timestamp.
  const sortedEntries = $derived(
    (detailRecording?.entries ?? [])
      .slice()
      .sort((a, b) => a.timestamp_ms - b.timestamp_ms || a.seq - b.seq)
  );

  // --- Actions ----------------------------------------------------------------

  function selectRecording(id: string | null): void {
    backendState.recordings.selectRecording(id);
  }

  // BUG 4: make name/description editing discoverable from the timeline view.
  // The editor lives in RecordingDetails (RightPanel) — clicking the ✎ affordance
  // ensures the right panel is open so the editor is visible. DRY: no duplicate
  // editor here, we reuse the single RecordingDetails name/description editor.
  function openDetailsEditor(): void {
    if (!backendState.panel.panels.right.open) {
      backendState.panel.togglePanel('right');
    }
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

  // --- Expandable entry state (ADR-018: ephemeral localState, never backend) ---

  // A Set of seq numbers for entries that are currently expanded.
  // Reassign to new Set on each mutation to guarantee Svelte reactivity.
  let expandedSeqs = $state(new Set<number>());

  function toggleEntry(seq: number): void {
    const next = new Set(expandedSeqs);
    if (next.has(seq)) {
      next.delete(seq);
    } else {
      next.add(seq);
    }
    expandedSeqs = next;
  }

  // --- Inline ref-resolvers (PIT-037: no local $state copy) ------------------

  // Must stay inline (not cached in local $state) so they always read the live
  // backendState.inspector arrays — PIT-037.

  function regionFor(regionId: string): Region | null {
    return backendState.inspector.regions.find((r) => r.region_id === regionId) ?? null;
  }

  function relationFor(relationId: string): Relation | null {
    return backendState.inspector.relations.find((r) => r.relation_id === relationId) ?? null;
  }

  // --- Additional formatting helpers -----------------------------------------

  function formatAbsoluteTime(ms: number): string {
    return new Date(ms).toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  function formatMs(ms: number): string {
    const s = ms / 1000;
    return `${s % 1 === 0 ? s.toFixed(0) : s.toFixed(1)}s`;
  }

  function rectStr(rect: { x: number; y: number; width: number; height: number }): string {
    return `${Math.round(rect.x)}, ${Math.round(rect.y)} · ${Math.round(rect.width)} × ${Math.round(rect.height)}`;
  }

  // --- Type-narrowing helpers for discriminated union (kind field may be optional in TS type,
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

  function isTranscriptSegment(entry: unknown): entry is TranscriptSegmentEntry {
    return (entry as TranscriptSegmentEntry).kind === 'transcript_segment';
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
      <button
        type="button"
        class="timeline-edit-btn"
        title="Edit name & description"
        aria-label="Edit name and description"
        onclick={openDetailsEditor}
      >
        ✎
      </button>
    </div>

    {#if sortedEntries.length === 0}
      <div class="empty">
        <p class="empty__hint">No entries yet.</p>
      </div>
    {:else}
      <div class="timeline-list">
        {#each sortedEntries as entry (entry.seq)}
          {@const isExpanded = expandedSeqs.has(entry.seq)}
          <div class="timeline-entry" class:is-expanded={isExpanded}>
            <!-- Compact summary row — clicking toggles the detail panel -->
            <button
              type="button"
              class="timeline-entry__row"
              onclick={() => toggleEntry(entry.seq)}
              aria-expanded={isExpanded}
            >
              <span class="entry-expand-icon" aria-hidden="true">{isExpanded ? '▾' : '▸'}</span>
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
              {:else if isTranscriptSegment(entry)}
                <span class="entry-kind transcript-segment">🎙 voice</span>
                <span class="entry-target entry-target--transcript">{entry.text}</span>
                <span class="entry-time">{formatRelativeTime(entry.timestamp_ms)}</span>
              {/if}
            </button>

            <!-- Expanded detail panel — per-kind resolved detail (PIT-037: inline lookups) -->
            {#if isExpanded}
              <div class="timeline-entry__detail">
                {#if isPageEvent(entry)}
                  <dl class="entry-detail">
                    <dt>seq</dt><dd>{entry.seq}</dd>
                    <dt>event</dt><dd><code>{entry.event_type}</code></dd>
                    <dt>target</dt><dd><code>{entry.target}</code></dd>
                    {#if entry.target_path && entry.target_path.length > 0}
                      <dt>path</dt><dd><code>{entry.target_path.join(' › ')}</code></dd>
                    {/if}
                    {#if entry.key}
                      <dt>key</dt><dd><code>{entry.key}</code></dd>
                    {/if}
                    <dt>prevented</dt><dd>{entry.default_prevented ? 'yes' : 'no'}</dd>
                    <dt>at</dt><dd>{formatAbsoluteTime(entry.timestamp_ms)}</dd>
                    <dt>+</dt><dd>{formatRelativeTime(entry.timestamp_ms)}</dd>
                  </dl>

                {:else if isPickRef(entry)}
                  {@const pick = backendState.inspector.picks.find((p) => p.pick_id === entry.pick_id) ?? null}
                  {#if pick !== null}
                    <dl class="entry-detail">
                      <dt>selector</dt><dd><code>{pick.element.selector}</code></dd>
                      {#if pick.comment}
                        <dt>comment</dt><dd>{pick.comment}</dd>
                      {/if}
                      <dt>color</dt><dd>{pick.color_index ?? 0}</dd>
                      <dt>rect</dt><dd><code>{rectStr(pick.element.rect)}</code></dd>
                      <dt>url</dt><dd class="entry-detail__url">{pick.url}</dd>
                      <dt>id</dt><dd><code>{entry.pick_id}</code></dd>
                    </dl>
                  {:else}
                    <p class="entry-detail-missing">pick not found ({entry.pick_id.slice(0, 8)}…)</p>
                  {/if}

                {:else if isRegionRef(entry)}
                  {@const region = regionFor(entry.region_id)}
                  {#if region !== null}
                    <dl class="entry-detail">
                      <dt>rect</dt><dd><code>{rectStr(region.rect)}</code></dd>
                      <dt>members</dt><dd>{(region.member_pick_ids ?? []).length}</dd>
                      {#if region.note}
                        <dt>note</dt><dd>{region.note}</dd>
                      {/if}
                      <dt>color</dt><dd>{region.color_index ?? 0}</dd>
                      <dt>id</dt><dd><code>{entry.region_id}</code></dd>
                    </dl>
                  {:else}
                    <p class="entry-detail-missing">region not found ({entry.region_id.slice(0, 6)})</p>
                  {/if}

                {:else if isRelationRef(entry)}
                  {@const relation = relationFor(entry.relation_id)}
                  {#if relation !== null}
                    <dl class="entry-detail">
                      <dt>kind</dt><dd><code>{relation.kind}</code></dd>
                      <dt>source</dt><dd><code>{relation.source_id} ({relation.source_kind})</code></dd>
                      <dt>target</dt><dd><code>{relation.target_id} ({relation.target_kind})</code></dd>
                      {#if relation.note}
                        <dt>note</dt><dd>{relation.note}</dd>
                      {/if}
                      <dt>id</dt><dd><code>{entry.relation_id}</code></dd>
                    </dl>
                  {:else}
                    <p class="entry-detail-missing">relation not found ({entry.relation_id.slice(0, 6)})</p>
                  {/if}

                {:else if isNavigation(entry)}
                  <dl class="entry-detail">
                    <dt>from</dt><dd class="entry-detail__url">{entry.from_url}</dd>
                    <dt>to</dt><dd class="entry-detail__url">{entry.to_url}</dd>
                    <dt>at</dt><dd>{formatAbsoluteTime(entry.timestamp_ms)}</dd>
                    <dt>+</dt><dd>{formatRelativeTime(entry.timestamp_ms)}</dd>
                  </dl>

                {:else if isAssertion(entry)}
                  <dl class="entry-detail">
                    <dt>type</dt><dd><code>{entry.assertion_type}</code></dd>
                    {#if entry.target}
                      <dt>target</dt><dd><code>{entry.target}</code></dd>
                    {/if}
                    {#if entry.expected}
                      <dt>expected</dt><dd><code>{entry.expected}</code></dd>
                    {/if}
                    <dt>comparator</dt><dd><code>{entry.comparator}</code></dd>
                    {#if entry.description}
                      <dt>desc</dt><dd>{entry.description}</dd>
                    {/if}
                    <dt>id</dt><dd><code>{entry.assertion_id.slice(0, 8)}</code></dd>
                  </dl>

                {:else if isTranscriptSegment(entry)}
                  <dl class="entry-detail">
                    <dt>text</dt><dd class="entry-detail__text">{entry.text}</dd>
                    <dt>timing</dt><dd><code>{formatMs(entry.start_ms)} – {formatMs(entry.end_ms)}</code></dd>
                    <dt>seq</dt><dd>{entry.seq}</dd>
                    <dt>at</dt><dd>{formatAbsoluteTime(entry.timestamp_ms)}</dd>
                    <dt>backend</dt><dd><code>{entry.backend_id}</code></dd>
                  </dl>
                {/if}
              </div>
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

  /* BUG 4: edit affordance — opens the RecordingDetails editor in the right panel. */
  .timeline-edit-btn {
    background: transparent;
    border: 1px solid var(--fp-color-border);
    color: var(--fp-color-text-secondary);
    font: inherit;
    font-size: 11px;
    line-height: 1;
    cursor: pointer;
    padding: 3px 7px;
    border-radius: 3px;
    flex-shrink: 0;
    transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
  }

  .timeline-edit-btn:hover {
    background: var(--fp-color-surface-secondary);
    color: var(--fp-color-text-primary);
    border-color: rgba(120, 180, 255, 0.5);
  }

  .timeline-list {
    flex: 1 1 auto;
    overflow: auto;
    min-height: 0;
  }

  .timeline-entry {
    border-bottom: 1px solid var(--fp-color-border-subtle);
    font-size: 11px;
  }

  /* Compact summary row — full-width button replacing the old div row */
  .timeline-entry__row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    padding: 5px 10px;
    width: 100%;
    background: transparent;
    border: none;
    cursor: pointer;
    font: inherit;
    text-align: left;
    color: var(--fp-color-text-primary);
    transition: background 80ms ease;
  }

  .timeline-entry__row:hover {
    background: var(--fp-color-surface-secondary);
  }

  .entry-expand-icon {
    font-size: 8px;
    color: var(--fp-color-text-muted);
    flex-shrink: 0;
    width: 10px;
    text-align: center;
    line-height: 1;
    align-self: center;
  }

  /* Detail panel — expanded per-kind resolved content */
  .timeline-entry__detail {
    padding: 0 10px 8px 26px;
    background: rgba(0, 0, 0, 0.08);
    border-top: 1px solid var(--fp-color-border-subtle);
  }

  .entry-detail {
    display: grid;
    grid-template-columns: max-content 1fr;
    column-gap: 10px;
    row-gap: 4px;
    margin: 6px 0 0 0;
    padding: 0;
    font-size: 10px;
  }

  .entry-detail dt {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--fp-color-text-muted);
    align-self: baseline;
    padding-top: 1px;
  }

  .entry-detail dd {
    margin: 0;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    word-break: break-all;
    color: var(--fp-color-text-primary);
  }

  .entry-detail code {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 10px;
    background: var(--fp-color-surface-secondary);
    padding: 1px 3px;
    border-radius: 2px;
  }

  .entry-detail__url {
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace;
    font-size: 9px;
    color: var(--fp-color-text-secondary);
    word-break: break-all;
  }

  .entry-detail__text {
    font-style: italic;
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
  }

  .entry-detail-missing {
    margin: 6px 0 0 0;
    font-size: 10px;
    color: var(--fp-color-text-muted);
    font-style: italic;
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
  .transcript-segment { background: rgba(255, 170, 120, 0.18); }

  /* Voice narration spans the whole row and wraps — it is prose, not a selector. */
  .entry-target--transcript {
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
    font-family: inherit;
    font-style: italic;
    color: var(--fp-color-text-secondary);
  }

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

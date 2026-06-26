<script lang="ts">
  /**
   * SettingsTab — Voice-Over settings: mic picker, backend picker, model download.
   *
   * Reads from:
   *   - `backendState.mic` (MicState) — device list + selection
   *   - `backendState.voiceOver.backends` (TranscriptionBackendInfo[]) — backend list + status
   *   - `backendState.settings` (SettingsState) — voiceOverEnabled, selectedTranscriptionBackendId
   *
   * Sends via bridge:
   *   - `SetMicDeviceRequested` — user changed mic device
   *   - `SetTranscriptionBackendRequested` — user selected a backend
   *   - `TriggerModelDownloadRequested` — user clicked Download for a backend
   *
   * ADR-018: no ephemeral UI state in this component — all state reads are backendState mirrors.
   */
  import { backendState } from '../../../backend-state/backend-state.svelte';
  import { bridge } from '../../../bridge/bridge.svelte';
  import type { SetMicDeviceRequested, SetTranscriptionBackendRequested, TriggerModelDownloadRequested } from '../../../_generated/schemas';

  function onMicChange(event: Event) {
    const select = event.target as HTMLSelectElement;
    const value = select.value;
    const deviceId = value === '' ? null : parseInt(value, 10);
    bridge.send({
      kind: 'set_mic_device_requested',
      mic_device_id: deviceId,
    } satisfies SetMicDeviceRequested);
  }

  function onSelectBackend(backendId: string) {
    bridge.send({
      kind: 'set_transcription_backend_requested',
      backend_id: backendId,
    } satisfies SetTranscriptionBackendRequested);
  }

  function onDownloadBackend(backendId: string) {
    bridge.send({
      kind: 'trigger_model_download_requested',
      backend_id: backendId,
    } satisfies TriggerModelDownloadRequested);
  }

  // Status badge display helpers
  const STATUS_LABELS: Record<string, string> = {
    unavailable: 'Unavailable',
    missing_dep: 'Missing dep',
    needs_download: 'Download required',
    downloading: 'Downloading',
    ready: 'Ready',
    error: 'Error',
  };
</script>

<div class="settings-tab">
  <!-- Mic picker section -->
  <section class="settings-section">
    <h3 class="settings-section-title">Microphone</h3>
    <select
      class="mic-select"
      value={backendState.mic.selectedDeviceId ?? ''}
      onchange={onMicChange}
    >
      <option value="">System default</option>
      {#each backendState.mic.devices as device (device.device_id)}
        <option value={String(device.device_id)}>{device.name}</option>
      {/each}
    </select>
  </section>

  <!-- Transcription backend section -->
  <section class="settings-section">
    <h3 class="settings-section-title">Transcription Backend</h3>
    {#if backendState.voiceOver.backends.length === 0}
      <p class="settings-empty">No backends registered.</p>
    {:else}
      <ul class="backend-list">
        {#each backendState.voiceOver.backends as backend (backend.backend_id)}
          <li class="backend-row">
            <div class="backend-row-header">
              <span class="backend-name">{backend.display_name}</span>
              <span class="backend-status-badge backend-status-{backend.status}">
                {STATUS_LABELS[backend.status] ?? backend.status}
              </span>
            </div>

            {#if backend.status === 'downloading'}
              <div
                class="backend-download-progress"
                role="progressbar"
                aria-valuenow={(backend.download_progress ?? 0) * 100}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  class="backend-download-progress-bar"
                  style="width: {(backend.download_progress ?? 0) * 100}%"
                ></div>
                <span class="backend-download-progress-label">
                  {Math.round((backend.download_progress ?? 0) * 100)}%
                </span>
              </div>
            {/if}

            {#if backend.status === 'needs_download'}
              <button
                class="backend-download-btn"
                onclick={() => onDownloadBackend(backend.backend_id)}
              >
                Download
              </button>
            {/if}

            {#if backend.status === 'ready' || backend.status === 'downloading'}
              <button
                class="backend-select-btn"
                onclick={() => onSelectBackend(backend.backend_id)}
              >
                {backendState.settings.selectedTranscriptionBackendId === backend.backend_id
                  ? 'Selected'
                  : 'Select'}
              </button>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</div>

<style>
  .settings-tab {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 0.75rem;
    overflow-y: auto;
  }

  .settings-section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .settings-section-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-secondary, #888);
    margin: 0;
  }

  .mic-select {
    width: 100%;
    padding: 0.375rem 0.5rem;
    font-size: 0.8rem;
    border: 1px solid var(--color-border, #333);
    border-radius: 4px;
    background: var(--color-bg-secondary, #1a1a1a);
    color: var(--color-text, #e0e0e0);
  }

  .backend-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .backend-row {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.5rem;
    border: 1px solid var(--color-border, #333);
    border-radius: 4px;
    background: var(--color-bg-secondary, #1a1a1a);
  }

  .backend-row-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .backend-name {
    font-size: 0.8rem;
    color: var(--color-text, #e0e0e0);
  }

  .backend-status-badge {
    font-size: 0.7rem;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    font-weight: 500;
  }

  .backend-status-ready {
    background: rgba(0, 200, 100, 0.15);
    color: #00c864;
  }

  .backend-status-needs_download,
  .backend-status-downloading {
    background: rgba(255, 180, 0, 0.15);
    color: #ffb400;
  }

  .backend-status-unavailable,
  .backend-status-missing_dep,
  .backend-status-error {
    background: rgba(255, 80, 80, 0.15);
    color: #ff5050;
  }

  .backend-download-progress {
    position: relative;
    height: 6px;
    background: var(--color-border, #333);
    border-radius: 3px;
    overflow: hidden;
  }

  .backend-download-progress-bar {
    height: 100%;
    background: #ffb400;
    border-radius: 3px;
    transition: width 0.2s ease;
  }

  .backend-download-progress-label {
    position: absolute;
    right: 4px;
    top: -14px;
    font-size: 0.65rem;
    color: var(--color-text-secondary, #888);
  }

  .backend-download-btn,
  .backend-select-btn {
    align-self: flex-start;
    padding: 0.25rem 0.625rem;
    font-size: 0.75rem;
    border: 1px solid var(--color-border, #444);
    border-radius: 3px;
    cursor: pointer;
    background: var(--color-bg, #111);
    color: var(--color-text, #e0e0e0);
  }

  .backend-download-btn:hover {
    border-color: #ffb400;
    color: #ffb400;
  }

  .backend-select-btn:hover {
    border-color: #00c864;
    color: #00c864;
  }

  .settings-empty {
    font-size: 0.8rem;
    color: var(--color-text-secondary, #888);
    margin: 0;
  }
</style>

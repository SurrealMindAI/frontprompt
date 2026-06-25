<script lang="ts">
  // Selection-bracket mark: four corner handles framing a target dot — the
  // gesture frontprompt makes when it picks an element. Doubles as the favicon
  // motif. size in px.
  let { size = 26 }: { size?: number } = $props();
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  aria-hidden="true"
  class="mark"
>
  <!-- corner handles -->
  <path d="M3 8V3H8" />
  <path d="M21 8V3H16" />
  <path d="M3 16V21H8" />
  <path d="M21 16V21H16" />
  <!-- target -->
  <circle cx="12" cy="12" r="2.4" class="dot" />
</svg>

<style>
  .mark path {
    stroke: var(--accent);
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .dot {
    fill: var(--select);
    stroke: none;
  }
</style>

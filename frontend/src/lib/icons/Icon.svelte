<!--
  Icon — single inline-SVG icon primitive for the HUD.

  Renders a crisp, stroke-based (lucide-style) icon from the {@link ICONS}
  registry at a chosen pixel size, inheriting colour via `currentColor`. It
  replaces the cross-platform-inconsistent Unicode glyph icons (◉ ○ ✕ …) that
  render differently per OS/font and carry no semantics.

  Accessibility: decorative by default (`aria-hidden`) — the parent control owns
  the accessible name (`aria-label`/`title`), matching the existing toolbar
  pattern. Pass `title` to turn the icon itself into a labelled image
  (`role="img"` + `<title>`), e.g. when it stands alone without a labelled parent.
-->
<script lang="ts">
  import { ICONS, type IconName } from './icons';

  interface Props {
    name: IconName;
    /** Pixel size (width = height). Default 16 — the HUD control glyph size. */
    size?: number;
    /** Accessible name. When set the icon becomes role="img"; else aria-hidden. */
    title?: string;
    /** Stroke width in viewBox units. Default 2 (lucide default). */
    strokeWidth?: number;
  }

  const { name, size = 16, title, strokeWidth = 2 }: Props = $props();
  const body = $derived(ICONS[name] ?? '');
</script>

<svg
  class="fp-icon"
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill="none"
  stroke="currentColor"
  stroke-width={strokeWidth}
  stroke-linecap="round"
  stroke-linejoin="round"
  role={title ? 'img' : undefined}
  aria-hidden={title ? undefined : 'true'}
  aria-label={title}
  data-icon={name}
>
  {#if title}<title>{title}</title>{/if}
  <!-- eslint-disable-next-line svelte/no-at-html-tags — static, trusted icon registry (no user input) -->
  {@html body}
</svg>

<style>
  .fp-icon {
    display: inline-block;
    flex-shrink: 0;
    vertical-align: middle;
  }
</style>

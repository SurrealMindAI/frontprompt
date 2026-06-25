<script lang="ts">
  import { readme, heroSubtitle, features, steps } from '../lib/content';
  import { renderMarkdown, renderSnippet } from '../lib/markdown';
  import HeroInspector from './HeroInspector.svelte';

  import IconCursor from '~icons/ph/cursor-click-bold';
  import IconGlobe from '~icons/ph/globe-hemisphere-west-bold';
  import IconPlugs from '~icons/ph/plugs-connected-bold';
  import IconBolt from '~icons/ph/lightning-bold';
  import IconBrowser from '~icons/ph/browser-bold';
  import IconSelect from '~icons/ph/selection-plus-bold';
  import IconSparkle from '~icons/ph/sparkle-bold';
  import IconArrow from '~icons/ph/arrow-right-bold';
  import IconGithub from '~icons/ph/github-logo-bold';

  const GITHUB = 'https://github.com/SurrealMindAI/frontprompt';

  // Icons are presentation — assigned by order, not authored in landing.md.
  const featureIcons = [IconCursor, IconGlobe, IconPlugs, IconBolt];
  const stepIcons = [IconBrowser, IconSelect, IconSparkle];

  // Hero headline = README's bold tagline (SSoT); subtitle = punchy landing.md line.
  const introParas = readme.intro.split(/\n\s*\n/);
  const tagline = (introParas[0] ?? '').replace(/^\*\*|\*\*$/g, '').trim();

  function firstCodeBlock(md: string): string {
    const m = md.match(/```[a-z]*\n([\s\S]*?)```/);
    return m ? m[1].trim() : '';
  }
  const installSection = readme.fullSections.get('Install') ?? '';
  const usageSection = readme.fullSections.get('Usage') ?? '';
  const heroCmd = firstCodeBlock(installSection);

  const installHtml = renderMarkdown(installSection, 'README.md');
  const usageHtml = renderMarkdown(usageSection, 'README.md');
</script>

<!-- ============================ HERO ============================ -->
<section class="hero">
  <div class="wrap hero-grid">
    <div class="hero-copy">
      <span class="hud-tag"><IconCursor /> browser automation · MCP server</span>
      <h1>{tagline}</h1>
      <p class="lede">{heroSubtitle}</p>

      <div class="cta">
        <a href="#/docs" class="btn btn-primary">Read the docs <IconArrow /></a>
        <a href={GITHUB} class="btn btn-ghost" target="_blank" rel="noopener noreferrer">
          <IconGithub /> GitHub
        </a>
      </div>

      {#if heroCmd}
        <div class="term" role="group" aria-label="Quick install">
          <div class="term-head">
            <span class="dots"><i></i><i></i><i></i></span>
            <span class="hud">install</span>
          </div>
          <pre>{heroCmd}</pre>
        </div>
      {/if}
    </div>

    <div class="hero-visual">
      <HeroInspector />
    </div>
  </div>
</section>

<!-- ========================== FEATURES ========================== -->
{#if features.length}
  <section class="section">
    <div class="wrap">
      <header class="sec-head">
        <span class="hud">// capabilities</span>
        <h2>What it does</h2>
      </header>

      <div class="feature-grid">
        {#each features as f, i}
          {@const Ico = featureIcons[i % featureIcons.length]}
          <article class="feature">
            <div class="feature-ic"><Ico /></div>
            <span class="feature-idx">{String(i + 1).padStart(2, '0')}</span>
            <h3>{f.title}</h3>
            <div class="feature-body">{@html renderSnippet(f.body)}</div>
            <span class="handle tl"></span><span class="handle tr"></span>
            <span class="handle bl"></span><span class="handle br"></span>
          </article>
        {/each}
      </div>
    </div>
  </section>
{/if}

<!-- ========================= HOW IT WORKS ======================= -->
{#if steps.length}
  <section class="section">
    <div class="wrap">
      <header class="sec-head">
        <span class="hud">// workflow</span>
        <h2>Point, annotate, drive</h2>
      </header>

      <ol class="steps">
        {#each steps as s, i}
          {@const Ico = stepIcons[i % stepIcons.length]}
          <li class="step">
            <div class="step-top">
              <div class="step-ic"><Ico /></div>
              <span class="step-num">{String(i + 1).padStart(2, '0')}</span>
            </div>
            <h3>{s.title}</h3>
            <div class="step-body">{@html renderSnippet(s.body)}</div>
          </li>
        {/each}
      </ol>
    </div>
  </section>
{/if}

<!-- ========================== GET STARTED ======================= -->
<section class="section install-section">
  <div class="wrap">
    <header class="sec-head">
      <span class="hud">// get started</span>
      <h2>Install &amp; run</h2>
    </header>

    <div class="install-grid">
      <div class="panel">
        <div class="panel-tab">Install</div>
        <div class="prose">{@html installHtml}</div>
      </div>
      <div class="panel">
        <div class="panel-tab">Usage</div>
        <div class="prose">{@html usageHtml}</div>
      </div>
    </div>

    <div class="docs-cta">
      <a href="#/docs/architecture" class="btn btn-ghost">How cross-origin survival works</a>
      <a href="#/docs" class="btn btn-primary">Full documentation <IconArrow /></a>
    </div>
  </div>
</section>

<style>
  /* ---------------- hero ---------------- */
  .hero {
    padding: clamp(3rem, 8vw, 6.5rem) 0 clamp(2.5rem, 6vw, 5rem);
    position: relative;
  }
  .hero-grid {
    display: grid;
    grid-template-columns: 1.05fr 0.95fr;
    gap: clamp(2rem, 5vw, 4.5rem);
    align-items: center;
  }
  .hud-tag :global(svg) {
    font-size: 0.9rem;
  }
  .hero-copy h1 {
    font-size: clamp(2.5rem, 6.2vw, 4.4rem);
    margin: 1rem 0 1.1rem;
    letter-spacing: -0.035em;
    background: linear-gradient(180deg, #fff 30%, #b9c6dc);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  .lede {
    font-size: 1.22rem;
    line-height: 1.55;
    color: var(--text-dim);
    max-width: 34ch;
    margin: 0;
  }
  .cta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.8rem;
    margin: 1.9rem 0 1.6rem;
  }
  .cta :global(svg) {
    font-size: 1.05em;
  }
  .term {
    border-radius: var(--radius-sm);
    background:
      linear-gradient(var(--panel), var(--panel)) padding-box,
      linear-gradient(120deg, var(--accent), var(--select)) border-box;
    border: 1px solid transparent;
    overflow: hidden;
    max-width: 31rem;
    box-shadow: 0 18px 50px -24px var(--accent-glow);
  }
  .term-head {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.5rem 0.85rem;
    border-bottom: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.02);
  }
  .dots {
    display: inline-flex;
    gap: 5px;
  }
  .dots i {
    width: 9px;
    height: 9px;
    border-radius: 999px;
    background: var(--line-strong);
  }
  .dots i:first-child {
    background: var(--select);
  }
  .dots i:nth-child(2) {
    background: var(--warn);
  }
  .dots i:last-child {
    background: var(--ok);
  }
  .term pre {
    margin: 0;
    padding: 0.95rem 1.05rem;
    font-family: var(--font-mono);
    font-size: 0.82rem;
    line-height: 1.75;
    color: var(--text);
    overflow-x: auto;
  }

  /* ---------------- sections ---------------- */
  .section {
    padding: clamp(2.5rem, 6vw, 5rem) 0;
    border-top: 1px solid var(--line);
  }
  .sec-head {
    margin-bottom: 2.2rem;
  }
  .sec-head .hud {
    display: block;
    margin-bottom: 0.5rem;
  }
  .sec-head h2 {
    font-size: clamp(1.8rem, 4vw, 2.6rem);
    letter-spacing: -0.03em;
  }

  /* ---------------- features ---------------- */
  .feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(238px, 1fr));
    gap: 1.1rem;
  }
  .feature {
    position: relative;
    padding: 1.6rem 1.4rem;
    border: 1px solid var(--line-strong);
    border-radius: var(--radius);
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    transition:
      border-color 0.2s ease,
      transform 0.2s ease;
    overflow: hidden;
  }
  .feature::after {
    /* soft accent corner glow */
    content: '';
    position: absolute;
    top: -40px;
    right: -40px;
    width: 110px;
    height: 110px;
    background: radial-gradient(circle, var(--accent-subtle), transparent 70%);
    opacity: 0;
    transition: opacity 0.25s ease;
  }
  .feature:hover {
    border-color: var(--accent);
    transform: translateY(-4px);
  }
  .feature:hover::after {
    opacity: 1;
  }
  .feature-ic {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border-radius: 11px;
    font-size: 1.4rem;
    color: var(--accent-bright);
    background: var(--accent-subtle);
    border: 1px solid rgba(91, 157, 255, 0.25);
    margin-bottom: 1rem;
  }
  .feature-idx {
    position: absolute;
    top: 1.5rem;
    right: 1.4rem;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    color: var(--text-mute);
  }
  .feature h3 {
    font-size: 1.22rem;
    margin: 0 0 0.5rem;
  }
  .feature-body {
    color: var(--text-dim);
    font-size: 0.97rem;
    line-height: 1.58;
  }
  .feature-body :global(p) {
    margin: 0;
  }
  .feature-body :global(strong) {
    color: var(--accent-bright);
    font-weight: 600;
  }
  .feature .handle {
    position: absolute;
    width: 8px;
    height: 8px;
    border: 1.5px solid var(--accent);
    background: var(--bg);
    border-radius: 1px;
    opacity: 0;
    transition: opacity 0.2s ease;
  }
  .feature:hover .handle {
    opacity: 1;
  }
  .feature .handle.tl {
    top: -4px;
    left: -4px;
  }
  .feature .handle.tr {
    top: -4px;
    right: -4px;
  }
  .feature .handle.bl {
    bottom: -4px;
    left: -4px;
  }
  .feature .handle.br {
    bottom: -4px;
    right: -4px;
  }

  /* ---------------- steps ---------------- */
  .steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.4rem;
    position: relative;
  }
  .step {
    position: relative;
    padding: 1.6rem 1.5rem;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--panel);
  }
  .step-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.9rem;
  }
  .step-ic {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 42px;
    height: 42px;
    border-radius: 11px;
    font-size: 1.35rem;
    color: var(--accent-bright);
    background: var(--accent-subtle);
    border: 1px solid rgba(91, 157, 255, 0.25);
  }
  .step-num {
    font-family: var(--font-mono);
    font-size: 1.7rem;
    font-weight: 700;
    color: rgba(91, 157, 255, 0.35);
  }
  .step h3 {
    font-size: 1.2rem;
    margin: 0 0 0.5rem;
  }
  .step-body {
    color: var(--text-dim);
    font-size: 0.97rem;
    line-height: 1.6;
  }
  .step-body :global(p) {
    margin: 0;
  }
  .step-body :global(code) {
    font-family: var(--font-mono);
    font-size: 0.85em;
    background: rgba(91, 157, 255, 0.12);
    border: 1px solid rgba(91, 157, 255, 0.2);
    border-radius: 5px;
    padding: 0.1em 0.4em;
    color: var(--accent-bright);
  }
  .step:not(:last-child)::after {
    content: '';
    position: absolute;
    right: -1rem;
    top: 50%;
    width: 1rem;
    height: 1px;
    background: linear-gradient(90deg, var(--accent), transparent);
    z-index: 2;
  }

  /* ---------------- install ---------------- */
  .install-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.3rem;
  }
  .panel {
    position: relative;
    border: 1px solid var(--line-strong);
    border-radius: var(--radius);
    background: var(--panel);
    padding: 1.5rem 1.6rem 1.7rem;
  }
  .panel-tab {
    display: inline-block;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--accent);
    border: 1px solid rgba(91, 157, 255, 0.3);
    border-radius: 999px;
    padding: 0.2em 0.8em;
    margin-bottom: 1rem;
  }
  .panel .prose {
    max-width: none;
    font-size: 0.96rem;
  }
  .docs-cta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.8rem;
    margin-top: 2.2rem;
    justify-content: center;
  }
  .docs-cta :global(svg) {
    font-size: 1.05em;
  }

  /* ---------------- responsive ---------------- */
  @media (max-width: 900px) {
    .hero-grid {
      grid-template-columns: 1fr;
    }
    .hero-visual {
      order: -1;
    }
    .steps {
      grid-template-columns: 1fr;
    }
    .step:not(:last-child)::after {
      display: none;
    }
    .install-grid {
      grid-template-columns: 1fr;
    }
  }
</style>

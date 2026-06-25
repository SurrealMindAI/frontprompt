<script lang="ts">
  import BrandMark from './BrandMark.svelte';
  import pkg from '../../package.json';

  const GITHUB = 'https://github.com/SurrealMindAI/frontprompt';
  const PYPI = 'https://pypi.org/project/frontprompt/';
</script>

<footer class="foot">
  <div class="wrap inner">
    <div class="col brand-col">
      <a href="#/" class="brand"><BrandMark size={22} /><span>frontprompt</span></a>
      <p class="tag">Annotate any web page, and drive it from an AI agent.</p>
      <span class="hud">v{pkg.version} · BSD-3-Clause</span>
    </div>

    <div class="col">
      <div class="col-title">Docs</div>
      <a href="#/docs/overview">Overview</a>
      <a href="#/docs/architecture">Architecture</a>
      <a href="#/docs/wire-protocol">Wire Protocol</a>
      <a href="#/docs/development">Development</a>
    </div>

    <div class="col">
      <div class="col-title">Project</div>
      <a href={GITHUB} target="_blank" rel="noopener noreferrer">GitHub ↗</a>
      <a href={PYPI} target="_blank" rel="noopener noreferrer">PyPI ↗</a>
      <a href="#/docs/contributing">Contributing</a>
    </div>
  </div>

  <div class="wrap baseline">
    <span>© SurrealMind</span>
    <span class="hud">annotate · pick · region · relation</span>
  </div>
</footer>

<style>
  .foot {
    border-top: 1px solid var(--line);
    margin-top: 2rem;
    padding: 3rem 0 2rem;
    background: linear-gradient(180deg, transparent, rgba(91, 157, 255, 0.03));
  }
  .inner {
    display: grid;
    grid-template-columns: 1.6fr 1fr 1fr;
    gap: 2rem;
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 0.5ch;
    color: var(--text);
    font-family: var(--font-display);
    font-weight: 800;
    font-size: 1.1rem;
    letter-spacing: -0.03em;
  }
  .tag {
    color: var(--text-mute);
    max-width: 32ch;
    margin: 0.8rem 0 0.7rem;
    font-size: 0.95rem;
  }
  .col-title {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-mute);
    margin-bottom: 0.8rem;
  }
  .col a {
    display: block;
    color: var(--text-dim);
    padding: 0.22rem 0;
    font-size: 0.95rem;
  }
  .col a:hover {
    color: var(--accent);
  }
  .baseline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-top: 2.4rem;
    padding-top: 1.4rem;
    border-top: 1px solid var(--line);
    color: var(--text-mute);
    font-size: 0.85rem;
  }
  @media (max-width: 700px) {
    .inner {
      grid-template-columns: 1fr 1fr;
    }
    .brand-col {
      grid-column: 1 / -1;
    }
  }
</style>

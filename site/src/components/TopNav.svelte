<script lang="ts">
  import BrandMark from './BrandMark.svelte';
  import { router } from '../lib/routes.svelte';
  import pkg from '../../package.json';
  import IconGithub from '~icons/ph/github-logo-bold';

  const GITHUB = 'https://github.com/SurrealMindAI/frontprompt';
  const PYPI = 'https://pypi.org/project/frontprompt/';

  const onDocs = $derived(router.route.kind === 'docs');
</script>

<header class="nav">
  <div class="wrap inner">
    <a href="#/" class="brand" aria-label="frontprompt — home">
      <span class="mark"><BrandMark size={26} /></span>
      <span class="wordmark">frontprompt</span>
      <span class="ver">v{pkg.version}</span>
    </a>

    <nav class="links">
      <a href="#/docs" class:active={onDocs}>Docs</a>
      <a href="#/docs/architecture">Architecture</a>
      <a href={PYPI} target="_blank" rel="noopener noreferrer">PyPI</a>
      <a href={GITHUB} class="gh" target="_blank" rel="noopener noreferrer" aria-label="GitHub">
        <IconGithub /> <span class="gh-label">GitHub</span>
      </a>
    </nav>
  </div>
</header>

<style>
  .nav {
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(7, 9, 15, 0.72);
    backdrop-filter: blur(14px) saturate(140%);
    border-bottom: 1px solid var(--line);
  }
  .inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 66px;
    gap: 1rem;
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    color: var(--text);
    line-height: 1;
  }
  .mark {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
  }
  .wordmark {
    font-family: var(--font-display);
    font-weight: 800;
    font-size: 1.22rem;
    letter-spacing: -0.03em;
    line-height: 1;
  }
  .ver {
    align-self: center;
    font-family: var(--font-mono);
    font-size: 0.64rem;
    color: var(--accent);
    border: 1px solid rgba(91, 157, 255, 0.3);
    border-radius: 999px;
    padding: 0.2em 0.55em;
    letter-spacing: 0.02em;
    transform: translateY(1px);
  }
  .links {
    display: flex;
    align-items: center;
    gap: clamp(0.8rem, 2.2vw, 1.7rem);
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 0.96rem;
  }
  .links a {
    color: var(--text-mute);
    transition: color 0.15s ease;
  }
  .links a:hover,
  .links a.active {
    color: var(--text);
  }
  .links .gh {
    display: inline-flex;
    align-items: center;
    gap: 0.45ch;
    color: var(--text);
  }
  .links .gh :global(svg) {
    font-size: 1.15em;
  }
  @media (max-width: 640px) {
    .links a:nth-child(2) {
      display: none;
    }
    .ver,
    .gh-label {
      display: none;
    }
  }
</style>

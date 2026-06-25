<script lang="ts">
  import { docBySlug } from '../lib/content';
  import { renderMarkdown } from '../lib/markdown';
  import Sidebar from './Sidebar.svelte';

  let { slug }: { slug: string } = $props();

  const GITHUB_BLOB = 'https://github.com/SurrealMindAI/frontprompt/blob/main/';

  const doc = $derived(docBySlug.get(slug));
  const html = $derived(doc ? renderMarkdown(doc.raw, doc.source) : '');
</script>

<div class="wrap docs">
  <aside class="rail">
    <Sidebar current={slug} />
  </aside>

  <article class="content">
    {#if doc}
      <div class="doc-meta">
        <span class="hud">{doc.group}</span>
        <a class="src" href={GITHUB_BLOB + doc.source} target="_blank" rel="noopener noreferrer">
          {doc.source} ↗
        </a>
      </div>
      <div class="prose">{@html html}</div>
    {:else}
      <div class="notfound">
        <span class="hud">404 · no pick here</span>
        <h1>Doc not found</h1>
        <p>The page <code>{slug}</code> doesn't exist in the lexicon.</p>
        <a href="#/docs" class="btn btn-primary">Back to docs</a>
      </div>
    {/if}
  </article>
</div>

<style>
  .docs {
    display: grid;
    grid-template-columns: 230px minmax(0, 1fr);
    gap: clamp(1.5rem, 4vw, 3.5rem);
    padding: 2.5rem 0 5rem;
    align-items: start;
  }
  .rail {
    position: sticky;
    top: 88px;
    max-height: calc(100vh - 110px);
    overflow-y: auto;
    padding-right: 0.5rem;
  }
  .content {
    min-width: 0;
  }
  .doc-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.4rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--line);
  }
  .src {
    font-family: var(--font-mono);
    font-size: 0.74rem;
    color: var(--text-mute);
  }
  .src:hover {
    color: var(--accent);
  }
  .notfound {
    padding: 3rem 0;
  }
  .notfound h1 {
    font-size: 2rem;
    margin: 0.6rem 0;
  }
  .notfound .btn {
    margin-top: 1.4rem;
  }

  @media (max-width: 820px) {
    .docs {
      grid-template-columns: 1fr;
    }
    .rail {
      position: static;
      max-height: none;
      border-bottom: 1px solid var(--line);
      padding-bottom: 1.5rem;
      margin-bottom: 1rem;
    }
  }
</style>

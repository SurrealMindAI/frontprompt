<script lang="ts">
  import { docBySlug } from '../lib/content';
  import { renderMarkdown } from '../lib/markdown';
  import { enhanceProse, type Heading } from '../lib/prose-enhance';
  import Sidebar from './Sidebar.svelte';

  let { slug }: { slug: string } = $props();

  const GITHUB_BLOB = 'https://github.com/SurrealMindAI/frontprompt/blob/main/';

  const doc = $derived(docBySlug.get(slug));
  const html = $derived(doc ? renderMarkdown(doc.raw, doc.source) : '');

  let proseEl: HTMLElement | undefined = $state();
  let toc: Heading[] = $state([]);

  // After each render, post-process the prose: render mermaid diagrams, add
  // copy buttons to code blocks, route heading-anchor links through the hash
  // router, and harvest the on-this-page table of contents. Re-runs on
  // navigation because it reads `html` and `slug`.
  $effect(() => {
    // establish reactive deps
    void html;
    const currentSlug = slug;
    const el = proseEl;
    if (!el) return;
    let cancelled = false;
    enhanceProse(el, currentSlug).then((headings) => {
      if (!cancelled) toc = headings;
    });
    return () => {
      cancelled = true;
    };
  });
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
      <div class="prose" bind:this={proseEl}>{@html html}</div>
    {:else}
      <div class="notfound">
        <span class="hud">404 · no pick here</span>
        <h1>Doc not found</h1>
        <p>The page <code>{slug}</code> doesn't exist in the lexicon.</p>
        <a href="#/docs" class="btn btn-primary">Back to docs</a>
      </div>
    {/if}
  </article>

  {#if doc && toc.length > 1}
    <aside class="toc" aria-label="On this page">
      <div class="toc-title">On this page</div>
      <ul>
        {#each toc as h}
          <li class="lvl-{h.level}">
            <a href={`#/docs/${slug}#${h.id}`}>{h.text}</a>
          </li>
        {/each}
      </ul>
    </aside>
  {/if}
</div>

<style>
  .docs {
    display: grid;
    grid-template-columns: 230px minmax(0, 1fr) 200px;
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

  /* On-this-page table of contents */
  .toc {
    position: sticky;
    top: 88px;
    max-height: calc(100vh - 110px);
    overflow-y: auto;
    font-size: 0.82rem;
  }
  .toc-title {
    font-family: var(--font-mono);
    font-size: 0.64rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-mute);
    margin-bottom: 0.7rem;
  }
  .toc ul {
    list-style: none;
    margin: 0;
    padding: 0;
    border-left: 1px solid var(--line);
  }
  .toc li {
    margin: 0;
  }
  .toc li a {
    display: block;
    padding: 0.28rem 0.7rem;
    margin-left: -1px;
    border-left: 2px solid transparent;
    color: var(--text-mute);
    line-height: 1.35;
    transition:
      color 0.14s ease,
      border-color 0.14s ease;
  }
  .toc li.lvl-3 a {
    padding-left: 1.4rem;
    font-size: 0.95em;
  }
  .toc li a:hover {
    color: var(--text);
    border-left-color: var(--accent);
  }

  @media (max-width: 1100px) {
    .docs {
      grid-template-columns: 230px minmax(0, 1fr);
    }
    .toc {
      display: none;
    }
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

<script lang="ts">
  import { nav } from '../lib/content';

  let { current }: { current: string } = $props();
</script>

<nav class="sidebar" aria-label="Documentation">
  {#each nav as section}
    <div class="group">
      <div class="group-title">{section.group}</div>
      <ul>
        {#each section.docs as doc}
          <li>
            <a href={`#/docs/${doc.slug}`} class:active={doc.slug === current}>
              {doc.title}
            </a>
          </li>
        {/each}
      </ul>
    </div>
  {/each}
</nav>

<style>
  .sidebar {
    font-size: 0.93rem;
  }
  .group {
    margin-bottom: 1.6rem;
  }
  .group-title {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-mute);
    margin-bottom: 0.6rem;
    padding-left: 0.75rem;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    border-left: 1px solid var(--line);
  }
  li a {
    display: block;
    padding: 0.32rem 0.75rem;
    margin-left: -1px;
    border-left: 2px solid transparent;
    color: var(--text-mute);
    transition:
      color 0.14s ease,
      border-color 0.14s ease;
  }
  li a:hover {
    color: var(--text);
  }
  li a.active {
    color: var(--accent-bright);
    border-left-color: var(--accent);
    background: linear-gradient(90deg, var(--accent-subtle), transparent);
  }
</style>

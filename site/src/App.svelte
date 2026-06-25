<script lang="ts">
  import { router } from './lib/routes.svelte';
  import TopNav from './components/TopNav.svelte';
  import SiteFooter from './components/SiteFooter.svelte';
  import Landing from './components/Landing.svelte';
  import DocsView from './components/DocsView.svelte';

  const route = $derived(router.route);
</script>

<TopNav />

<main>
  {#if route.kind === 'docs'}
    <DocsView slug={route.slug} />
  {:else}
    <Landing />
  {/if}
</main>

<SiteFooter />

<style>
  main {
    display: block;
    min-height: 60vh;
  }
</style>

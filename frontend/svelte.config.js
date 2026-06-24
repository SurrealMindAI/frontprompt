import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/vite-plugin-svelte').SvelteConfig} */
const config = {
  preprocess: vitePreprocess(),
  compilerOptions: {
    // Svelte 5 Runes mode mandatory for all .svelte files (consistency).
    runes: true,
  },
};

export default config;

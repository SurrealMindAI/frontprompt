import { svelte, vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// Standalone Vite app config for the overlay visual-regression harness ONLY.
// Separate from the lib-mode build (../vite.config.ts) so it has no
// build-session guard and serves a normal index.html that Playwright can drive.
// Svelte options mirror ../svelte.config.js (runes + vitePreprocess) because the
// plugin would otherwise not discover that config from this nested root.
export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  plugins: [
    svelte({
      emitCss: false,
      preprocess: vitePreprocess(),
      compilerOptions: { runes: true },
    }),
  ],
  resolve: { conditions: ['browser'] },
  server: { port: 5180, strictPort: true },
  preview: { port: 5180, strictPort: true },
});

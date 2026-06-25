import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';
import Icons from 'unplugin-icons/vite';

// ============================================================================
// frontprompt SITE build — marketing landing + docs surface
// ============================================================================
// Separate from frontend/vite.config.ts (the overlay IIFE library build). This
// is a plain SPA build for GitHub Pages.
//
// Markdown is the single source of truth: content.ts globs the repo's *.md
// files raw (../README.md, ../ARCHITECTURE.md, ../docs/**, frontend service
// READMEs) — nothing is duplicated into HTML/Svelte. The Svelte layer only
// renders. fs.allow is widened to the repo root so those globs + the shared
// design tokens (../frontend/src/lib/tokens) resolve in dev.
//
// base '/frontprompt/' targets GitHub Pages at surrealmindai.github.io/frontprompt/.
// ============================================================================

export default defineConfig({
  base: '/frontprompt/',
  plugins: [
    svelte(),
    // Phosphor icons inlined as Svelte components at build time — no runtime
    // fetch, no network, no FOUC. Import as `~icons/ph/<name>`.
    Icons({ compiler: 'svelte' }),
  ],
  server: {
    fs: {
      // site/ sits at the repo root; '..' is the frontprompt repo root, which
      // contains every Markdown SSoT file + the shared design tokens.
      allow: ['..'],
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});

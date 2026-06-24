import { svelte } from '@sveltejs/vite-plugin-svelte';
import { svelteTesting } from '@testing-library/svelte/vite';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

// ============================================================================
// CANONICAL BUILD-PIPELINE GUARD
// ============================================================================
// This config MUST be invoked via `uv run python -m frontprompt.build`, which
// generates the FRONTPROMPT_BUILD_SESSION env var + runs the Pydantic→Zod
// codegen first. Direct `bun run build` would skip codegen → drift between the
// Pydantic SSoT and the generated Zod schemas → silent wire-protocol mismatches.
//
// Guard fires ONLY on actual build (vite build / vite dev) — svelte-check
// (bun run check) and vitest (bun run test) load this config too, but don't
// produce any output, so they don't need the build-session env var.
// ============================================================================

// Phase 1 overlay-build: IIFE single-file output for Playwright `add_init_script` inject.
// Output: dist/overlay.iife.js — self-contained, no external CSS, no chunks.
// Svelte component-scoped <style> blocks are inlined into the JS bundle by svelte-plugin's
// default behaviour (no `import './foo.css'` allowed in source — keep all styles in .svelte).

// Detect an actual build invocation via argv. svelte-check + vitest also import
// this config (via vite-plugin-svelte's preprocess + vitest's loader), but they
// don't produce build output — argv-detection is the only reliable distinguisher,
// since their config-load path doesn't pass `command === 'build'` to defineConfig.
//
// `vite build` argv contains 'build'. svelte-check / vitest don't.
const isBuildInvocation = (process.argv ?? []).includes('build');

export default defineConfig(() => {
  if (isBuildInvocation && !process.env.FRONTPROMPT_BUILD_SESSION) {
    throw new Error(
      '\n' +
        '============================================================\n' +
        'ERROR: frontprompt overlay MUST be built via:\n' +
        '\n' +
        '  uv run python -m frontprompt.build\n' +
        '\n' +
        'Direct `bun run build` / `vite build` is NOT supported —\n' +
        'codegen (Pydantic → Zod) and build-info would be missing.\n' +
        'See DEVELOPMENT.md.\n' +
        '============================================================'
    );
  }

  return {
    plugins: [
      svelte({
        // emitCss: false → Svelte-Component-Styles werden als JS-Strings in den
        // Bundle eingebettet und zur Runtime in document.head injectiert (mit
        // hash-classes scoped). Kritisch für inject-via-add_init_script:
        // kein external dist/*.css file.
        emitCss: false,
      }),
      // svelteTesting: fixes Svelte 5 component resolution in vitest jsdom env —
      // ensures browser-side Svelte runtime is used instead of the SSR server bundle.
      svelteTesting(),
    ],
    build: {
      lib: {
        entry: fileURLToPath(new URL('./src/main.ts', import.meta.url)),
        name: 'FrontpromptOverlay',
        formats: ['iife'],
        fileName: () => 'overlay.iife.js',
      },
      outDir: 'dist',
      emptyOutDir: true,
      cssCodeSplit: false,
      minify: false,
      sourcemap: 'inline',
      rollupOptions: {
        output: {
          inlineDynamicImports: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./vitest.setup.ts'],
      // Svelte 5 needs browser-condition resolution for component mounting in jsdom.
      // Without this, svelte resolves to src/index-server.js which throws
      // "mount(...) is not available on the server".
      resolve: {
        conditions: ['browser'],
      },
    },
  };
});

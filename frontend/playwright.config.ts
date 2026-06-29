import { defineConfig } from '@playwright/test';

// Visual-regression + accessibility harness for the overlay.
// Drives the standalone Vite app under ./visual (see visual/README.md).
// Deterministic by construction: fixed viewport + DPR, reduced motion, frozen
// CSS animations, dark scheme — so screenshots are stable across machines.
export default defineConfig({
  testDir: './tests-visual',
  snapshotDir: './tests-visual/__screenshots__',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5180',
    browserName: 'chromium',
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    reducedMotion: 'reduce',
    colorScheme: 'dark',
  },
  expect: {
    toHaveScreenshot: {
      animations: 'disabled',
      // Small tolerance for sub-pixel AA differences across GPU/font stacks.
      maxDiffPixelRatio: 0.02,
    },
  },
  webServer: {
    command: 'bunx vite --config visual/vite.config.ts',
    url: 'http://localhost:5180',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});

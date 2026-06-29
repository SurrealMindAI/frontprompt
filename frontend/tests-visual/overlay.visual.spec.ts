import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const READY_FLAG = '__frontprompt_overlay_ready__';
const HOST = '#__frontprompt_overlay_host__';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  // The overlay sets this flag true after a successful mount (main.ts contract).
  await page.waitForFunction(
    (flag) => (window as unknown as Record<string, boolean>)[flag] === true,
    READY_FLAG,
    { timeout: 15_000 }
  );
  // The overlay fades in on the first rAF tick (.grid--mounted); give it a beat.
  await page.waitForTimeout(300);
});

test('overlay chrome — visual baseline (cold boot)', async ({ page }) => {
  const host = page.locator(HOST);
  await expect(host).toBeAttached();
  await expect(host).toHaveScreenshot('overlay-coldboot.png');
});

test('overlay chrome — no critical axe violations', async ({ page }) => {
  const results = await new AxeBuilder({ page })
    .include(HOST)
    .options({ runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } })
    .analyze();

  // Gate on the highest-severity bucket only. Serious/moderate findings are
  // recorded in the run output for triage without failing the suite, so the
  // baseline reflects the overlay's real current a11y posture honestly.
  const critical = results.violations.filter((v) => v.impact === 'critical');
  const serious = results.violations.filter((v) => v.impact === 'serious');
  if (serious.length > 0) {
    // eslint-disable-next-line no-console
    console.log(`[axe] serious violations (non-gating):\n${JSON.stringify(serious, null, 2)}`);
  }
  expect(critical, JSON.stringify(critical, null, 2)).toEqual([]);
});

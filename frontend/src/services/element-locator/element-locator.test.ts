/**
 * element-locator unit tests (vitest + jsdom).
 *
 * Test-Surface:
 *   - isStableId — predicate für stabile vs framework-generierte IDs
 *   - generateCssSelector — Firefox-style id-first → nth-of-type chain
 *   - buildFingerprint — Scrapling-equivalent shape
 */
import { describe, expect, test } from 'vitest';
import { isStableId } from './stable-id';
import { generateCssSelector } from './selector-path';
import { buildFingerprint } from './element-fingerprint';

// ---------------------------------------------------------------------------
// isStableId
// ---------------------------------------------------------------------------

describe('isStableId', () => {
  test('accepts plain page-author id', () => {
    expect(isStableId('hero-cta')).toBe(true);
    expect(isStableId('main-content')).toBe(true);
    expect(isStableId('user_profile_42')).toBe(true);
  });

  test('rejects React-generated id', () => {
    expect(isStableId('_R_1_')).toBe(false);
    expect(isStableId('react-root')).toBe(false);
  });

  test('rejects Vue / Svelte / Ember generated ids', () => {
    expect(isStableId('v-a1b2c3')).toBe(false);
    expect(isStableId('svelte-h3p2c4')).toBe(false);
    expect(isStableId('ember42')).toBe(false);
  });

  test('rejects aria/tippy/popper auto-ids', () => {
    expect(isStableId('aria-radio-7')).toBe(false);
    expect(isStableId('tippy-1')).toBe(false);
    expect(isStableId('popper-tooltip-2')).toBe(false);
  });

  test('rejects numeric-only id', () => {
    expect(isStableId('123')).toBe(false);
    expect(isStableId('0')).toBe(false);
  });

  test('rejects very long ids (>40 chars — likely hash)', () => {
    expect(isStableId('a'.repeat(41))).toBe(false);
    expect(isStableId('a'.repeat(40))).toBe(true);
  });

  test('rejects empty / null / undefined', () => {
    expect(isStableId(null)).toBe(false);
    expect(isStableId(undefined)).toBe(false);
    expect(isStableId('')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// generateCssSelector
// ---------------------------------------------------------------------------

describe('generateCssSelector', () => {
  test('returns #id for element with stable id', () => {
    document.body.innerHTML = '<div id="hero-cta">x</div>';
    const el = document.getElementById('hero-cta')!;
    expect(generateCssSelector(el)).toBe('#hero-cta');
  });

  test('falls through id-fast-path when id is framework-generated', () => {
    document.body.innerHTML = '<main><div id="react-root">x</div></main>';
    const el = document.getElementById('react-root')!;
    const selector = generateCssSelector(el);
    expect(selector).not.toContain('#');
    expect(selector).toContain('div:nth-of-type');
  });

  test('builds nth-of-type chain when no stable id', () => {
    document.body.innerHTML = `
      <main>
        <section><p>a</p><p>b</p><p>c</p></section>
      </main>
    `;
    const ps = document.querySelectorAll('p');
    // Path inkl. body weil Cap bei 4 → body→main→section→p
    expect(generateCssSelector(ps[1]!)).toBe(
      'body:nth-of-type(1) > main:nth-of-type(1) > section:nth-of-type(1) > p:nth-of-type(2)'
    );
  });

  test('produced selector resolves back to the same element via querySelector', () => {
    document.body.innerHTML = `
      <main>
        <section><p>a</p><p>b</p><p>c</p></section>
      </main>
    `;
    const ps = document.querySelectorAll('p');
    const sel = generateCssSelector(ps[1]!);
    const resolved = document.querySelector(sel);
    expect(resolved).toBe(ps[1]);
  });

  test('caps depth at 4 levels by default', () => {
    document.body.innerHTML =
      '<div><div><div><div><div><div><span>x</span></div></div></div></div></div></div>';
    const span = document.querySelector('span')!;
    const sel = generateCssSelector(span);
    const segments = sel.split(' > ');
    expect(segments.length).toBeLessThanOrEqual(4);
  });

  test('fullPath option emits full chain', () => {
    document.body.innerHTML = '<main><section><p>x</p></section></main>';
    const p = document.querySelector('p')!;
    const sel = generateCssSelector(p, { fullPath: true });
    const segments = sel.split(' > ');
    expect(segments.length).toBeGreaterThan(2);
  });

  test('handles orphan element (no parent in document)', () => {
    const orphan = document.createElement('span');
    expect(generateCssSelector(orphan)).toBe('span:nth-of-type(1)');
  });

  test('escapes special CSS characters in id', () => {
    // CSS.escape via real DOM-supplied helper if available
    document.body.innerHTML = '<div id="weird:id">x</div>';
    const el = document.getElementById('weird:id')!;
    const sel = generateCssSelector(el);
    expect(sel.startsWith('#')).toBe(true);
    // CSS.escape produces '\\:' for ':'
    expect(sel).toContain('\\:');
  });
});

// ---------------------------------------------------------------------------
// buildFingerprint
// ---------------------------------------------------------------------------

describe('buildFingerprint', () => {
  test('captures tag + attributes + text', () => {
    document.body.innerHTML =
      '<section><div id="x" class="foo bar" data-test="t">Hello world</div></section>';
    const el = document.getElementById('x')!;
    const fp = buildFingerprint(el);
    expect(fp.tag).toBe('div');
    expect(fp.attributes).toEqual({ id: 'x', class: 'foo bar', 'data-test': 't' });
    expect(fp.text).toBe('Hello world');
  });

  test('captures path from root to element', () => {
    document.body.innerHTML = '<main><div><span>x</span></div></main>';
    const span = document.querySelector('span')!;
    const fp = buildFingerprint(span);
    const path = fp.path ?? [];
    // jsdom: html → body → main → div → span
    expect(path[path.length - 1]).toBe('span');
    expect(path).toContain('html');
    expect(path).toContain('body');
  });

  test('captures parent_name + siblings + children (Scrapling-format)', () => {
    document.body.innerHTML = `
      <ul>
        <li>a</li>
        <li><a>x</a><b>y</b></li>
        <li>c</li>
      </ul>
    `;
    const middleLi = document.querySelectorAll('li')[1]!;
    const fp = buildFingerprint(middleLi);
    // Scrapling-Format: parent_name (NICHT parent_tag)
    expect(fp.parent_name).toBe('ul');
    // Siblings EXKLUDIERT self (Scrapling-Konvention: `if child != element`)
    expect(fp.siblings).toEqual(['li', 'li']);
    // direct children of middleLi
    expect(fp.children).toEqual(['a', 'b']);
  });

  test('orphan element: parent_name null, parent_attribs empty', () => {
    const orphan = document.createElement('span');
    orphan.textContent = 'foo';
    const fp = buildFingerprint(orphan);
    expect(fp.parent_name).toBeNull();
    expect(fp.parent_attribs).toEqual({});
    expect(fp.parent_text).toBe('');
    expect(fp.siblings).toEqual([]);
    expect(fp.children).toEqual([]);
  });

  test('truncates very long text to 500 chars', () => {
    const long = 'x'.repeat(2000);
    document.body.innerHTML = `<div><span>${long}</span></div>`;
    const span = document.querySelector('span')!;
    const fp = buildFingerprint(span);
    expect(fp.text?.length).toBe(500);
  });

  test('json-roundtrip preserves all fields', () => {
    document.body.innerHTML = '<div id="x" class="a">hi</div>';
    const el = document.getElementById('x')!;
    const fp = buildFingerprint(el);
    const restored = JSON.parse(JSON.stringify(fp));
    expect(restored).toEqual(fp);
  });
});

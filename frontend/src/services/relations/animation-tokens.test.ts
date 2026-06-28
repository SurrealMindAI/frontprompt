/**
 * AnimationTokens — TOKEN constants, colorVarFor, applyTokenDefaults.
 *
 * applyTokenDefaults is tested against a real HTMLElement (jsdom provides it).
 */
import { describe, expect, test } from 'vitest';
import { TOKEN, DEFAULTS, colorVarFor, applyTokenDefaults } from './animation-tokens';

// ---------------------------------------------------------------------------
// TOKEN constant
// ---------------------------------------------------------------------------

describe('TOKEN constants', () => {
  test('TOKEN.dashPeriod is the expected CSS-var name', () => {
    expect(TOKEN.dashPeriod).toBe('--rel-dash-period');
  });

  test('TOKEN.colorRelatesTo is the expected CSS-var name', () => {
    expect(TOKEN.colorRelatesTo).toBe('--rel-color-relates-to');
  });

  test('TOKEN.colorTriggers is the expected CSS-var name', () => {
    expect(TOKEN.colorTriggers).toBe('--rel-color-triggers');
  });

  test('TOKEN.colorPartOf is the expected CSS-var name', () => {
    expect(TOKEN.colorPartOf).toBe('--rel-color-part-of');
  });

  test('TOKEN.colorHover is the expected CSS-var name', () => {
    expect(TOKEN.colorHover).toBe('--rel-color-hover');
  });
});

// ---------------------------------------------------------------------------
// DEFAULTS
// ---------------------------------------------------------------------------

describe('DEFAULTS', () => {
  test('DEFAULTS has a value for every TOKEN key', () => {
    for (const varName of Object.values(TOKEN)) {
      expect(DEFAULTS).toHaveProperty(varName);
    }
  });

  test('DEFAULTS dashPeriod is "1s"', () => {
    expect(DEFAULTS[TOKEN.dashPeriod]).toBe('1s');
  });

  test('DEFAULTS pulsePeriod is "2s"', () => {
    expect(DEFAULTS[TOKEN.pulsePeriod]).toBe('2s');
  });

  test('DEFAULTS strokeWidth is "2px"', () => {
    expect(DEFAULTS[TOKEN.strokeWidth]).toBe('2px');
  });
});

// ---------------------------------------------------------------------------
// colorVarFor
// ---------------------------------------------------------------------------

describe('colorVarFor', () => {
  test('relates_to → var(--rel-color-relates-to)', () => {
    expect(colorVarFor('relates_to')).toBe(`var(${TOKEN.colorRelatesTo})`);
  });

  test('triggers → var(--rel-color-triggers)', () => {
    expect(colorVarFor('triggers')).toBe(`var(${TOKEN.colorTriggers})`);
  });

  test('part_of → var(--rel-color-part-of)', () => {
    expect(colorVarFor('part_of')).toBe(`var(${TOKEN.colorPartOf})`);
  });

  test('unknown kind (exhaustive default) → fallback to relates_to var', () => {
    // Exercises the default branch (exhaustiveness guard). At runtime, an
    // unknown kind that slips through TypeScript's type system hits the default
    // case and returns the relates_to fallback.
    const unknown = 'unknown_kind_phase2' as unknown as import('../../_generated/state').RelationKind;
    expect(colorVarFor(unknown)).toBe(`var(${TOKEN.colorRelatesTo})`);
  });
});

// ---------------------------------------------------------------------------
// applyTokenDefaults
// ---------------------------------------------------------------------------

describe('applyTokenDefaults', () => {
  test('sets all CSS vars from DEFAULTS on an HTMLElement', () => {
    const el = document.createElement('div');
    applyTokenDefaults(el);
    for (const [name, value] of Object.entries(DEFAULTS)) {
      expect(el.style.getPropertyValue(name)).toBe(value);
    }
  });

  test('sets dashPeriod to "1s" on the element', () => {
    const el = document.createElement('div');
    applyTokenDefaults(el);
    expect(el.style.getPropertyValue(TOKEN.dashPeriod)).toBe('1s');
  });

  test('sets colorRelatesTo on the element', () => {
    const el = document.createElement('div');
    applyTokenDefaults(el);
    expect(el.style.getPropertyValue(TOKEN.colorRelatesTo)).toBeTruthy();
  });

  test('does not overwrite values already applied (idempotent)', () => {
    const el = document.createElement('div');
    applyTokenDefaults(el);
    applyTokenDefaults(el);
    // Should still have the correct default value
    expect(el.style.getPropertyValue(TOKEN.dashPeriod)).toBe('1s');
  });
});

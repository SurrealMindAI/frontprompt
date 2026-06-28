/**
 * fingerprintHash — pure function tests.
 *
 * Two fingerprints with the same structural data produce the same hash.
 * Different data produce different hashes. Attribute order doesn't matter
 * (sorted). Missing optional fields use sensible defaults.
 */
import { describe, expect, test } from 'vitest';
import { fingerprintHash } from './fingerprint-hash';
import type { ElementFingerprint } from '../../_generated/state';

function makeFp(overrides: Partial<ElementFingerprint> = {}): ElementFingerprint {
  return {
    tag: 'div',
    path: [],
    attributes: {},
    parent_name: null,
    parent_attribs: {},
    siblings: [],
    text: '',
    ...overrides,
  } as unknown as ElementFingerprint;
}

describe('fingerprintHash — determinism', () => {
  test('same fingerprint always produces same hash', () => {
    const fp = makeFp({ tag: 'button', path: ['div', 'form'] });
    expect(fingerprintHash(fp)).toBe(fingerprintHash(fp));
  });

  test('different fingerprints produce different hashes', () => {
    const fp1 = makeFp({ tag: 'button' });
    const fp2 = makeFp({ tag: 'input' });
    expect(fingerprintHash(fp1)).not.toBe(fingerprintHash(fp2));
  });

  test('attribute order does not affect the hash (sorted key-value pairs)', () => {
    const fp1 = makeFp({ attributes: { id: 'x', class: 'foo' } });
    const fp2 = makeFp({ attributes: { class: 'foo', id: 'x' } });
    expect(fingerprintHash(fp1)).toBe(fingerprintHash(fp2));
  });
});

describe('fingerprintHash — optional fields', () => {
  test('handles missing/undefined path gracefully (uses [])', () => {
    const fp = makeFp({ path: undefined });
    expect(() => fingerprintHash(fp)).not.toThrow();
    const hash = fingerprintHash(fp);
    expect(hash).toContain('"path":[]');
  });

  test('handles missing attributes gracefully', () => {
    const fp = makeFp({ attributes: undefined });
    expect(() => fingerprintHash(fp)).not.toThrow();
    expect(fingerprintHash(fp)).toContain('"attributes":[]');
  });

  test('handles missing parent_name gracefully (uses null)', () => {
    const fp = makeFp({ parent_name: undefined });
    expect(() => fingerprintHash(fp)).not.toThrow();
  });

  test('handles missing siblings gracefully (uses [])', () => {
    const fp = makeFp({ siblings: undefined });
    expect(() => fingerprintHash(fp)).not.toThrow();
  });
});

describe('fingerprintHash — path and siblings influence hash', () => {
  test('different paths produce different hashes', () => {
    const fp1 = makeFp({ path: ['div', 'section'] });
    const fp2 = makeFp({ path: ['div', 'article'] });
    expect(fingerprintHash(fp1)).not.toBe(fingerprintHash(fp2));
  });

  test('different siblings produce different hashes', () => {
    const fp1 = makeFp({ siblings: ['span', 'div'] });
    const fp2 = makeFp({ siblings: ['p', 'div'] });
    expect(fingerprintHash(fp1)).not.toBe(fingerprintHash(fp2));
  });

  test('parent_name influences hash', () => {
    const fp1 = makeFp({ parent_name: 'form' });
    const fp2 = makeFp({ parent_name: 'section' });
    expect(fingerprintHash(fp1)).not.toBe(fingerprintHash(fp2));
  });
});

describe('fingerprintHash — text and rect excluded', () => {
  test('text field does NOT influence hash (excluded by design)', () => {
    // fingerprintHash should produce the same result regardless of text content
    const fp1 = makeFp({ tag: 'p', text: 'Hello world' } as any);
    const fp2 = makeFp({ tag: 'p', text: 'Completely different text' } as any);
    // Both should produce same hash since text is excluded
    expect(fingerprintHash(fp1)).toBe(fingerprintHash(fp2));
  });
});

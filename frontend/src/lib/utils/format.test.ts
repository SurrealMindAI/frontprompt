/**
 * formatCount — all branches including k/M/G suffixes.
 */
import { describe, expect, test } from 'vitest';
import { formatCount } from './format';

describe('formatCount < 1000 (no suffix)', () => {
  test('0 → "0"', () => expect(formatCount(0)).toBe('0'));
  test('1 → "1"', () => expect(formatCount(1)).toBe('1'));
  test('42 → "42"', () => expect(formatCount(42)).toBe('42'));
  test('999 → "999"', () => expect(formatCount(999)).toBe('999'));
});

describe('formatCount ≥ 1000 and < 1 000 000 (k suffix)', () => {
  test('1000 → "1.00k"', () => expect(formatCount(1_000)).toBe('1.00k'));
  test('1234 → "1.23k"', () => expect(formatCount(1_234)).toBe('1.23k'));
  test('9999 → "10.00k"', () => expect(formatCount(9_999)).toBe('10.00k'));
  test('999999 → "1000.00k"', () => expect(formatCount(999_999)).toBe('1000.00k'));
});

describe('formatCount ≥ 1 000 000 and < 1 000 000 000 (M suffix)', () => {
  test('1 000 000 → "1.00M"', () => expect(formatCount(1_000_000)).toBe('1.00M'));
  test('1 234 567 → "1.23M"', () => expect(formatCount(1_234_567)).toBe('1.23M'));
  test('500 000 000 → "500.00M"', () => expect(formatCount(500_000_000)).toBe('500.00M'));
  test('999 999 999 → "1000.00M"', () => expect(formatCount(999_999_999)).toBe('1000.00M'));
});

describe('formatCount ≥ 1 000 000 000 (G suffix)', () => {
  test('1 000 000 000 → "1.00G"', () => expect(formatCount(1_000_000_000)).toBe('1.00G'));
  test('2 500 000 000 → "2.50G"', () => expect(formatCount(2_500_000_000)).toBe('2.50G'));
  test('1 234 567 890 → "1.23G"', () => expect(formatCount(1_234_567_890)).toBe('1.23G'));
});

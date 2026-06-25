import { afterEach, describe, expect, it } from 'vitest';

import { PANEL_CONFIGS } from '../../backend-state/panel-state.svelte';
import {
  FRAME_INSETS,
  applyHostFrameInset,
  removeHostFrameInset,
  setAboutBlankBackdrop,
} from './host-frame';

afterEach(() => {
  removeHostFrameInset();
  setAboutBlankBackdrop(false);
  document.documentElement.removeAttribute('style');
});

describe('FRAME_INSETS', () => {
  it('derives each side from the panel tabThickness (single source of truth)', () => {
    expect(FRAME_INSETS).toEqual({
      top: PANEL_CONFIGS.top.tabThickness,
      right: PANEL_CONFIGS.right.tabThickness,
      bottom: PANEL_CONFIGS.bottom.tabThickness,
      left: PANEL_CONFIGS.left.tabThickness,
    });
  });
});

describe('applyHostFrameInset', () => {
  it('insets <html> by the frame insets with box-sizing border-box', () => {
    applyHostFrameInset();
    const s = document.documentElement.style;
    expect(s.getPropertyValue('box-sizing')).toBe('border-box');
    expect(s.getPropertyValue('padding-top')).toBe(`${FRAME_INSETS.top}px`);
    expect(s.getPropertyValue('padding-right')).toBe(`${FRAME_INSETS.right}px`);
    expect(s.getPropertyValue('padding-bottom')).toBe(`${FRAME_INSETS.bottom}px`);
    expect(s.getPropertyValue('padding-left')).toBe(`${FRAME_INSETS.left}px`);
  });

  it('sets the inset declarations as !important so host author styles cannot override', () => {
    applyHostFrameInset();
    const s = document.documentElement.style;
    expect(s.getPropertyPriority('box-sizing')).toBe('important');
    expect(s.getPropertyPriority('padding-top')).toBe('important');
    expect(s.getPropertyPriority('padding-right')).toBe('important');
    expect(s.getPropertyPriority('padding-bottom')).toBe('important');
    expect(s.getPropertyPriority('padding-left')).toBe('important');
  });

  it('is idempotent — applying twice yields the same single inset', () => {
    applyHostFrameInset();
    applyHostFrameInset();
    expect(document.documentElement.style.getPropertyValue('padding-left')).toBe(
      `${FRAME_INSETS.left}px`
    );
  });

  it('accepts custom insets', () => {
    applyHostFrameInset({ top: 1, right: 2, bottom: 3, left: 4 });
    const s = document.documentElement.style;
    expect(s.getPropertyValue('padding-top')).toBe('1px');
    expect(s.getPropertyValue('padding-right')).toBe('2px');
    expect(s.getPropertyValue('padding-bottom')).toBe('3px');
    expect(s.getPropertyValue('padding-left')).toBe('4px');
  });
});

describe('removeHostFrameInset', () => {
  it('clears every inset declaration', () => {
    applyHostFrameInset();
    removeHostFrameInset();
    const s = document.documentElement.style;
    expect(s.getPropertyValue('box-sizing')).toBe('');
    expect(s.getPropertyValue('padding-top')).toBe('');
    expect(s.getPropertyValue('padding-right')).toBe('');
    expect(s.getPropertyValue('padding-bottom')).toBe('');
    expect(s.getPropertyValue('padding-left')).toBe('');
  });
});

describe('setAboutBlankBackdrop', () => {
  it('paints a black !important backdrop on <html> when enabled', () => {
    setAboutBlankBackdrop(true);
    const s = document.documentElement.style;
    // jsdom normalises the #000 shorthand to rgb() on read-back.
    expect(s.getPropertyValue('background-color')).toBe('rgb(0, 0, 0)');
    expect(s.getPropertyPriority('background-color')).toBe('important');
  });

  it('clears the backdrop when disabled', () => {
    setAboutBlankBackdrop(true);
    setAboutBlankBackdrop(false);
    expect(document.documentElement.style.getPropertyValue('background-color')).toBe('');
  });
});

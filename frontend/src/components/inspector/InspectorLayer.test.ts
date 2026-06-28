/**
 * InspectorLayer smoke tests.
 *
 * Tests: rendering, click-cancel when no hovered element, custom props,
 * pointer move, wheel forwarding.
 *
 * Note: jsdom does not implement document.elementsFromPoint(). We polyfill it
 * to return [] (no elements at any point) so findTarget() always returns null.
 * This means pointer moves never "find" a target, so click always goes to the
 * cancel path. This is correct behavior for the jsdom environment.
 */
const send = vi.hoisted(() => vi.fn());
vi.mock('../../bridge/bridge.svelte', () => ({ bridge: { send } }));

import { describe, expect, test, afterEach, beforeEach, vi } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/svelte';
import InspectorLayer from './InspectorLayer.svelte';
import { backendState } from '../../backend-state/backend-state.svelte';

// jsdom does not implement document.elementsFromPoint — define it globally
// so the component can call it. We control its return value per test.
let mockElementsFromPoint: ReturnType<typeof vi.fn>;

afterEach(() => {
  cleanup();
  send.mockClear();
  vi.restoreAllMocks();
});

beforeEach(() => {
  backendState.inspector.picks = [];
  backendState.inspector.regions = [];
  // Define elementsFromPoint on document (jsdom doesn't implement it).
  // Default: returns [] so findTarget() always returns null.
  mockElementsFromPoint = vi.fn().mockReturnValue([]);
  Object.defineProperty(document, 'elementsFromPoint', {
    value: mockElementsFromPoint,
    writable: true,
    configurable: true,
  });
});

describe('InspectorLayer — rendering', () => {
  test('renders .inspector-layer div', () => {
    const { container } = render(InspectorLayer);
    expect(container.querySelector('.inspector-layer')).not.toBeNull();
  });

  test('does not render HighlightBorder when no element is hovered (rect is null)', () => {
    const { container } = render(InspectorLayer);
    // HighlightBorder is only rendered when rect is non-null (after pointermove)
    expect(container.querySelector('.inspector-border')).toBeNull();
  });
});

describe('InspectorLayer — click behavior (no hovered element)', () => {
  test('click without prior pointermove calls backendState.inspector.cancel', () => {
    const cancelSpy = vi.spyOn(backendState.inspector, 'cancel');
    const { container } = render(InspectorLayer);
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    fireEvent.click(layer);
    expect(cancelSpy).toHaveBeenCalled();
    cancelSpy.mockRestore();
  });

  test('click with custom onCancel prop calls it instead of default cancel', () => {
    const customCancel = vi.fn();
    const { container } = render(InspectorLayer, { props: { onCancel: customCancel } });
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    fireEvent.click(layer);
    expect(customCancel).toHaveBeenCalled();
  });

  test('click with custom onPickCaptured does not throw even if no hoveredEl', () => {
    const customPick = vi.fn();
    const customCancel = vi.fn();
    const { container } = render(InspectorLayer, {
      props: { onPickCaptured: customPick, onCancel: customCancel },
    });
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    expect(() => fireEvent.click(layer)).not.toThrow();
    // No hovered element → cancel was called, not pick
    expect(customCancel).toHaveBeenCalled();
    expect(customPick).not.toHaveBeenCalled();
  });
});

describe('InspectorLayer — pointer move', () => {
  test('pointermove event does not throw (findTarget returns null with mocked elementsFromPoint)', () => {
    // document.elementsFromPoint is mocked to return [] → findTarget returns null
    const { container } = render(InspectorLayer);
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    expect(() => {
      fireEvent.pointerMove(layer, { clientX: 100, clientY: 100 });
    }).not.toThrow();
  });

  test('pointermove runs onPointerMove code path (target=null → stopTracking, rect=null)', () => {
    // With elementsFromPoint mocked to [], target=null → hoveredEl stays null
    // The branch `if (target !== hoveredEl)` is taken (null !== null is false, so first move is skipped)
    // Actually: initial hoveredEl=null, target=null → target === hoveredEl → no update
    // Second move from different coords: same outcome
    const onCancel = vi.fn();
    const { container } = render(InspectorLayer, { props: { onCancel } });
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    fireEvent.pointerMove(layer, { clientX: 10, clientY: 10 });
    fireEvent.pointerMove(layer, { clientX: 200, clientY: 200 });
    expect(layer).toBeTruthy(); // component is still alive
  });

  test('multiple pointermoves do not accumulate errors', () => {
    const { container } = render(InspectorLayer);
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    expect(() => {
      fireEvent.pointerMove(layer, { clientX: 10, clientY: 10 });
      fireEvent.pointerMove(layer, { clientX: 20, clientY: 20 });
      fireEvent.pointerMove(layer, { clientX: 30, clientY: 30 });
    }).not.toThrow();
  });

  test('pointermove with real element in DOM allows findTarget to run full loop', () => {
    // Override mock to return a real DOM element so findTarget iterates the loop
    const realEl = document.createElement('div');
    realEl.id = 'target-test';
    document.body.appendChild(realEl);
    mockElementsFromPoint.mockReturnValue([realEl]);

    const onPickCaptured = vi.fn();
    const { container } = render(InspectorLayer, { props: { onPickCaptured } });
    const layer = container.querySelector('.inspector-layer') as HTMLElement;

    // After pointermove, hoveredEl = realEl (no fp-overlay, no inspector-layer class)
    expect(() => fireEvent.pointerMove(layer, { clientX: 50, clientY: 50 })).not.toThrow();

    // Click → hoveredEl is set → builds Pick and calls onPickCaptured
    expect(() => fireEvent.click(layer)).not.toThrow();

    document.body.removeChild(realEl);
  });
});

describe('InspectorLayer — wheel behavior', () => {
  test('wheel event calls forwardWheel without throwing', () => {
    // forwardWheel also calls document.elementsFromPoint — already mocked to []
    // so it returns early without error (underCursor = undefined → return)
    const { container } = render(InspectorLayer);
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    expect(() => {
      fireEvent.wheel(layer, { deltaY: 100, clientX: 0, clientY: 0 });
    }).not.toThrow();
  });
});

describe('InspectorLayer — findTarget filtering', () => {
  test('fp-overlay element is skipped by findTarget (cancel is called)', () => {
    // Create an fp-overlay element — findTarget should skip it and return null
    const fpOverlay = document.createElement('fp-overlay');
    const innerDiv = document.createElement('div');
    fpOverlay.appendChild(innerDiv);
    document.body.appendChild(fpOverlay);

    // Mock elementsFromPoint to return [innerDiv] (which is inside fp-overlay)
    // closest('fp-overlay') will return fpOverlay (innerDiv is inside it)
    mockElementsFromPoint.mockReturnValue([innerDiv]);

    const cancelSpy = vi.spyOn(backendState.inspector, 'cancel');
    const { container } = render(InspectorLayer);
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    fireEvent.pointerMove(layer, { clientX: 50, clientY: 50 });
    fireEvent.click(layer);

    // fp-overlay skipped → hoveredEl remains null → cancel called
    expect(cancelSpy).toHaveBeenCalled();
    cancelSpy.mockRestore();
    document.body.removeChild(fpOverlay);
  });

  test('element with inspector-layer class is skipped by findTarget', () => {
    // Inspector-layer div skipped → findTarget returns null → cancel
    const layerEl = document.createElement('div');
    layerEl.classList.add('inspector-layer');
    document.body.appendChild(layerEl);

    mockElementsFromPoint.mockReturnValue([layerEl]);

    const cancelSpy = vi.spyOn(backendState.inspector, 'cancel');
    const { container } = render(InspectorLayer);
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    fireEvent.pointerMove(layer, { clientX: 50, clientY: 50 });
    fireEvent.click(layer);

    expect(cancelSpy).toHaveBeenCalled();
    cancelSpy.mockRestore();
    document.body.removeChild(layerEl);
  });
});

describe('InspectorLayer — default handlers (no custom props)', () => {
  test('submitPick is called via default onPickCaptured when hoveredEl is a real element', () => {
    // Override mock to return a real DOM element → findTarget finds it → onClick builds pick
    const realEl = document.createElement('div');
    realEl.id = 'pick-target';
    document.body.appendChild(realEl);
    mockElementsFromPoint.mockReturnValue([realEl]);

    const submitPickSpy = vi.spyOn(backendState.inspector, 'submitPick').mockReturnValue('test-pick-id');
    const { container } = render(InspectorLayer);
    const layer = container.querySelector('.inspector-layer') as HTMLElement;

    // Move to set hoveredEl = realEl
    fireEvent.pointerMove(layer, { clientX: 50, clientY: 50 });
    // Click with hoveredEl set → calls handlePick → default submitPick
    fireEvent.click(layer);

    expect(submitPickSpy).toHaveBeenCalled();
    submitPickSpy.mockRestore();
    document.body.removeChild(realEl);
  });

  test('cancel is called via default onCancel when hoveredEl is null (no elements from point)', () => {
    // elementsFromPoint returns [] → hoveredEl stays null → onClick calls cancel
    const cancelSpy = vi.spyOn(backendState.inspector, 'cancel');
    const { container } = render(InspectorLayer);
    const layer = container.querySelector('.inspector-layer') as HTMLElement;
    fireEvent.click(layer);
    expect(cancelSpy).toHaveBeenCalled();
    cancelSpy.mockRestore();
  });
});

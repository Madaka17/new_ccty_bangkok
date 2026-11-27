import { describe, it, expect } from 'vitest';
import { initialShown, shouldShow } from './useReveal.js';

describe('initialShown', () => {
  it('reports shown straight away when IntersectionObserver is missing, so content never stays hidden', () => {
    expect(initialShown(false)).toBe(true);
  });

  it('starts hidden when IntersectionObserver exists, until the element scrolls into view', () => {
    expect(initialShown(true)).toBe(false);
  });
});

describe('shouldShow', () => {
  const entry = (over = {}) => ({ isIntersecting: true, intersectionRatio: 0.2, boundingClientRect: { height: 300 }, ...over });

  it('shows once 15% of the element is in view', () => {
    expect(shouldShow(entry({ intersectionRatio: 0.2 }), 800)).toBe(true);
  });

  it('keeps waiting while less than 15% is in view', () => {
    expect(shouldShow(entry({ intersectionRatio: 0.05 }), 800)).toBe(false);
  });

  it('does nothing when the element is not intersecting', () => {
    expect(shouldShow(entry({ isIntersecting: false, intersectionRatio: 0 }), 800)).toBe(false);
  });

  it('shows a box taller than five viewports as soon as it touches the screen', () => {
    expect(shouldShow(entry({ intersectionRatio: 0.01, boundingClientRect: { height: 4001 } }), 800)).toBe(true);
  });

  it('does not treat a box of exactly five viewports as tall', () => {
    expect(shouldShow(entry({ intersectionRatio: 0.01, boundingClientRect: { height: 4000 } }), 800)).toBe(false);
  });
});

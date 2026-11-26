import { describe, it, expect } from 'vitest';
import { initialShown } from './useReveal.js';

describe('initialShown', () => {
  it('reports shown straight away when IntersectionObserver is missing, so content never stays hidden', () => {
    expect(initialShown(false)).toBe(true);
  });

  it('starts hidden when IntersectionObserver exists, until the element scrolls into view', () => {
    expect(initialShown(true)).toBe(false);
  });
});

import { describe, it, expect } from 'vitest';
import { subscriberSentence } from './alertText.js';

describe('subscriberSentence', () => {
  it('hides the count when there are no subscribers', () => {
    expect(subscriberSentence({ subscribers: 0 })).toBe('');
  });
  it('hides the count when the field is missing', () => {
    expect(subscriberSentence({})).toBe('');
    expect(subscriberSentence(null)).toBe('');
  });
  it('states the count in plain Thai when there is at least one', () => {
    expect(subscriberSentence({ subscribers: 3 })).toBe(' · มีคนเปิดรับแจ้งเตือน 3 เครื่อง');
  });
});

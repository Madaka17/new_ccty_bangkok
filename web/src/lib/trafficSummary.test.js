import { describe, expect, test } from 'vitest';
import { bmaCountsLive, pickTrafficSummary } from './trafficSummary.js';

const bmaUp = { ready: true, online: true, is_bma: true, flow_index: 72, updated_at: 1791900000 };
const bmaDown = { ready: true, online: false, is_bma: true, flow_index: null, updated_at: 1791458052 };
const longdo = { ready: true, online: true, flow_index: 86, updated_at: 1791900095 };

describe('pickTrafficSummary', () => {
  test('uses the BMA cameras while the BMA site is up', () => {
    expect(pickTrafficSummary('bma', bmaUp, longdo)).toBe(bmaUp);
  });

  test('uses the Longdo roads while the BMA site is down', () => {
    expect(pickTrafficSummary('bma', bmaDown, longdo)).toBe(longdo);
  });

  test('keeps the BMA summary when the site is down and Longdo has nothing yet', () => {
    expect(pickTrafficSummary('bma', bmaDown, null)).toBe(bmaDown);
  });

  test('uses Longdo when BMA has not answered yet', () => {
    expect(pickTrafficSummary('bma', null, longdo)).toBe(longdo);
  });
});

describe('bmaCountsLive', () => {
  test('is false while YOLO is off', () => {
    expect(bmaCountsLive({ yolo_enabled: false })).toBe(false);
  });

  test('is true while YOLO is on', () => {
    expect(bmaCountsLive({ yolo_enabled: true })).toBe(true);
  });

  test('is true when the server does not send the flag yet', () => {
    expect(bmaCountsLive(undefined)).toBe(true);
  });
});

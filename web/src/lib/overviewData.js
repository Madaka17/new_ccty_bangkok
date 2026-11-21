// Pure data shaping for the overview cards on the dashboard.
// No DOM, no fetch: inputs are the JSON the API already returns.

const DAY_KEY = /^(\d{4})-(\d{2})-(\d{2})$/;
const HOUR_KEY = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/;

function hourLabel(key) {
  const m = HOUR_KEY.exec(key);
  return m ? `${m[4]} น.` : key;
}

function keyLabel(key) {
  const day = DAY_KEY.exec(key);
  if (day) return `${Number(day[3])}/${Number(day[2])}`;
  return hourLabel(key);
}

// Epoch seconds for 'YYYY-MM-DD HH:MM[:SS]' (or 'T' separator), read as local time. null if unparseable.
function localEpochSeconds(text) {
  const m = HOUR_KEY.exec(String(text || ''));
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5])).getTime() / 1000;
}

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);

// /api/ai/history -> one row per key, summed across cameras.
export function sumVehicleHistory(history) {
  if (!history || !Array.isArray(history.keys)) return [];
  const cameras = Array.isArray(history.cameras) ? history.cameras : [];
  return history.keys.map((key) => {
    let cars = 0;
    let motorcycles = 0;
    for (const cam of cameras) {
      const cell = cam?.series?.[key];
      if (!cell) continue;
      cars += num(cell.cars);
      motorcycles += num(cell.motorcycles);
    }
    return { key, label: keyLabel(key), cars, motorcycles };
  });
}

// bma.hourly_trends -> per-camera averages per hour, ready for a line chart.
export function bmaHourlyLines(hourly) {
  if (!Array.isArray(hourly)) return [];
  const out = [];
  for (const row of hourly) {
    if (!row || !row.hour) continue;
    const t = localEpochSeconds(row.hour);
    if (t == null) continue;
    const cams = Math.max(1, num(row.cam_count));
    out.push({
      t,
      label: hourLabel(row.hour),
      cars: Math.round((num(row.cars) / cams) * 10) / 10,
      motorcycles: Math.round((num(row.motorcycles) / cams) * 10) / 10,
    });
  }
  return out;
}

// incidents.camera + incidents.longdo -> one list, newest first.
export function incidentRows(incidents) {
  if (!incidents) return [];
  const cam = (Array.isArray(incidents.camera) ? incidents.camera : []).map((r, i) => ({
    id: r.id ?? `camera-${i}`,
    title: r.title,
    kind: r.kind || 'accident',
    source: 'camera',
    image: r.image || null,
    at: r.ts ?? null,
  }));
  const lon = (Array.isArray(incidents.longdo) ? incidents.longdo : []).map((r, i) => ({
    id: r.id ?? `longdo-${i}`,
    title: r.title,
    kind: r.kind || 'accident',
    source: 'longdo',
    image: r.image || null,
    at: localEpochSeconds(r.start),
  }));
  return sortRows([...cam, ...lon], 'at', 'desc');
}

// Returns a new array sorted by rows[key]; null/undefined always go last.
export function sortRows(rows, key, dir = 'asc') {
  const sign = dir === 'desc' ? -1 : 1;
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    const aMissing = av == null;
    const bMissing = bv == null;
    if (aMissing && bMissing) return 0;
    if (aMissing) return 1;
    if (bMissing) return -1;
    if (av < bv) return -1 * sign;
    if (av > bv) return 1 * sign;
    return 0;
  });
}

function csvCell(value) {
  if (value == null) return '';
  const s = String(value);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

// Excel-friendly CSV: UTF-8 BOM so Thai reads correctly, CRLF line ends.
export function toCsv(rows, columns) {
  const header = columns.map((c) => csvCell(c.label)).join(',');
  const body = rows.map((row) => columns.map((c) => csvCell(row[c.key])).join(','));
  return ['﻿' + header, ...body].join('\r\n');
}

// Step between shown chart labels so at most `max` are drawn.
export function thinLabels(n, max = 12) {
  return Math.max(1, Math.ceil(n / max));
}

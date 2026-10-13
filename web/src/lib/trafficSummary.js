// Which traffic summary the dashboard shows: the BMA camera count or the Longdo road colours.
// While the BMA site is down its summary has no flow and an old time, so Longdo stands in when it has data.
export function pickTrafficSummary(source, bmaSummary, longdoSummary) {
  const bmaLive = bmaSummary?.online ? bmaSummary : null;
  return source === 'bma' ? (bmaLive || longdoSummary || bmaSummary) : (longdoSummary || bmaSummary);
}

// False while YOLO is off: the BMA scanner then reports no counts, so the cameras cannot stand for traffic.
export function bmaCountsLive(scanStatus) {
  return scanStatus?.yolo_enabled !== false;
}

// Distance calculation using Haversine formula (km)
export function haversineDistance(lat1, lon1, lat2, lon2) {
  if (!lat1 || !lon1 || !lat2 || !lon2) return 999;
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// Extract stations that are at overflow (>100%) or high alert (>85-90%)
export function getRiskWaterStations(waterSummary) {
  if (!waterSummary) return [];
  const stations = [];

  // Rivers
  (waterSummary.river || []).forEach((r) => {
    if ((r.level === 'overflow' || r.level === 'high') && r.lat && r.lng) {
      stations.push({
        id: r.id,
        name: r.name,
        type: 'river',
        river: r.river,
        district: r.district,
        province: r.province,
        storagePct: r.storage_pct,
        level: r.level, // 'overflow' or 'high'
        diffText: r.diff_text,
        lat: r.lat,
        lng: r.lng,
      });
    }
  });

  // Canals
  (waterSummary.canals || []).forEach((c) => {
    if ((c.level === 'overflow' || c.level === 'high') && c.lat && c.lng) {
      stations.push({
        id: c.id,
        name: c.name,
        type: 'canal',
        district: c.district,
        province: c.province,
        storagePct: c.storage_pct,
        level: c.level,
        lat: c.lat,
        lng: c.lng,
      });
    }
  });

  return stations;
}

// Match camera to nearest high-risk water station or critical flood hotspot
export function matchCameraFloodRisk(cam, riskStations) {
  if (!riskStations || !riskStations.length) return null;

  const lat = cam.latitude || cam.lat;
  const lng = cam.longitude || cam.lng;
  const text = `${cam.short_title || ''} ${cam.title || ''} ${cam.district || ''} ${cam.road || ''}`.toLowerCase();

  let closest = null;
  let minDistance = 999;

  for (const st of riskStations) {
    if (!st.lat || !st.lng) continue;
    const d = haversineDistance(lat, lng, st.lat, st.lng);
    const maxRange = st.level === 'overflow' ? 3.6 : 2.4;

    if (d <= maxRange) {
      // Prioritize overflow station, or closer distance
      if (
        !closest ||
        (st.level === 'overflow' && closest.level !== 'overflow') ||
        (st.level === closest.level && d < minDistance)
      ) {
        closest = st;
        minDistance = d;
      }
    }
  }

  // Keyword-based fallback for critical known Google Flood Hub / telemetry hotspots
  if (!closest) {
    if (text.includes('บางบัว') || text.includes('คลองลาดพร้าว') || text.includes('เกษตร') || text.includes('งามวงศ์วาน')) {
      const bLatPhrao = riskStations.find((s) => s.name.includes('ลาดพร้าว') || s.district?.includes('บางเขน'));
      if (bLatPhrao) {
        closest = bLatPhrao;
        minDistance = 2.0;
      }
    } else if (text.includes('พระประแดง') || text.includes('บางกระเจ้า') || text.includes('ลัดบางยอ')) {
      const bPhraPradaeng = riskStations.find((s) => s.district?.includes('พระประแดง'));
      if (bPhraPradaeng) {
        closest = bPhraPradaeng;
        minDistance = 1.5;
      }
    } else if (text.includes('บางนา-ตราด') || text.includes('บางนาตราด') || text.includes('อุดมสุข')) {
      const bBangna = riskStations.find((s) => s.district?.includes('บางนา'));
      if (bBangna) {
        closest = bBangna;
        minDistance = 1.5;
      }
    } else if (text.includes('มหาสวัสดิ์') || text.includes('บางกรวย') || text.includes('สวนผัก')) {
      const bMaha = riskStations.find((s) => s.name.includes('มหาสวัสดิ์') || s.district?.includes('ตลิ่งชัน'));
      if (bMaha) {
        closest = bMaha;
        minDistance = 2.0;
      }
    }
  }

  if (!closest) return null;

  const isOverflow = closest.level === 'overflow';
  return {
    isRisk: true,
    level: closest.level, // 'overflow' | 'high'
    isOverflow,
    stationName: closest.name,
    stationType: closest.type === 'canal' ? 'คลอง' : 'แม่น้ำ',
    district: closest.district,
    storagePct: Math.round(closest.storagePct || 0),
    distanceKm: Math.round(minDistance * 10) / 10,
    badgeText: isOverflow ? '🌊 ล้นตลิ่ง' : '⚠️ เฝ้าระวังสูง',
    label: isOverflow
      ? `เสี่ยงน้ำล้นตลิ่ง (${closest.name} ${Math.round(closest.storagePct || 0)}%)`
      : `เฝ้าระวังระดับน้ำสูง (${closest.name} ${Math.round(closest.storagePct || 0)}%)`,
    tagColor: isOverflow ? 'red' : 'amber',
  };
}

// Augment camera list with flood risk data
export function enrichCamerasWithFloodRisk(cameras, waterSummary) {
  if (!cameras || !cameras.length) return [];
  const riskStations = getRiskWaterStations(waterSummary);
  if (!riskStations.length) return cameras;

  return cameras.map((cam) => {
    const floodRisk = matchCameraFloodRisk(cam, riskStations);
    return {
      ...cam,
      floodRisk,
    };
  });
}

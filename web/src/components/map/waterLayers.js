// The water layers of the traffic map ("น้ำ" in the side panel), one hook each: road-flood sensors, the AI flood
// watch on the BMA cameras, reports from the public, Traffy Fondue reports, highway flood tickets and the
// river / canal gauges. Each polls its feed while the page is open and keeps one marker per point.
import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { fetchFloodStatus, fetchFloodStations, fetchFloodCameras, fetchUserReports, fetchFloodReports, fetchHdmsFloods } from '../../lib/api.js';
import { FLOOD_STYLE, esc, CAM_FLOOD_STYLE, CAM_WET, agoTh, USER_REPORT_COLOR, REPORT_COLOR, REPORT_FRESH_S, HDMS_COLOR, GAUGE_STYLE } from './markers.js';
import { fmtTime } from '../dashboard/format.js';

export function useRoadFloodLayer(mapRef, isActive) {
  // BMA road-flood sensors (Bangkok)
  const [showFlood, setShowFlood] = useState(false);
  const [floodDry, setFloodDry] = useState(false);
  const [flood, setFlood] = useState(null);
  const [floodAll, setFloodAll] = useState(null);
  const floodMarkersRef = useRef([]);

  // Road-flood sensors: the wet ones every minute, the whole network only when dry ones are shown
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchFloodStatus().then((d) => alive && setFlood(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  useEffect(() => {
    if (!isActive || !floodDry) return;
    let alive = true;
    fetchFloodStations({ limit: 1000 }).then((d) => alive && setFloodAll(d.items)).catch(() => {});
    const id = setInterval(() => fetchFloodStations({ limit: 1000 }).then((d) => alive && setFloodAll(d.items)).catch(() => {}), 300000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive, floodDry]);

  const floodPoints = useMemo(() => {
    if (!flood) return [];
    return floodDry && floodAll ? floodAll : flood.wet;
  }, [flood, floodAll, floodDry]);

  const floodCounts = flood?.counts || { flood: 0, slight: 0, normal: 0, offline: 0 };
  const floodTop = useMemo(() => (flood?.wet || []).slice(0, 6), [flood]);

  // One marker per road sensor: a depth badge when wet, a small dot when dry or broken
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of floodMarkersRef.current) m.remove();
    floodMarkersRef.current = [];
    if (!showFlood) return;
    for (const st of floodPoints) {
      const sty = FLOOD_STYLE[st.status] || FLOOD_STYLE.offline;
      const wet = st.status === 'flood' || st.status === 'slight';
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `${st.short_name}: ${sty.label}${st.level_cm != null ? ` ${st.level_cm} ซม.` : ''}`;
      if (wet) {
        el.style.cssText = `display:flex;align-items:center;gap:3px;padding:2px 7px 2px 5px;border-radius:999px;background:${sty.color};color:#fff;font:700 11px/1 var(--font-sans);border:2px solid #fff;box-shadow:0 0 0 5px ${sty.ring},0 1px 4px rgba(15,23,42,.35);cursor:pointer`;
        el.innerHTML = `<span style="font-size:11px">💧</span><span>${Math.round(st.level_cm)} ซม.</span>`;
      } else {
        el.style.cssText = `width:12px;height:12px;border-radius:999px;background:${sty.color};border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.3);cursor:pointer;padding:0;opacity:.85`;
      }
      const popup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '280px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b>${esc(st.short_name)}</b>
          ${st.road ? `<br><span style="color:#64748b">${esc(st.road)}${st.district ? ` · เขต${esc(st.district)}` : ''}</span>` : ''}
          <br><span style="color:${sty.color};font-weight:700">${sty.label}</span>
          ${st.level_cm != null && st.status !== 'offline' ? ` <b>${st.level_cm} ซม.</b>` : ''}
          ${st.trend_th ? ` <span style="color:#64748b">· ${esc(st.trend_th)}</span>` : ''}
          ${st.kind === 'tunnel' ? `<br><span style="color:#64748b">อุโมงค์ทางลอด${st.side ? ` · ${esc(st.side)}` : ''}</span>` : ''}
          ${st.started ? `<br><span style="color:#64748b">เริ่มท่วม ${esc(st.started)}</span>` : ''}
          ${st.max_cm ? `<br><span style="color:#64748b">สูงสุด ${st.max_cm} ซม.</span>` : ''}
          ${st.ts_th ? `<br><span style="color:#94a3b8;font-size:11px">ข้อมูล ${esc(st.ts_th)} · สำนักการระบายน้ำ กทม.</span>` : ''}
        </div>`
      );
      floodMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([st.lng, st.lat]).setPopup(popup).addTo(map));
    }
  }, [floodPoints, showFlood]);
  return { floodCounts, floodTop, showFlood, setShowFlood, floodDry, setFloodDry, flood };
}

export function useCamFloodLayer(mapRef, isActive) {
  // AI flood watch on every BMA camera: on by default, the map shows only the cameras with water
  const [showCamFlood, setShowCamFlood] = useState(true);
  const [camFloodDry, setCamFloodDry] = useState(false);
  const [camFlood, setCamFlood] = useState(null);
  const camFloodMarkersRef = useRef([]);

  // AI flood watch on the BMA cameras; a camera is re-checked every ~10 min (5 while it has water)
  useEffect(() => {
    if (!isActive || !showCamFlood) return;
    let alive = true;
    const tick = () => fetchFloodCameras({ all: camFloodDry }).then((d) => alive && setCamFlood(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive, showCamFlood, camFloodDry]);

  // One pill per camera the AI saw water on (plus a dot per dry / unclear camera when asked); faded when the frame is old
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of camFloodMarkersRef.current) m.remove();
    camFloodMarkersRef.current = [];
    if (!showCamFlood || !camFlood) return;
    for (const c of camFlood.items || []) {
      if (c.lat == null || c.lng == null) continue;
      const sty = CAM_FLOOD_STYLE[c.level] || CAM_FLOOD_STYLE.unclear;
      const wet = CAM_WET.includes(c.level);
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `กล้อง ${c.title}: ${sty.label}${c.stale ? ' (ภาพเก่า)' : ''}`;
      if (wet) {
        el.style.cssText = `display:flex;align-items:center;gap:3px;padding:2px 7px 2px 5px;border-radius:6px;background:${sty.color};color:#fff;font:700 11px/1 var(--font-sans);border:2px ${c.stale ? 'dashed' : 'solid'} #fff;box-shadow:0 0 0 ${c.stale ? 2 : 5}px ${sty.color}44,0 1px 4px rgba(15,23,42,.35);cursor:pointer;opacity:${c.stale ? 0.6 : 1}`;
        el.innerHTML = `<span style="font-size:11px">📷</span><span>${esc(sty.label)}</span>`;
      } else {
        el.style.cssText = `width:10px;height:10px;border-radius:3px;background:${sty.color};border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.3);cursor:pointer;padding:0;opacity:${c.stale ? 0.45 : 0.85}`;
      }
      const popup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '320px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b>${esc(c.title)}</b>
          <br><span style="color:#64748b">${[c.road, c.district ? `เขต${c.district}` : c.province].filter(Boolean).map(esc).join(' · ')}${c.road || c.district || c.province ? ' · ' : ''}${c.kind === 'itic' ? `กล้อง ${esc(c.organization || 'iTIC')}` : 'กล้อง กทม.'}</span>
          <br><span style="color:${sty.color};font-weight:700">${sty.label}</span>
          <span style="color:#64748b">· AI มั่นใจ ${Math.round((c.confidence || 0) * 100)}%</span>
          ${c.note_th ? `<br><span>${esc(c.note_th)}</span>` : ''}
          <img src="/api/flood/cameras/${encodeURIComponent(c.camid)}/image?t=${c.checked_at}" alt="ภาพที่ AI ดู จากกล้อง ${esc(c.title)}" loading="lazy" style="display:block;margin-top:6px;width:100%;aspect-ratio:352/288;object-fit:cover;border-radius:6px;background:#e2e8f0">
          ${wet && c.wet_since ? `<span style="color:#64748b">เห็นน้ำตั้งแต่ ${fmtTime(c.wet_since)} น.</span><br>` : ''}
          <span style="color:${c.stale ? '#b45309' : '#94a3b8'};font-size:11px">ภาพเมื่อ ${fmtTime(c.frame_ts)} น. (${agoTh(c.frame_ts)})${c.stale ? ' · ภาพเก่า กล้องยังไม่ส่งภาพใหม่' : ''}</span>
          <br><span style="color:#94a3b8;font-size:11px">AI ดูจากภาพกล้อง อาจผิดพลาดได้</span>
        </div>`
      );
      // a wet pill stands just above its point, so it does not cover the CCTV pin of the same (iTIC) camera
      const place = wet ? { anchor: 'bottom', offset: [0, -10] } : {};
      camFloodMarkersRef.current.push(new maplibregl.Marker({ element: el, ...place }).setLngLat([c.lng, c.lat]).setPopup(popup).addTo(map));
    }
  }, [camFlood, showCamFlood]);
  return { showCamFlood, setShowCamFlood, camFloodDry, setCamFloodDry, camFlood };
}

export function useUserReportLayer(mapRef, isActive) {
  const [showUserReports, setShowUserReports] = useState(true);
  const [userReports, setUserReports] = useState(null);
  const userReportMarkersRef = useRef([]);

  // Flood reports from the public (published after the AI check), shown for 6 h
  useEffect(() => {
    if (!isActive || !showUserReports) return;
    let alive = true;
    const tick = () => fetchUserReports().then((d) => alive && setUserReports(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive, showUserReports]);

  // One pin per report from the public, with its photo in the popup
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of userReportMarkersRef.current) m.remove();
    userReportMarkersRef.current = [];
    if (!showUserReports || !userReports) return;
    for (const u of userReports.items || []) {
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `ประชาชนแจ้งน้ำท่วม ${agoTh(u.ts)} · น้ำสูง${u.depth_th}`;
      el.style.cssText = `width:26px;height:26px;border-radius:999px 999px 999px 3px;background:${USER_REPORT_COLOR};border:2px solid #fff;box-shadow:0 0 0 4px ${USER_REPORT_COLOR}44,0 1px 4px rgba(15,23,42,.35);color:#fff;font-size:13px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0`;
      el.textContent = u.photo ? '📷' : '💧';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b style="color:${USER_REPORT_COLOR}">ประชาชนแจ้ง ยังไม่ยืนยัน</b> <span style="color:#64748b">· ${agoTh(u.ts)}</span>
          <br>น้ำสูง<b>${esc(u.depth_th)}</b> <span style="color:#64748b">(~${u.depth_cm} ซม.)</span>
          ${u.note ? `<br><span>${esc(u.note)}</span>` : ''}
          ${u.photo ? `<img src="${esc(u.photo)}" alt="รูปจากผู้แจ้ง" loading="lazy" style="display:block;margin-top:6px;width:100%;max-height:200px;object-fit:cover;border-radius:6px;background:#e2e8f0">` : ''}
          ${u.photo && u.ai_level_th ? `<span style="color:#64748b;font-size:11px">AI ดูรูปแล้ว: ${esc(u.ai_level_th)}${u.ai_note ? ` · ${esc(u.ai_note)}` : ''}</span>` : ''}
        </div>`
      );
      userReportMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([u.lng, u.lat]).setPopup(popup).addTo(map));
    }
  }, [userReports, showUserReports]);
  return { showUserReports, setShowUserReports, userReports };
}

export function useTraffyReportLayer(mapRef, isActive) {
  const [showReports, setShowReports] = useState(false);
  const [reports, setReports] = useState(null);
  const [reportsFailed, setReportsFailed] = useState(false);   // this page's last request for the reports failed
  const reportMarkersRef = useRef([]);

  // Traffy Fondue flood complaints; the server refreshes them every 5 min
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () =>
      fetchFloodReports()
        .then((d) => {
          if (!alive) return;
          setReports(d);
          setReportsFailed(false);
        })
        .catch(() => alive && setReportsFailed(true));
    tick();
    const id = setInterval(tick, 300000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  const reportPoints = useMemo(() => (reports?.items || []).filter((r) => r.lat && r.lng), [reports]);
  const reportFresh = useMemo(() => reportPoints.filter((r) => Date.now() / 1000 - r.ts <= REPORT_FRESH_S).length, [reportPoints]);
  // Districts with the most reports, busiest first: that is where the sois are under water
  const reportDistricts = useMemo(() => {
    const by = {};
    for (const r of reportPoints) (by[r.district || 'ไม่ระบุเขต'] ||= []).push(r);
    return Object.entries(by).map(([name, items]) => ({ name, items })).sort((a, b) => b.items.length - a.items.length).slice(0, 5);
  }, [reportPoints]);

  // One pin per citizen report: solid and ringed in the last hour, faded when older
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of reportMarkersRef.current) m.remove();
    reportMarkersRef.current = [];
    if (!showReports) return;
    for (const r of reportPoints) {
      const fresh = Date.now() / 1000 - r.ts <= REPORT_FRESH_S;
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `ประชาชนแจ้งน้ำท่วม ${agoTh(r.ts)}${r.district ? ` · เขต${r.district}` : ''}`;
      el.style.cssText = `width:24px;height:24px;border-radius:999px 999px 999px 3px;background:${REPORT_COLOR};border:2px solid #fff;box-shadow:${fresh ? `0 0 0 5px ${REPORT_COLOR}44,` : ''}0 1px 4px rgba(15,23,42,.35);color:#fff;font-size:12px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;opacity:${fresh ? 1 : 0.6}`;
      el.textContent = '📣';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b style="color:${REPORT_COLOR}">ประชาชนแจ้งน้ำท่วม</b> <span style="color:#64748b">· ${agoTh(r.ts)}</span>
          ${r.depth ? `<br>ระดับน้ำ: <b>${esc(r.depth)}</b>` : ''}
          <br><span>${esc(r.text.length > 180 ? `${r.text.slice(0, 180)}…` : r.text)}</span>
          ${r.photo ? `<br><img src="${esc(r.photo)}" alt="" loading="lazy" style="margin-top:6px;width:100%;max-height:160px;object-fit:cover;border-radius:6px">` : ''}
          <br><span style="color:#64748b">${esc(r.address)}</span>
          <br><span style="color:#64748b">สถานะ: ${esc(r.state || '-')}</span>
          · <a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer" style="color:#2563eb">ดูใน Traffy Fondue</a>
        </div>`
      );
      reportMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([r.lng, r.lat]).setPopup(popup).addTo(map));
    }
  }, [reportPoints, showReports]);
  return { reportPoints, reportFresh, reportDistricts, showReports, setShowReports, reports, reportsFailed };
}

export function useHdmsLayer(mapRef, isActive) {
  const [showHdms, setShowHdms] = useState(false);
  const [hdms, setHdms] = useState(null);
  const hdmsMarkersRef = useRef([]);

  // Department of Highways flood tickets; the server refreshes them every 10 min
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchHdmsFloods().then((d) => alive && setHdms(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 600000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  const hdmsPoints = useMemo(() => (hdms?.items || []).filter((h) => h.lat && h.lng), [hdms]);
  const hdmsActive = useMemo(() => hdmsPoints.filter((h) => h.active).length, [hdmsPoints]);
  // Districts with the most open tickets, busiest first
  const hdmsAreas = useMemo(() => {
    const by = {};
    for (const h of hdmsPoints) {
      if (!h.active) continue;
      const name = !h.amphoe ? h.province : h.province === 'กรุงเทพมหานคร' ? `เขต${h.amphoe}` : `อ.${h.amphoe} จ.${h.province}`;
      (by[name] ||= []).push(h);
    }
    return Object.entries(by).map(([name, items]) => ({ name, items })).sort((a, b) => b.items.length - a.items.length).slice(0, 5);
  }, [hdmsPoints]);

  // One pin per highway flood ticket: solid while open, faded once closed
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of hdmsMarkersRef.current) m.remove();
    hdmsMarkersRef.current = [];
    if (!showHdms) return;
    for (const h of hdmsPoints) {
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `กรมทางหลวง: ${h.place || h.title}${h.depth_cm ? ` · ${h.depth_cm} ซม.` : ''}`;
      el.style.cssText = `width:24px;height:24px;border-radius:6px;background:${HDMS_COLOR};border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);color:#fff;font-size:12px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;opacity:${h.active ? 1 : 0.5}`;
      el.textContent = '🛣';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b style="color:${HDMS_COLOR}">ทางหลวงน้ำท่วม (กรมทางหลวง)</b> <span style="color:#64748b">· ${agoTh(h.ts)}</span>
          <br><b>${esc(h.place || h.title)}</b>
          <br><span>${esc(h.title)}</span>
          ${h.depth_cm ? `<br>ระดับน้ำ: <b>${esc(h.depth_cm)} ซม.</b>` : ''}
          ${h.closure || h.lane_closure ? `<br>${esc(h.closure || 'ปิดช่องจราจร')}` : ''}
          ${h.relief ? `<br><span style="color:#475569">${esc(h.relief)}</span>` : ''}
          <br><span style="color:#64748b">${h.amphoe ? `${esc(h.amphoe)} · ` : ''}${esc(h.province)}${h.depot ? ` · ${esc(h.depot)}` : ''}</span>
          <br><span style="color:#64748b">สถานะ: ${h.active ? 'ยังมีน้ำท่วม' : 'คลี่คลายแล้ว'}</span>
        </div>`
      );
      hdmsMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([h.lng, h.lat]).setPopup(popup).addTo(map));
    }
  }, [hdmsPoints, showHdms]);
  return { hdmsPoints, hdmsActive, hdmsAreas, showHdms, setShowHdms, hdms };
}

export function useGaugeLayer(mapRef, waterSummary) {
  const [showGauges, setShowGauges] = useState(false);
  const gaugeMarkersRef = useRef([]);

  // River + canal gauges for the six metro provinces, from the water summary MapPage polls (waterSummary)
  const gauges = useMemo(() => {
    const out = [];
    for (const r of waterSummary?.river || []) {
      if (r.lat && r.lng) out.push({ ...r, kind: 'river' });
    }
    for (const c of waterSummary?.canals || []) {
      if (c.lat && c.lng) out.push({ ...c, kind: 'canal' });
    }
    return out;
  }, [waterSummary]);

  const gaugeCounts = useMemo(() => {
    const c = { overflow: 0, high: 0, normal: 0, low: 0 };
    for (const g of gauges) c[g.level] = (c[g.level] || 0) + 1;
    return c;
  }, [gauges]);

  const provinceCount = useMemo(() => new Set(gauges.map((g) => g.province).filter(Boolean)).size, [gauges]);

  // River / canal gauges: a dot whose colour is the bank level, with the % of capacity inside
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of gaugeMarkersRef.current) m.remove();
    gaugeMarkersRef.current = [];
    if (!showGauges) return;
    for (const g of gauges) {
      const sty = GAUGE_STYLE[g.level] || GAUGE_STYLE.normal;
      const alarm = g.level === 'overflow' || g.level === 'high';
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `${g.name} (${g.province}): ${sty.label}${g.storage_pct != null ? ` ${g.storage_pct}%` : ''}`;
      if (alarm) {
        el.style.cssText = `display:flex;align-items:center;justify-content:center;min-width:34px;height:20px;padding:0 5px;border-radius:6px;background:${sty.color};color:#fff;font:700 10px/1 var(--font-sans);border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);cursor:pointer`;
        el.textContent = `${Math.round(g.storage_pct)}%`;
      } else {
        el.style.cssText = `width:10px;height:10px;border-radius:2px;background:${sty.color};border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.3);cursor:pointer;padding:0;opacity:.8`;
      }
      const popup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '280px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b>${esc(g.name)}</b>
          <br><span style="color:#64748b">${g.kind === 'river' ? 'จุดวัดน้ำแม่น้ำ' : 'จุดวัดน้ำคลอง'}${g.district ? ` · ${esc(g.district)}` : ''}${g.province ? ` · ${esc(g.province)}` : ''}</span>
          <br><span style="color:${sty.color};font-weight:700">${sty.label}</span>${g.storage_pct != null ? ` น้ำเต็ม <b>${g.storage_pct}%</b>` : ''}
          ${g.msl != null ? `<br><span style="color:#64748b">ระดับน้ำ ${g.msl} ม.${g.bank != null ? ` · ตลิ่ง ${g.bank} ม.` : ''} (วัดจากระดับน้ำทะเล)</span>` : ''}
          ${g.diff_text && g.diff_bank != null ? `<br><span style="color:#64748b">${esc(g.diff_text)} ${g.diff_bank}</span>` : ''}
          ${g.ts ? `<br><span style="color:#94a3b8;font-size:11px">ข้อมูล ${new Date(g.ts * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })} น. · ${g.source === 'bma' ? 'สำนักการระบายน้ำ กทม.' : 'คลังข้อมูลน้ำแห่งชาติ'}</span>` : ''}
        </div>`
      );
      gaugeMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([g.lng, g.lat]).setPopup(popup).addTo(map));
    }
  }, [gauges, showGauges]);
  return { gauges, gaugeCounts, provinceCount, showGauges, setShowGauges };
}

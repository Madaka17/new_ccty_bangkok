// Flood Pin (#/report, the nav's แจ้งน้ำท่วม button): flooding reported by the public through Traffy Fondue, the
// city's own complaint channel, so a report reaches the district office that has to act on it. The map
// shows every Traffy flood ticket of the last 6 h (/api/flood/reports, which polls Traffy every 5 min) and
// the side card sends people to the Traffy Fondue LINE account to report a new one.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { fetchFloodReports } from '../lib/api.js';
import { Card, Badge, FOCUS } from './dashboard/ui.jsx';
import { PageHeader } from './dashboard/primitives.jsx';
import { PAGE_TITLES } from './Sidebar.jsx';
import { fmtTime } from './dashboard/format.js';
import { baseStyle } from './water/WaterMap.jsx';

const POLL_MS = 60000;
const TRAFFY_LINE = 'https://line.me/R/ti/p/@traffyfondue';
const TRAFFY_SITE = 'https://share.traffy.in.th/teamchadchart';
const PIN = '#7c3aed';     // the Traffy colour on the Traffic Map too
const FRESH_S = 3600;      // a report younger than this gets a halo
const LATEST = 8;
const STATE_TONE = { 'รอรับเรื่อง': 'yellow', 'รับเรื่อง': 'blue', 'ส่งต่อ(ใหม่)': 'blue', 'กำลังดำเนินการ': 'blue', 'เสร็จสิ้น': 'green' };
const STEPS = [
  'เพิ่มเพื่อน LINE @traffyfondue',
  'ถ่ายรูปน้ำท่วม แล้วกดแชร์ตำแหน่งตรงจุดที่ท่วม',
  'เลือกประเภทเรื่อง "น้ำท่วม" และพิมพ์ระดับน้ำ เช่น ท่วมถึงเข่า',
  'ติดตามสถานะได้ในแชท เรื่องจะขึ้นบนแผนที่นี้ภายในราว 5 นาที',
];

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ago = (ts) => {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.round(m / 60)} ชม.ก่อน`;
};

function popupHtml(r) {
  return `<div style="font-size:13px;line-height:1.45">
    <b style="color:${PIN}">แจ้งผ่าน Traffy Fondue</b> <span style="color:#64748b">· ${ago(r.ts)}</span>
    ${r.depth ? `<br>ระดับน้ำ: <b>${esc(r.depth)}</b>` : ''}
    <br><span>${esc(r.text.length > 180 ? `${r.text.slice(0, 180)}…` : r.text)}</span>
    ${r.photo ? `<br><img src="${esc(r.photo)}" alt="" loading="lazy" style="margin-top:6px;width:100%;max-height:160px;object-fit:cover;border-radius:6px">` : ''}
    <br><span style="color:#64748b">${esc(r.address)}</span>
    <br><span style="color:#64748b">สถานะ: ${esc(r.state || '-')}</span>
    · <a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer" style="color:#2563eb">ดูเรื่องนี้ใน Traffy Fondue</a>
  </div>`;
}

export default function FloodPinPage({ isActive }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});

  const load = useCallback(() => {
    fetchFloodReports()
      .then((d) => {
        setData(d);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const points = useMemo(() => (data?.items || []).filter((r) => r.lat && r.lng), [data]);
  const byState = useMemo(() => {
    const c = {};
    for (const r of points) c[r.state || '-'] = (c[r.state || '-'] || 0) + 1;
    return Object.entries(c).sort((a, b) => b[1] - a[1]);
  }, [points]);

  // Map: created once
  useEffect(() => {
    if (!mapEl.current || mapRef.current) return undefined;
    const map = new maplibregl.Map({ container: mapEl.current, style: baseStyle(), center: [100.55, 13.76], zoom: 10.5, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true } }), 'top-left');
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = {};
    };
  }, []);

  // One speech-bubble pin per report, brighter while fresh
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of Object.values(markersRef.current)) m.remove();
    markersRef.current = {};
    for (const r of points) {
      const fresh = Date.now() / 1000 - r.ts <= FRESH_S;
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `แจ้งน้ำท่วม ${ago(r.ts)}${r.district ? ` · เขต${r.district}` : ''}`;
      el.style.cssText = `width:24px;height:24px;border-radius:999px 999px 999px 3px;background:${PIN};border:2px solid #fff;box-shadow:${fresh ? `0 0 0 5px ${PIN}44,` : ''}0 1px 4px rgba(15,23,42,.35);color:#fff;font-size:12px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;opacity:${fresh ? 1 : 0.6}`;
      el.textContent = '📣';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px' }).setHTML(popupHtml(r));
      markersRef.current[r.id] = new maplibregl.Marker({ element: el }).setLngLat([r.lng, r.lat]).setPopup(popup).addTo(map);
    }
  }, [points]);

  const flyTo = (r) => {
    const map = mapRef.current;
    const m = markersRef.current[r.id];
    if (!map || !m) return;
    for (const other of Object.values(markersRef.current)) if (other !== m && other.getPopup()?.isOpen()) other.togglePopup();
    map.flyTo({ center: [r.lng, r.lat], zoom: 15, duration: 700 });
    if (!m.getPopup()?.isOpen()) m.togglePopup();
    mapEl.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  const latest = points.slice(0, LATEST);

  const lineCard = (
    <Card className="p-4 lg:col-start-2 lg:row-start-1">
      <h3 className="text-[15px] font-semibold text-slate-900">แจ้งน้ำท่วมผ่าน Traffy Fondue</h3>
      <ol className="mt-2 flex flex-col gap-1.5 text-sm text-slate-700 list-decimal pl-5">
        {STEPS.map((s) => <li key={s}>{s}</li>)}
      </ol>
      <a
        href={TRAFFY_LINE}
        target="_blank"
        rel="noopener noreferrer"
        className={`mt-3 flex items-center justify-center gap-2 h-12 rounded-xl bg-[#06c755] hover:bg-[#05b34c] text-white text-base font-semibold ${FOCUS}`}
      >
        เปิด LINE @traffyfondue
      </a>
      <a href={TRAFFY_SITE} target="_blank" rel="noopener noreferrer" className={`mt-2 block text-center text-xs text-blue-700 hover:underline ${FOCUS}`}>
        ดูเรื่องทั้งหมดบนเว็บ Traffy Fondue
      </a>
    </Card>
  );

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={PAGE_TITLES.report}
        description="แจ้งน้ำท่วมผ่าน Traffy Fondue เรื่องจะส่งถึงสำนักงานเขตโดยตรง · แผนที่นี้แสดงเรื่องน้ำท่วมที่คนแจ้งใน 6 ชั่วโมงล่าสุด"
      />
      {/* phones: the LINE card first, then the map, then the lists · wide: the map left, the rest stacked right */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] lg:grid-rows-[auto_1fr] gap-4 items-start">
        {lineCard}

        <Card className="p-0 overflow-hidden lg:col-start-1 lg:row-start-1 lg:row-span-2">
          <div className="relative h-[52vh] min-h-[340px] lg:h-[calc(100vh-13rem)]">
            {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
            <div ref={mapEl} style={{ position: 'absolute', inset: 0 }} aria-label="แผนที่เรื่องน้ำท่วมที่แจ้งผ่าน Traffy Fondue" />
            <span className="absolute top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-white border border-slate-200 px-3 py-1 text-[11px] text-slate-700 shadow-sm pointer-events-none whitespace-nowrap">
              {!data ? 'กำลังโหลดเรื่องแจ้ง…' : data.updated_at ? `📣 ${points.length} เรื่องใน 6 ชม. · อัปเดต ${fmtTime(data.updated_at)} น.` : 'ยังโหลดเรื่องจาก Traffy ไม่ได้'}
            </span>
          </div>
          {/* never loaded: the badge and the list already say Traffy could not be read, and there is nothing "on hand" */}
          {(failed || (data?.error && data.updated_at)) && (
            <p role="status" className="px-4 py-2 text-xs text-amber-800 bg-amber-50 border-t border-amber-200">
              อัปเดตรอบล่าสุดไม่สำเร็จ แสดงข้อมูลเท่าที่มี
            </p>
          )}
        </Card>

        <div className="flex flex-col gap-3 lg:col-start-2 lg:row-start-2">
          {byState.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {byState.map(([state, n]) => (
                <Badge key={state} tone={STATE_TONE[state] || 'neutral'}>{state} {n}</Badge>
              ))}
            </div>
          )}

          <Card className="p-0 overflow-hidden">
            <p className="px-4 pt-3 pb-2 text-xs font-semibold text-slate-600">แจ้งล่าสุด</p>
            {latest.length === 0 ? (
              <p className="px-4 pb-4 text-sm text-slate-500">{!data ? 'กำลังโหลด…' : data.updated_at ? 'ยังไม่มีเรื่องน้ำท่วมใน 6 ชั่วโมงล่าสุด' : 'ยังโหลดเรื่องจาก Traffy ไม่ได้ ระบบจะลองใหม่เอง'}</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {latest.map((r) => (
                  <li key={r.id}>
                    <button type="button" onClick={() => flyTo(r)} className={`cursor-pointer w-full text-left px-4 py-2.5 hover:bg-slate-50 flex gap-3 ${FOCUS}`}>
                      {r.photo && <img src={r.photo} alt="" loading="lazy" className="w-14 h-14 rounded-md object-cover shrink-0 bg-slate-100" />}
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm text-slate-900 line-clamp-2">{r.text}</span>
                        <span className="mt-0.5 block text-[11px] text-slate-500">
                          {ago(r.ts)}{r.district ? ` · เขต${r.district}` : ''}{r.depth ? ` · ${r.depth}` : ''} · {r.state || '-'}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

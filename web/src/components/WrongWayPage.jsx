import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchWrongWayStatus, fetchWrongWayRecent, fetchWrongWayCameras, fetchWrongWayField, triggerWrongWayCheck,
  reanalyseWrongWay, reanalyseWrongWayPending, dismissWrongWay, getBmaSnapshotUrl,
} from '../lib/api.js';
import { Card, Badge, Button, Skeleton, EmptyState, Truncate } from './dashboard/ui.jsx';
import { PageHeader, Tabs, StatTile, StatusBanner, Modal } from './dashboard/primitives.jsx';
import { fmtNum, fmtTime, fmtDateTime } from './dashboard/format.js';

const POLL_MS = 30000;
const TABS = [
  { id: 'violations', label: 'รถย้อนศร' },
  { id: 'captures', label: 'รถที่สงสัย' },
  { id: 'cameras', label: 'กล้องทุกตัว' },
];
const VERDICT_TONE = { wrong_way: 'red', ok: 'green', pending: 'blue', unclear: 'neutral', error: 'yellow' };
const LEVEL = { online: { tone: 'green', label: 'ออนไลน์' }, offline: { tone: 'neutral', label: 'ออฟไลน์' }, unknown: { tone: 'neutral', label: 'รอสแกน' } };
// image-space direction of each heading for the arrow overlay (toward = down the frame)
const ARROW = { toward: [0, 1], away: [0, -1], left: [-1, 0], right: [1, 0] };

// Wrong-way patrol over all 574 BMA cameras: the trained heading detector (YOLO26x) reads which way
// every vehicle faces, each camera learns its normal lane directions, and a vehicle facing against
// its lane is sent to the vision agent. Same three views as the helmet page.
export default function WrongWayPage({ isActive, onToast }) {
  const [tab, setTab] = useState('violations');
  const [status, setStatus] = useState(null);
  const [violations, setViolations] = useState(null);
  const [captures, setCaptures] = useState(null);
  const [cameras, setCameras] = useState(null);
  const [hours, setHours] = useState(24);
  const [query, setQuery] = useState('');
  const [onlyLearned, setOnlyLearned] = useState(true);
  const [open, setOpen] = useState(null);
  const [field, setField] = useState(null);
  const [checking, setChecking] = useState(null);
  const [judging, setJudging] = useState(null);
  const [bulk, setBulk] = useState(null);

  const load = useCallback(async () => {
    try {
      const [st, v, c] = await Promise.all([
        fetchWrongWayStatus(),
        fetchWrongWayRecent({ hours, verdict: 'wrong_way', limit: 300 }),
        fetchWrongWayRecent({ hours: Math.min(hours, 48), limit: 300 }),
      ]);
      setStatus(st);
      setViolations(v.items);
      setCaptures(c.items);
    } catch {
      /* keep the last data on a failed poll */
    }
  }, [hours]);

  const loadCameras = useCallback(() => fetchWrongWayCameras().then((d) => setCameras(d.items)).catch(() => {}), []);

  useEffect(() => {
    if (!isActive) return;
    load();
    loadCameras();
    const id = setInterval(() => {
      load();
      if (tab === 'cameras') loadCameras();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load, loadCameras, tab]);

  // learned lane directions of the camera behind the open evidence
  useEffect(() => {
    if (!open?.camid) { setField(null); return; }
    fetchWrongWayField(open.camid).then(setField).catch(() => setField(null));
  }, [open?.camid]);

  const checkNow = async (cam) => {
    setChecking(cam.camid);
    try {
      const r = await triggerWrongWayCheck(cam.camid);
      onToast?.(r.ok ? `${cam.title}: ${r.message}` : `${cam.title}: ${r.error}`);
      if (r.ok && r.captures?.length) setTimeout(load, 4000);
      loadCameras();
    } catch {
      onToast?.('สั่งตรวจไม่สำเร็จ');
    } finally {
      setChecking(null);
    }
  };

  const judge = async (item, agent) => {
    setJudging(agent);
    try {
      const r = await reanalyseWrongWay(item.id, agent);
      if (r.ok) {
        setOpen(r.item);
        onToast?.(`${r.item.verdict_th}${r.item.confidence != null ? ` (${Math.round(r.item.confidence * 100)}%)` : ''} · ${r.item.source}`);
        load();
      } else onToast?.(r.error);
    } catch {
      onToast?.('วิเคราะห์ไม่สำเร็จ');
    } finally {
      setJudging(null);
    }
  };

  const dismiss = async (item) => {
    setJudging('dismiss');
    try {
      const r = await dismissWrongWay(item.id);
      if (r.ok) {
        setOpen(r.item);
        onToast?.('บันทึกว่าไม่ใช่การย้อนศรแล้ว');
        load();
      } else onToast?.(r.error);
    } catch {
      onToast?.('บันทึกไม่สำเร็จ');
    } finally {
      setJudging(null);
    }
  };

  const judgePending = async (agent) => {
    setBulk(agent);
    try {
      const r = await reanalyseWrongWayPending(agent, agent === 'local' ? 300 : 60);
      onToast?.(r.queued ? `ส่งภาพที่ยังไม่ชัด ${r.queued} ภาพให้ ${agent === 'local' ? detector : status?.agent_model || 'AI'} ตรวจใหม่` : 'ไม่มีภาพค้างตรวจ');
      setTimeout(load, agent === 'local' ? 3000 : 8000);
    } catch {
      onToast?.('สั่งตรวจไม่สำเร็จ');
    } finally {
      setBulk(null);
    }
  };

  const camList = useMemo(() => {
    if (!cameras) return [];
    const q = query.trim().toLowerCase();
    return cameras.filter((c) => (!onlyLearned || c.known > 0 || c.captures > 0) && (!q || c.title.toLowerCase().includes(q) || (c.district || '').toLowerCase().includes(q)));
  }, [cameras, query, onlyLearned]);

  const t = status?.today || {};
  const detector = status?.detector || null;
  const noModel = status && !status.enabled;
  const agentOff = status && (!status.agent || status.agent === 'off');

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="ตรวจรถย้อนศรจากกล้อง กทม."
        description="ทุกรอบสแกน (~4 นาที) โมเดลทิศทางรถที่เทรนเอง (YOLO26x) อ่านว่ารถแต่ละคันหันไปทางไหน กล้องแต่ละตัวเรียนรู้เองว่าช่องทางไหนปกติวิ่งทางใด รถที่หันสวนช่องทางจะถูกส่งให้ AI agent ยืนยัน แล้วเก็บหลักฐานลง Drive E: อัตโนมัติ"
        actions={
          <div className="flex items-center gap-2">
            <select value={hours} onChange={(e) => setHours(Number(e.target.value))} className="h-9 rounded-lg border border-slate-300 bg-white px-2 text-sm text-slate-700">
              <option value={6}>6 ชม.</option>
              <option value={24}>24 ชม.</option>
              <option value={72}>3 วัน</option>
              <option value={168}>7 วัน</option>
            </select>
            <Button size="sm" onClick={() => { load(); loadCameras(); }}>รีเฟรช</Button>
          </div>
        }
      />

      {noModel && (
        <StatusBanner tone="yellow" label="ยังไม่มีโมเดลทิศทางรถ">
          ไม่พบ <code>wrongway_det.pt</code> ที่ root — รัน <code>local\pipeline\wrongway_pipeline.bat</code> (เก็บภาพทั้งวัน + เทรน) แล้วรีสตาร์ต server
        </StatusBanner>
      )}
      {!noModel && agentOff && (
        <StatusBanner tone="neutral" label="ไม่มี AI agent ยืนยัน">
          ใช้ผลจากโมเดลในเครื่องอย่างเดียว ตั้ง <code>GEMINI_API_KEY</code> ใน .env เพื่อให้ AI ตรวจซ้ำก่อนบันทึก
        </StatusBanner>
      )}
      {status && !status.archive_ok && (
        <StatusBanner tone="red" label="ไม่พบไดรฟ์เก็บหลักฐาน">
          {status.archive_dir} เข้าไม่ได้ ระบบยังตรวจต่อแต่จะไม่มีไฟล์ภาพลงไดรฟ์
        </StatusBanner>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="รถย้อนศรวันนี้" value={fmtNum(t.wrong_way)} tone="red" sub={`สะสมทั้งหมด ${fmtNum(status?.total_wrong_way)} คัน`} loading={!status} />
        <StatTile label="รถที่สงสัยวันนี้" value={fmtNum(t.captures)} sub={`รอตรวจ ${fmtNum(t.pending ?? 0)} · ไม่ใช่ ${fmtNum(t.ok ?? 0)} · ไม่ชัด ${fmtNum(t.unclear ?? 0)}`} loading={!status} />
        <StatTile label="กล้องที่รู้ทิศทางแล้ว" value={fmtNum(status?.cameras_learned)} sub={`จากที่เห็น ${fmtNum(status?.cameras_seen)} กล้อง · ต้องมี ${status?.min_votes ?? '-'} คัน/ช่อง`} loading={!status} />
        <StatTile label="ตรวจล่าสุด" value={status?.last_check ? fmtTime(status.last_check) : '–'} sub={status ? `คิวรอ ${status.queue} · โมเดล ${detector || 'ไม่มี'} + ${status.agent_model || 'ไม่มี agent'}` : ''} loading={!status} />
      </div>

      <Tabs
        label="มุมมอง"
        value={tab}
        onChange={setTab}
        tabs={TABS.map((x) => ({ ...x, badge: x.id === 'violations' ? violations?.length : x.id === 'captures' ? captures?.length : cameras?.length }))}
      />

      {tab === 'violations' && (
        <EvidenceGrid items={violations} onOpen={setOpen} empty={`ยังไม่พบรถย้อนศรใน ${hours} ชม.ที่ผ่านมา`} />
      )}

      {tab === 'captures' && (
        <>
          <div className="flex flex-wrap items-center gap-2 -mt-1">
            <span className="text-xs text-slate-500">ตรวจภาพที่ยังไม่ชัดอีกครั้งด้วย:</span>
            <Button size="sm" variant="primary" onClick={() => judgePending('local')} loading={bulk === 'local'} disabled={!detector || !!bulk}>
              {detector || 'โมเดลในเครื่อง'} (ฟรี ทันที)
            </Button>
            <Button size="sm" onClick={() => judgePending('cloud')} loading={bulk === 'cloud'} disabled={agentOff || !!status?.agent_error || !!bulk}>
              {status?.agent_model || 'AI agent'}
            </Button>
          </div>
          <EvidenceGrid items={captures} onOpen={setOpen} compact empty="ยังไม่มีรถที่สงสัย กล้องต้องเรียนรู้ทิศทางก่อน (ดูแท็บกล้อง) หรือกด 'ตรวจตอนนี้'" />
        </>
      )}

      {tab === 'cameras' && (
        <Card className="p-4 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="ค้นหาชื่อกล้อง / เขต"
              className="h-9 w-full sm:w-72 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400"
            />
            <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input type="checkbox" checked={onlyLearned} onChange={(e) => setOnlyLearned(e.target.checked)} className="accent-blue-600" />
              เฉพาะกล้องที่รู้ทิศทางแล้ว
            </label>
            <span className="ml-auto text-xs text-slate-500">{camList.length} จาก {cameras?.length ?? 0} กล้อง · เรียงตามย้อนศร / สงสัย / ช่องที่รู้ทิศ</span>
          </div>
          {!cameras ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {[1, 2, 3, 4, 5, 6].map((n) => <Skeleton key={n} className="h-24" />)}
            </div>
          ) : camList.length === 0 ? (
            <EmptyState title="ไม่มีกล้องตรงเงื่อนไข" description="กล้องเรียนรู้ทิศทางจากรถที่ผ่านทุกรอบสแกน ต้องรอสักพักหลังรีสตาร์ต หรือปิดตัวกรอง" />
          ) : (
            <ul className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {camList.slice(0, 150).map((c) => {
                const lv = LEVEL[c.status] || LEVEL.unknown;
                return (
                  <li key={c.camid} className="rounded-xl border border-slate-200 p-3 flex gap-3 items-center">
                    <div className="w-24 h-16 rounded-md bg-slate-900 overflow-hidden shrink-0 border border-slate-200">
                      <img src={getBmaSnapshotUrl(c.camid, false, status?.updated)} alt="" loading="lazy" className="w-full h-full object-cover" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <Truncate text={c.title} className="text-sm font-medium text-slate-900" />
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-600 mt-0.5">
                        <Badge tone={lv.tone}>{lv.label}</Badge>
                        <span className="tabular-nums" title="ช่องบนภาพที่รู้ทิศทางแล้ว / ช่องที่มีรถผ่าน">รู้ทิศ {c.known}/{c.active} ช่อง</span>
                        <span className="tabular-nums">สงสัยวันนี้ {c.captures}</span>
                        {c.wrong_way > 0 && <span className="tabular-nums font-medium text-red-700">ย้อนศร {c.wrong_way}</span>}
                      </div>
                      {c.district && <span className="block text-xs text-slate-500 truncate">{c.district}</span>}
                    </div>
                    <Button size="sm" onClick={() => checkNow(c)} loading={checking === c.camid} disabled={noModel}>
                      ตรวจตอนนี้
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
          {camList.length > 150 && <p className="text-xs text-slate-500">แสดง 150 กล้องแรก พิมพ์ค้นหาเพื่อกรอง</p>}
        </Card>
      )}

      <Modal open={!!open} onClose={() => setOpen(null)} title={open?.title} subtitle={open ? `${fmtDateTime(open.ts)} · ${open.district || ''}` : ''} wide>
        {open && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-1 md:grid-cols-[1fr_260px] gap-3">
              <div className="relative">
                <img src={open.frame} alt="ภาพเต็มจากกล้อง กรอบแดง = รถที่สงสัย ลูกศรเขียว = ทิศปกติของช่องทาง" className="w-full rounded-lg border border-slate-200 bg-slate-900" />
                {field?.cells?.length > 0 && <FieldOverlay field={field} />}
              </div>
              <img src={open.crop} alt="ภาพขยายรถ" className="w-full rounded-lg border border-slate-200 bg-slate-900" />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone={VERDICT_TONE[open.verdict]} dot={open.verdict === 'wrong_way'}>{open.verdict_th}</Badge>
              <span className="text-slate-700">รถหัน: {open.heading_th} · ช่องทางปกติ: {open.expected_th}</span>
              {open.confidence != null && <span className="text-slate-500 tabular-nums">ความมั่นใจ {Math.round(open.confidence * 100)}%</span>}
              {open.source && <span className="text-slate-500">ตรวจโดย {open.source === 'local' ? detector || 'โมเดลในเครื่อง' : open.source === 'person' ? 'ผู้ดูแล' : open.source}</span>}
            </div>
            {open.note && <p className="text-sm text-slate-700">{open.note}</p>}
            <p className="text-xs text-slate-500">
              บนภาพ: กรอบแดง = รถที่สงสัย, ลูกศรเขียวใหญ่ = ทิศปกติของช่องทางนั้น, ลูกศรเล็กสีฟ้า = ทิศทางที่กล้องเรียนรู้ในแต่ละช่อง
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-200">
              <span className="text-xs text-slate-500">วิเคราะห์ใหม่ด้วย:</span>
              <Button size="sm" variant="primary" onClick={() => judge(open, 'local')} loading={judging === 'local'} disabled={!detector || !!judging}>
                {detector || 'โมเดลในเครื่อง'}
              </Button>
              <Button size="sm" onClick={() => judge(open, 'cloud')} loading={judging === 'cloud'} disabled={agentOff || !!judging}>
                {status?.agent_model || 'Gemini'}{status?.agent_error ? ' (หยุดชั่วคราว)' : ''}
              </Button>
              {open.verdict !== 'ok' && (
                <Button size="sm" onClick={() => dismiss(open)} loading={judging === 'dismiss'} disabled={!!judging} className="ml-auto">
                  ไม่ใช่ย้อนศร (จอด/เลี้ยว)
                </Button>
              )}
            </div>
            {open.archive && <p className="text-xs text-slate-500 break-all">ไฟล์หลักฐาน: {open.archive}</p>}
          </div>
        )}
      </Modal>
    </div>
  );
}

// Small arrows over the evidence frame: one per grid cell whose lane direction the camera has learned
function FieldOverlay({ field }) {
  const { cols, rows, cells } = field;
  return (
    <svg viewBox={`0 0 ${cols * 10} ${rows * 10}`} preserveAspectRatio="none" className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden="true">
      {cells.map((c) => {
        const [dx, dy] = ARROW[c.heading] || [0, 0];
        const cx = c.c * 10 + 5;
        const cy = c.r * 10 + 5;
        return (
          <g key={`${c.r}-${c.c}`} stroke="#38bdf8" strokeWidth="0.8" strokeLinecap="round" opacity="0.85">
            <line x1={cx - dx * 3} y1={cy - dy * 3} x2={cx + dx * 3} y2={cy + dy * 3} />
            <line x1={cx + dx * 3} y1={cy + dy * 3} x2={cx + dx * 3 - dx * 1.6 - dy * 1.6} y2={cy + dy * 3 - dy * 1.6 + dx * 1.6} />
            <line x1={cx + dx * 3} y1={cy + dy * 3} x2={cx + dx * 3 - dx * 1.6 + dy * 1.6} y2={cy + dy * 3 - dy * 1.6 - dx * 1.6} />
          </g>
        );
      })}
    </svg>
  );
}

function EvidenceGrid({ items, onOpen, compact = false, empty }) {
  if (!items) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {[1, 2, 3, 4, 5].map((n) => <Skeleton key={n} className="h-44" />)}
      </div>
    );
  }
  if (items.length === 0) return <EmptyState title={empty} />;
  return (
    <ul className={`grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 ${compact ? 'xl:grid-cols-6' : 'xl:grid-cols-5'} gap-3`}>
      {items.map((it) => (
        <li key={it.id}>
          <button type="button" onClick={() => onOpen(it)} className="cursor-pointer w-full text-left rounded-xl border border-slate-200 bg-white overflow-hidden hover:border-slate-400 transition-colors">
            <div className="relative aspect-[4/3] bg-slate-900">
              <img src={compact ? it.crop : it.frame} alt="" loading="lazy" className="w-full h-full object-cover" />
              <span className="absolute top-1.5 left-1.5">
                <Badge tone={VERDICT_TONE[it.verdict]} dot={it.verdict === 'wrong_way'}>{it.verdict_th}</Badge>
              </span>
              {!compact && (
                <img src={it.crop} alt="" loading="lazy" className="absolute bottom-1.5 right-1.5 w-16 h-16 object-cover rounded-md border-2 border-white shadow" />
              )}
            </div>
            <div className="p-2.5">
              <Truncate text={it.title} className="text-sm font-medium text-slate-900" />
              <div className="flex items-center justify-between text-xs text-slate-500 mt-0.5">
                <span>{fmtDateTime(it.ts)}</span>
                {it.confidence != null && <span className="tabular-nums">{Math.round(it.confidence * 100)}%</span>}
              </div>
              {!compact && <p className="text-xs text-slate-600 mt-1 line-clamp-2">{it.note || `${it.heading_th} สวนช่องทาง${it.expected_th}`}</p>}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}

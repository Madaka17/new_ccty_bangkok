import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchHelmetStatus, fetchHelmetRecent, fetchHelmetCameras, triggerHelmetCheck, reanalyseHelmet, reanalyseHelmetPending, getBmaSnapshotUrl } from '../lib/api.js';
import { Card, Badge, Button, Skeleton, EmptyState, Truncate } from './dashboard/ui.jsx';
import { PageHeader, Tabs, StatTile, StatusBanner, Modal } from './dashboard/primitives.jsx';
import { fmtNum, fmtTime, fmtDateTime } from './dashboard/format.js';

const POLL_MS = 30000;
const TABS = [
  { id: 'violations', label: 'ไม่สวมหมวกกันน็อก' },
  { id: 'suspects', label: 'สงสัย รอยืนยัน' },
  { id: 'captures', label: 'มอไซที่จับภาพได้' },
  { id: 'cameras', label: 'กล้องทุกตัว' },
];
const VERDICT_TONE = { no_helmet: 'red', suspect: 'yellow', helmet: 'green', pending: 'blue', unclear: 'neutral', error: 'yellow' };
const LEVEL = { online: { tone: 'green', label: 'ออนไลน์' }, offline: { tone: 'neutral', label: 'ออฟไลน์' }, unknown: { tone: 'neutral', label: 'รอสแกน' } };

// Helmet patrol over all 574 BMA cameras: every motorcycle the scanner sees is cropped, a vision
// agent decides helmet / no helmet, and each no-helmet case is archived on the data drive.
// Three views on one poll: violations (evidence), all captures, and every camera with a "check now".
export default function HelmetPage({ isActive, onToast }) {
  const [tab, setTab] = useState('violations');
  const [status, setStatus] = useState(null);
  const [violations, setViolations] = useState(null);
  const [suspects, setSuspects] = useState(null);
  const [captures, setCaptures] = useState(null);
  const [cameras, setCameras] = useState(null);
  const [hours, setHours] = useState(24);
  const [query, setQuery] = useState('');
  const [onlyMoto, setOnlyMoto] = useState(true);
  const [open, setOpen] = useState(null);
  const [checking, setChecking] = useState(null);
  const [judging, setJudging] = useState(null);
  const [bulk, setBulk] = useState(false);

  const load = useCallback(async () => {
    try {
      const [st, v, sus, c] = await Promise.all([
        fetchHelmetStatus(),
        fetchHelmetRecent({ hours, verdict: 'no_helmet', limit: 300 }),
        fetchHelmetRecent({ hours, verdict: 'suspect', limit: 300 }),
        fetchHelmetRecent({ hours: Math.min(hours, 48), limit: 300 }),
      ]);
      setStatus(st);
      setViolations(v.items);
      setSuspects(sus.items);
      setCaptures(c.items);
    } catch {
      /* keep the last data on a failed poll */
    }
  }, [hours]);

  const loadCameras = useCallback(() => fetchHelmetCameras().then((d) => setCameras(d.items)).catch(() => {}), []);

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

  const checkNow = async (cam) => {
    setChecking(cam.camid);
    try {
      const r = await triggerHelmetCheck(cam.camid);
      onToast?.(r.ok ? `${cam.title}: ${r.message}` : `${cam.title}: ${r.error}`);
      if (r.ok && r.captures?.length) setTimeout(load, 4000);
    } catch {
      onToast?.('สั่งตรวจไม่สำเร็จ');
    } finally {
      setChecking(null);
    }
  };

  // Second opinion on one capture (local VLM on the server GPU, or the cloud agent)
  const judge = async (item, agent) => {
    setJudging(agent);
    try {
      const r = await reanalyseHelmet(item.id, agent);
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

  const judgePending = async () => {
    setBulk(true);
    try {
      const r = await reanalyseHelmetPending('local', 60);
      onToast?.(r.queued ? `ส่งภาพที่ยังไม่ชัด ${r.queued} ภาพให้ AI ในเครื่องตรวจใหม่ ผลจะทยอยขึ้นใน 1-3 นาที` : 'ไม่มีภาพค้างตรวจ');
      setTimeout(load, 8000);
    } catch {
      onToast?.('สั่งตรวจไม่สำเร็จ');
    } finally {
      setBulk(false);
    }
  };

  const camList = useMemo(() => {
    if (!cameras) return [];
    const q = query.trim().toLowerCase();
    return cameras.filter((c) => (!onlyMoto || c.motorcycles > 0 || c.captures > 0) && (!q || c.title.toLowerCase().includes(q) || (c.district || '').toLowerCase().includes(q)));
  }, [cameras, query, onlyMoto]);

  const t = status?.today || {};
  const vlm = status?.local_vlm;
  const agentOff = status && !status.enabled;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="ตรวจหมวกกันน็อกจากกล้อง กทม."
        description="ทุกรอบสแกน (~4 นาที) ระบบตัดภาพมอไซทุกคันที่เห็นหัวชัดพอ ส่งให้ AI agent ตัดสินว่าสวมหมวกหรือไม่ ถ้าไม่สวมจะบันทึกภาพเต็ม + ภาพขยายลง Drive E: อัตโนมัติ"
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

      {agentOff && (
        <StatusBanner tone="yellow" label="AI agent ปิดอยู่">
          ตั้ง <code>GEMINI_API_KEY</code> (หรือ <code>ANTHROPIC_API_KEY</code>) ใน .env หรือวางโมเดล <code>helmet_det.pt</code> ที่ root แล้วรีสตาร์ต server
        </StatusBanner>
      )}
      {status?.agent_error && (
        <StatusBanner tone="red" label="AI agent หยุดชั่วคราว">
          {status.agent_error} — ระบบยังจับภาพมอไซต่อ แต่จะไม่มีคำตัดสินจนกว่า API จะกลับมา (เติมเครดิตที่ AI Studio หรือใส่ <code>ANTHROPIC_API_KEY</code>) ถ้ามี <code>helmet_det.pt</code> โมเดลในเครื่องจะตัดสินแทน
        </StatusBanner>
      )}
      {status && !status.archive_ok && (
        <StatusBanner tone="red" label="ไม่พบไดรฟ์เก็บหลักฐาน">
          {status.archive_dir} เข้าไม่ได้ ระบบยังตรวจต่อแต่จะไม่มีไฟล์ภาพลงไดรฟ์
        </StatusBanner>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="มอไซที่จับภาพวันนี้" value={fmtNum(t.captures)} sub={`รอตรวจ ${fmtNum(t.pending ?? 0)} คัน`} loading={!status} />
        <StatTile label="ไม่สวมหมวกวันนี้" value={fmtNum(t.no_helmet)} tone="red" sub={`สงสัยรอยืนยัน ${fmtNum(t.suspect ?? 0)} · สะสม ${fmtNum(status?.total_no_helmet)}`} loading={!status} />
        <StatTile label="สวมหมวก" value={fmtNum(t.helmet)} tone="green" sub={`มองไม่ชัด ${fmtNum(t.unclear ?? 0)}`} loading={!status} />
        <StatTile label="ตรวจล่าสุด" value={status?.last_check ? fmtTime(status.last_check) : '–'} sub={status ? `คิวรอ ${status.queue} · เก็บที่ ${status.archive_dir}` : ''} loading={!status} />
      </div>

      <Tabs
        label="มุมมอง"
        value={tab}
        onChange={setTab}
        tabs={TABS.map((x) => ({ ...x, badge: x.id === 'violations' ? violations?.length : x.id === 'suspects' ? suspects?.length : x.id === 'captures' ? captures?.length : cameras?.length }))}
      />

      {tab === 'violations' && (
        <EvidenceGrid items={violations} onOpen={setOpen} empty={`ยังไม่พบผู้ไม่สวมหมวกใน ${hours} ชม.ที่ผ่านมา`} />
      )}

      {tab === 'suspects' && (
        <>
          <p className="text-sm text-slate-600 -mt-1">
            AI ในเครื่องสงสัยว่าไม่สวมหมวก ยังไม่บันทึกลงไดรฟ์จนกว่า {status?.agent_model || 'Gemini'} หรือคนจะยืนยัน ระบบส่งยืนยันเองทีละ 5 ภาพทุก 30 วินาทีเมื่อโควตาพอ
          </p>
          <EvidenceGrid items={suspects} onOpen={setOpen} empty={`ไม่มีภาพที่สงสัยใน ${hours} ชม.ที่ผ่านมา`} />
        </>
      )}

      {tab === 'captures' && (
        <>
          <div className="flex flex-wrap items-center gap-2 -mt-1">
            <Button size="sm" variant="primary" onClick={judgePending} loading={bulk} disabled={!vlm?.ready} className="ml-auto">
              ให้ AI ในเครื่องตรวจภาพที่ยังไม่ชัดทั้งหมด
            </Button>
          </div>
          <EvidenceGrid items={captures} onOpen={setOpen} compact empty="ยังไม่มีภาพมอไซที่จับได้ รอรอบสแกนถัดไปหรือกด 'ตรวจตอนนี้' ที่แท็บกล้อง" />
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
              <input type="checkbox" checked={onlyMoto} onChange={(e) => setOnlyMoto(e.target.checked)} className="accent-blue-600" />
              เฉพาะกล้องที่เห็นมอไซ
            </label>
            <span className="ml-auto text-xs text-slate-500">{camList.length} จาก {cameras?.length ?? 0} กล้อง · เรียงตามไม่สวมหมวก / จับภาพ / มอไซตอนนี้</span>
          </div>
          {!cameras ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {[1, 2, 3, 4, 5, 6].map((n) => <Skeleton key={n} className="h-24" />)}
            </div>
          ) : camList.length === 0 ? (
            <EmptyState title="ไม่มีกล้องตรงเงื่อนไข" description="ลองปิดตัวกรอง 'เฉพาะกล้องที่เห็นมอไซ'" />
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
                        <span className="tabular-nums">มอไซตอนนี้ {c.motorcycles}</span>
                        <span className="tabular-nums">จับภาพวันนี้ {c.captures}</span>
                        {c.no_helmet > 0 && <span className="tabular-nums font-medium text-red-700">ไม่สวมหมวก {c.no_helmet}</span>}
                      </div>
                      {c.district && <span className="block text-xs text-slate-500 truncate">{c.district}</span>}
                    </div>
                    <Button size="sm" onClick={() => checkNow(c)} loading={checking === c.camid} disabled={agentOff}>
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
              <img src={open.frame} alt="ภาพเต็มจากกล้อง" className="w-full rounded-lg border border-slate-200 bg-slate-900" />
              <img src={open.crop} alt="ภาพขยายมอไซ" className="w-full rounded-lg border border-slate-200 bg-slate-900" />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone={VERDICT_TONE[open.verdict]} dot={open.verdict === 'no_helmet'}>{open.verdict_th}</Badge>
              {open.riders != null && <span className="text-slate-700">ผู้ขับขี่/ซ้อน {open.riders} คน · ไม่สวม {open.no_helmet ?? 0} คน</span>}
              {open.confidence != null && <span className="text-slate-500 tabular-nums">ความมั่นใจ {Math.round(open.confidence * 100)}%</span>}
              {open.source && <span className="text-slate-500">ตรวจโดย {open.source === 'local' ? 'โมเดลในเครื่อง' : open.source}</span>}
            </div>
            {open.note && <p className="text-sm text-slate-700">{open.note}</p>}
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-200">
              <span className="text-xs text-slate-500">วิเคราะห์ใหม่ด้วย:</span>
              <Button size="sm" variant="primary" onClick={() => judge(open, 'cloud')} loading={judging === 'cloud'} disabled={!status?.agent || status.agent === 'off' || !!judging}>
                {status?.agent_model || 'Gemini'}{status?.agent_error ? ' (หยุดชั่วคราว)' : ''}
              </Button>
            </div>
            {open.archive && <p className="text-xs text-slate-500 break-all">ไฟล์หลักฐาน: {open.archive}</p>}
          </div>
        )}
      </Modal>
    </div>
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
                <Badge tone={VERDICT_TONE[it.verdict]} dot={it.verdict === 'no_helmet'}>{it.verdict_th}</Badge>
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
              {!compact && it.note && <p className="text-xs text-slate-600 mt-1 line-clamp-2">{it.note}</p>}
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}

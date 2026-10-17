import { useCallback, useEffect, useState } from 'react';
import { fetchCalendar, addTeamEvent, deleteTeamEvent } from '../../lib/api.js';
import { kindLabel, sourceLabel, timeRange, bangkokInputToEpoch, requestMapLayer } from '../../lib/events.js';
import { BKK_DISTRICTS } from '../../lib/bkkDistricts.js';
import { Card, SectionHeader, Badge, Button, Skeleton, ErrorState, Truncate, FOCUS } from './ui.jsx';

const POLL_MS = 60000;
const SECTIONS = [
  ['ongoing', 'กำลังปิดอยู่'],
  ['today', 'วันนี้'],
  ['tomorrow', 'พรุ่งนี้'],
  ['week', '7 วันข้างหน้า'],
];
const KIND_TONE = { closure: 'red', diversion: 'yellow', event: 'blue' };
const KIND_OPTIONS = ['closure', 'diversion', 'event', 'run', 'concert', 'ceremony'];
const NOT_TEAM = 'เพิ่มได้เฉพาะทีมงาน';
const INPUT = `h-9 w-full rounded-lg border border-slate-300 bg-white px-2.5 text-sm text-slate-900 ${FOCUS}`;
const EMPTY_FORM = { title: '', kind: 'closure', place: '', district: '', start: '', end: '', detail: '' };

function placeLine(i) {
  return [i.place, i.district ? `เขต${i.district}` : ''].filter(Boolean).join(' · ');
}

function ItemRow({ item, canDelete, onDelete, onMap, busy }) {
  const place = placeLine(item);
  return (
    <li className="py-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 min-w-0">
            <Badge tone={KIND_TONE[item.kind] || 'neutral'}>{kindLabel(item.kind)}</Badge>
            <Truncate text={item.title} className="text-sm font-medium text-slate-900" />
          </div>
          {place && <p className="text-[13px] text-slate-600 mt-0.5">{place}</p>}
          <p className="text-xs text-slate-700 tabular-nums mt-0.5">{timeRange(item.start, item.end)}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            {sourceLabel(item.source)}
            {item.url && /^https?:\/\//.test(item.url) && (
              <>
                {' · '}
                <a href={item.url} target="_blank" rel="noreferrer" className={`text-blue-700 hover:underline rounded ${FOCUS}`}>
                  ดูประกาศ
                </a>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {item.lat != null && item.lng != null && (
            <Button size="sm" onClick={() => onMap(item)}>
              ดูบนแผนที่
            </Button>
          )}
          {canDelete && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onDelete(item)}>
              ลบ
            </Button>
          )}
        </div>
      </div>
    </li>
  );
}

function TeamForm({ onAdded, onNotTeam }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    const title = form.title.trim();
    const start = bangkokInputToEpoch(form.start);
    const end = bangkokInputToEpoch(form.end);
    if (!title || start == null || end == null) {
      setError('กรอกหัวข้อ วันเริ่ม และวันสิ้นสุดให้ครบ');
      return;
    }
    if (start >= end) {
      setError('วันสิ้นสุดต้องอยู่หลังวันเริ่ม');
      return;
    }
    const body = { title, kind: form.kind, place: form.place.trim(), start, end };
    if (form.district) body.district = form.district;
    if (form.detail.trim()) body.detail = form.detail.trim();
    setBusy(true);
    setError('');
    try {
      const item = await addTeamEvent(body);
      setForm(EMPTY_FORM);
      onAdded(item);
    } catch (err) {
      if (err.status === 403) {
        onNotTeam();
        setError(NOT_TEAM);
      } else if (err.status === 422) {
        setError('ข้อมูลไม่ถูกต้อง ตรวจหัวข้อ วันเวลา และเขตอีกครั้ง');
      } else {
        setError('เพิ่มไม่สำเร็จ ลองใหม่อีกครั้ง');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3" aria-label="เพิ่มงาน">
      <label className="flex flex-col gap-1 sm:col-span-2 text-xs text-slate-600">
        หัวข้อ
        <input className={INPUT} value={form.title} maxLength={120} onChange={set('title')} required />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-600">
        ประเภท
        <select className={INPUT} value={form.kind} onChange={set('kind')}>
          {KIND_OPTIONS.map((k) => (
            <option key={k} value={k}>
              {kindLabel(k)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-600">
        สถานที่
        <input className={INPUT} value={form.place} maxLength={120} onChange={set('place')} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-600">
        เขต (ไม่บังคับ)
        <select className={INPUT} value={form.district} onChange={set('district')}>
          <option value="">ไม่ระบุ</option>
          {BKK_DISTRICTS.map((d) => (
            <option key={d} value={d}>
              เขต{d}
            </option>
          ))}
        </select>
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          วันเริ่ม
          <input type="datetime-local" className={INPUT} value={form.start} onChange={set('start')} required />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          วันสิ้นสุด
          <input type="datetime-local" className={INPUT} value={form.end} onChange={set('end')} required />
        </label>
      </div>
      <label className="flex flex-col gap-1 sm:col-span-2 text-xs text-slate-600">
        รายละเอียด (ไม่บังคับ)
        <textarea
          className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900"
          rows={2}
          maxLength={600}
          value={form.detail}
          onChange={set('detail')}
        />
      </label>
      <div className="sm:col-span-2 flex items-center gap-3 flex-wrap">
        <Button type="submit" variant="primary" loading={busy} disabled={busy}>
          บันทึกงาน
        </Button>
        <span role="status" className="text-xs text-slate-600">
          {error}
        </span>
      </div>
    </form>
  );
}

export default function EventsPanel({ isActive, onNavigate }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [addedIds, setAddedIds] = useState(() => new Set()); // team items added in this session
  const [notTeam, setNotTeam] = useState(''); // the 403 note, for add or delete
  const [busyId, setBusyId] = useState('');

  const load = useCallback(() => {
    return fetchCalendar('bkk')
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

  const onAdded = (item) => {
    setAddedIds((s) => new Set(s).add(item.id));
    setNotTeam('');
    load();
  };

  const onDelete = async (item) => {
    setBusyId(item.id);
    setNotTeam('');
    try {
      await deleteTeamEvent(item.id);
      await load();
    } catch (err) {
      setNotTeam(err.status === 403 ? NOT_TEAM : 'ลบไม่สำเร็จ ลองใหม่อีกครั้ง');
    } finally {
      setBusyId('');
    }
  };

  const onMap = () => {
    requestMapLayer('calendar');
    onNavigate?.('map');
  };

  if (!data && !failed) {
    return (
      <Card className="p-4 space-y-3" aria-busy="true">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </Card>
    );
  }
  if (!data) return <ErrorState onRetry={load} />;

  return (
    <div className="space-y-4">
      <Card className="p-4 sm:p-5">
        <SectionHeader
          id="events-title"
          title="ถนนปิดและงานใหญ่ในกรุงเทพฯ"
          description="ดูว่าถนนไหนปิด เบี่ยงจราจร หรือมีงานใหญ่ในช่วง 7 วันข้างหน้า"
        />
        <div className="mt-4 space-y-5">
          {SECTIONS.map(([key, title]) => {
            const items = data[key] || [];
            return (
              <section key={key} aria-labelledby={`events-${key}`}>
                <h4 id={`events-${key}`} className="text-sm font-semibold text-slate-900">
                  {title} <span className="text-slate-500 font-normal tabular-nums">({items.length})</span>
                </h4>
                {items.length === 0 ? (
                  <p className="text-[13px] text-slate-500 mt-2">ไม่มีรายการ</p>
                ) : (
                  <ul className="mt-1 divide-y divide-slate-100">
                    {items.map((item) => (
                      <ItemRow
                        key={item.id}
                        item={item}
                        canDelete={item.source === 'team' && (formOpen || addedIds.has(item.id))}
                        onDelete={onDelete}
                        onMap={onMap}
                        busy={busyId === item.id}
                      />
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
        {failed && <p className="text-xs text-amber-700 mt-3">โหลดข้อมูลล่าสุดไม่สำเร็จ แสดงข้อมูลที่โหลดไว้ก่อนหน้า</p>}
        {notTeam && (
          <p role="status" className="text-xs text-amber-700 mt-3">
            {notTeam}
          </p>
        )}
      </Card>

      <Card className="p-4 sm:p-5">
        <Button variant="ghost" aria-expanded={formOpen} onClick={() => setFormOpen((o) => !o)}>
          {formOpen ? 'ซ่อนฟอร์ม' : 'เพิ่มงาน (ทีมงาน)'}
        </Button>
        {formOpen && <TeamForm onAdded={onAdded} onNotTeam={() => setNotTeam(NOT_TEAM)} />}
      </Card>
    </div>
  );
}

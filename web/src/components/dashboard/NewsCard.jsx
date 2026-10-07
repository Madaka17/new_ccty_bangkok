import { useEffect, useState } from 'react';
import { fetchNews } from '../../lib/api.js';
import { agoText, fmtTime } from './format.js';

// Flood and road-accident news from the whole country (news_feed.py), beside the roads to avoid: the outlet's
// cover picture, the type, how long ago, the headline, the outlet and the province it names. Each is a link to the
// outlet's own page; only headlines and covers are shown, never the story. On wide screens the card takes the
// height of the roads card next to it (DashboardPage) and the list scrolls inside it.
const POLL_MS = 300000;   // the server reads the feeds every 5 minutes too
const SHORT = 5;
const STALE_S = 20 * 60;  // four missed server reads
const KIND = {
  flood: { label: 'น้ำท่วม', cls: 'bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300' },
  accident: { label: 'อุบัติเหตุ', cls: 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300' },
};
// Shown when a story has no cover or the outlet's picture does not load
const KIND_ICON = {
  flood: 'M12 3.5c-3 4.2-6 7.6-6 11a6 6 0 0 0 12 0c0-3.4-3-6.8-6-11z',
  accident: 'M5 16V12l2-5h10l2 5v4M5 16h14M5 16v2M19 16v2M8 13h.01M16 13h.01',
};

function Cover({ src, kind }) {
  const [broken, setBroken] = useState(false);
  const box = 'w-24 aspect-[16/10] shrink-0 overflow-hidden rounded-lg bg-[var(--c-raised)]';
  if (!src || broken) {
    return (
      <span className={`${box} grid place-items-center ${KIND[kind]?.cls || ''}`} aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-7 h-7 opacity-70">
          <path d={KIND_ICON[kind] || KIND_ICON.flood} />
        </svg>
      </span>
    );
  }
  return (
    <span className={box}>
      <img
        src={src}
        alt=""
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
      />
    </span>
  );
}

const FILTERS = [['all', 'ทั้งหมด'], ['flood', 'น้ำท่วม'], ['accident', 'อุบัติเหตุ']];

export default function NewsCard({ isActive }) {
  const [news, setNews] = useState(null);
  const [failed, setFailed] = useState(false);
  const [kind, setKind] = useState('all');
  const [more, setMore] = useState(false);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const load = () =>
      fetchNews()
        .then((d) => {
          if (!alive) return;
          setNews(d);
          setFailed(false);
        })
        .catch(() => alive && setFailed(true));
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  const items = (news?.items || []).filter((i) => kind === 'all' || i.kind === kind);
  const shown = more ? items : items.slice(0, SHORT);
  // What the list is: still loading, never loaded, loaded (maybe empty), or kept from an earlier read because the
  // latest one failed (this page's request, or the server's read of the outlets)
  const read = !!news?.updated_at;
  const stale = read && (failed || !!news.error || Date.now() / 1000 - news.updated_at > STALE_S);
  const state = !news ? (failed ? 'failed' : 'loading') : !read ? (news.error ? 'failed' : 'loading') : 'read';

  return (
    <section aria-labelledby="news-h" className="min-w-0 flex flex-col rounded-md border border-[var(--c-border)] bg-[var(--c-surface)] p-5 sm:p-6 lg:absolute lg:inset-0">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="news-h" className="text-xl font-bold">ข่าวน้ำท่วม อุบัติเหตุ</h2>
        <span className="text-sm text-[var(--c-muted)]">ทั่วประเทศ</span>
      </div>
      <div role="group" aria-label="ประเภทข่าว" className="mt-2 flex flex-wrap gap-1">
        {FILTERS.map(([k, label]) => (
          <button
            key={k}
            type="button"
            aria-pressed={kind === k}
            onClick={() => {
              setKind(k);
              setMore(false);
            }}
            className={`cursor-pointer min-h-9 px-3 rounded-[4px] text-sm font-semibold ${
              kind === k ? 'bg-[var(--c-sel-bg)] text-[var(--c-sel-text)]' : 'text-[var(--c-muted)] hover:bg-[var(--c-raised)] hover:text-[var(--c-ink)]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {state === 'loading' && <p className="mt-4 text-sm text-[var(--c-muted)]">กำลังโหลดข่าว...</p>}
      {state === 'failed' && <p role="status" className="mt-4 text-sm text-[var(--c-muted)]">โหลดข่าวไม่ได้ตอนนี้ ลองใหม่อีกครั้งภายหลัง</p>}
      {state === 'read' && stale && (
        <p role="status" className="mt-3 rounded-[4px] border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          อัปเดตข่าวไม่สำเร็จ แสดงข่าวเมื่อ {fmtTime(news.updated_at)}&nbsp;น. อาจมีข่าวใหม่ที่ยังไม่ขึ้น
        </p>
      )}
      {state === 'read' && items.length === 0 && (
        <p className="mt-4 text-sm text-[var(--c-muted)]">{stale ? 'ไม่มีข่าวเรื่องนี้ในข้อมูลล่าสุดที่โหลดได้' : 'ยังไม่มีข่าวเรื่องนี้ใน 2 วันที่ผ่านมา'}</p>
      )}

      {shown.length > 0 && (
        <ul className="mt-2 -mr-2 pr-2 lg:flex-1 lg:min-h-0 lg:overflow-y-auto scroll-soft">
          {shown.map((i) => (
            <li key={i.id} className="border-t border-[var(--c-border)] first:border-t-0">
              <a href={i.link} target="_blank" rel="noopener noreferrer" className="group flex items-center gap-3 py-2.5">
                <Cover src={i.image} kind={i.kind} />
                <span className="flex-1 min-w-0">
                  <span className="text-[15px] leading-snug text-[var(--c-ink)] line-clamp-2 group-hover:underline" title={i.title}>{i.title}</span>
                  <span className="mt-1 flex items-center gap-1.5 text-xs text-[var(--c-muted)] min-w-0">
                    <span className={`shrink-0 rounded-full px-2 py-px font-semibold ${KIND[i.kind]?.cls || ''}`}>{KIND[i.kind]?.label}</span>
                    <span className="truncate">
                      {i.source}
                      {i.province ? ` · ${i.province}` : ''} · {agoText(i.ts)}
                    </span>
                  </span>
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-[var(--c-border)] pt-2">
        <p className="text-xs text-[var(--c-muted)]">กดที่ข่าวเพื่ออ่านที่เว็บข่าว</p>
        {items.length > SHORT && (
          <button type="button" onClick={() => setMore((v) => !v)} className="cursor-pointer min-h-11 px-2 text-sm font-semibold hover:underline">
            {more ? 'ย่อ' : `ดูข่าวเพิ่ม (${items.length - SHORT})`}
          </button>
        )}
      </div>
    </section>
  );
}

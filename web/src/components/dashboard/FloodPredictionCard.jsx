import { useMemo, useState } from 'react';
import { Card, Badge, Button } from './ui.jsx';

// Color classes that work vibrantly in both Light and Dark themes
const LEVEL_STYLES = {
  ต่ำ: {
    bg: 'bg-emerald-50 dark:bg-emerald-950/30',
    border: 'border-emerald-200 dark:border-emerald-800/50',
    text: 'text-emerald-800 dark:text-emerald-300',
    badgeTone: 'green',
    dot: 'bg-emerald-500',
    label: 'ปกติ',
  },
  ปานกลาง: {
    bg: 'bg-amber-50 dark:bg-amber-950/40',
    border: 'border-amber-300 dark:border-amber-700/60',
    text: 'text-amber-900 dark:text-amber-200',
    badgeTone: 'yellow',
    dot: 'bg-amber-500',
    label: 'เฝ้าระวัง',
  },
  สูง: {
    bg: 'bg-rose-50 dark:bg-rose-950/50',
    border: 'border-rose-300 dark:border-rose-700/70',
    text: 'text-rose-900 dark:text-rose-200',
    badgeTone: 'red',
    dot: 'bg-rose-500',
    label: 'เสี่ยงสูง',
  },
};

const WATCH_BADGES = {
  red: { tone: 'red', label: 'เสี่ยงสูง' },
  orange: { tone: 'yellow', label: 'เฝ้าระวัง' },
  yellow: { tone: 'yellow', label: 'เฝ้าระวัง' },
  green: { tone: 'green', label: 'ปกติ' },
};

export default function FloodPredictionCard({ prediction = [], modelNote }) {
  const [filter, setFilter] = useState('all'); // 'all' | 'watch' | 'normal'
  const [viewMode, setViewMode] = useState('table'); // 'table' | 'cards'
  const [showFormula, setShowFormula] = useState(false);

  // Grouping & Filtering
  const watchCount = useMemo(
    () => prediction.filter((p) => p.peak_score >= 40).length,
    [prediction]
  );
  const normalCount = prediction.length - watchCount;

  const filteredList = useMemo(() => {
    if (filter === 'watch') return prediction.filter((p) => p.peak_score >= 40);
    if (filter === 'normal') return prediction.filter((p) => p.peak_score < 40);
    return prediction;
  }, [prediction, filter]);

  if (!prediction || prediction.length === 0) {
    return null;
  }

  // Get hour timestamps from the first item
  const hourHeaders = prediction[0]?.hours || [];

  return (
    <Card className="p-4 sm:p-5 flex flex-col gap-4">
      {/* 1. Header & Context */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-cream-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-base font-semibold text-ink-900 leading-6">
              การคาดการณ์น้ำท่วมล่วงหน้า 1–6 ชั่วโมง
            </h2>
            {watchCount > 0 ? (
              <span className="inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full font-medium bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                เฝ้าระวัง {watchCount} โซน
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                ทุกโซนปกติ
              </span>
            )}
          </div>
          <p className="text-xs text-ink-600 mt-1">
            ประเมินความเสี่ยงน้ำท่วมรายโซนจาก ระดับน้ำในคลอง/แม่น้ำ + น้ำท่วมขังบนถนน + ปริมาณฝนคาดการณ์ 6 ชม. ข้างหน้า
          </p>
        </div>

        {/* View mode toggle & Formula button */}
        <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
          <div className="inline-flex rounded-lg border border-cream-200 dark:border-slate-700 bg-cream-50 dark:bg-slate-800/80 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setViewMode('table')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === 'table'
                  ? 'bg-white dark:bg-slate-700 text-ink-900 shadow-xs'
                  : 'text-ink-600 hover:text-ink-900'
              }`}
            >
              ตารางไทม์ไลน์
            </button>
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === 'cards'
                  ? 'bg-white dark:bg-slate-700 text-ink-900 shadow-xs'
                  : 'text-ink-600 hover:text-ink-900'
              }`}
            >
              การ์ดรายโซน
            </button>
          </div>

          <button
            type="button"
            onClick={() => setShowFormula((prev) => !prev)}
            className="text-xs px-2 py-1 rounded-lg border border-cream-200 dark:border-slate-700 text-ink-600 hover:text-ink-900 hover:bg-cream-100 dark:hover:bg-slate-800 transition-colors"
            title="คลิกเพื่อดูสูตรคำนวณคะแนนความเสี่ยง"
          >
            {showFormula ? 'ซ่อนสูตร' : 'ℹ️ วิธีคิดคะแนน'}
          </button>
        </div>
      </div>

      {/* 2. Collapsible Scoring Formula */}
      {showFormula && (
        <div className="p-3.5 rounded-xl bg-lavender-50/60 dark:bg-slate-800/60 border border-lavender-200/80 dark:border-slate-700 text-xs text-ink-700 space-y-1.5 animate-fadeIn">
          <p className="font-semibold text-ink-900 flex items-center gap-1.5">
            <span>📐</span> ที่มาของคะแนนความเสี่ยง (0 – 100 คะแนน):
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2 pt-1 text-[11px]">
            <div className="p-2 rounded-lg bg-white/80 dark:bg-slate-900/60 border border-cream-200 dark:border-slate-700">
              <span className="font-medium text-ink-900 block mb-0.5">1. ฐานระดับน้ำเดิม</span>
              • ล้นตลิ่ง/ถนนท่วมขัง: +45 คะแนน<br />
              • คลอง/แม่น้ำใกล้ล้น: +25 คะแนน<br />
              • ฝนที่ตกแล้ววันนี้: +(ฝน มม. ÷ 3)
            </div>
            <div className="p-2 rounded-lg bg-white/80 dark:bg-slate-900/60 border border-cream-200 dark:border-slate-700">
              <span className="font-medium text-ink-900 block mb-0.5">2. ฝนสะสมคาดการณ์</span>
              • +2.5 คะแนน ต่อฝนสะสมทุก 1 มม.<br />
              • เพิ่มตามปริมาณฝนที่จะตกสะสมถึงชั่วโมงนั้น
            </div>
            <div className="p-2 rounded-lg bg-white/80 dark:bg-slate-900/60 border border-cream-200 dark:border-slate-700">
              <span className="font-medium text-ink-900 block mb-0.5">3. โอกาสเกิดฝน</span>
              • +10 คะแนน เมื่อโอกาสฝนตก ≥ 70%<br />
              • ช่วยเตือนล่วงหน้าก่อนเมฆฝนก่อตัว
            </div>
          </div>
          {modelNote && (
            <p className="text-[10px] text-ink-500 pt-1">
              หมายเหตุแบบจำลอง: {modelNote}
            </p>
          )}
        </div>
      )}

      {/* 3. Legend & Filter Chips */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-2.5 rounded-xl bg-cream-50 dark:bg-slate-800/50 border border-cream-200 dark:border-slate-800">
        {/* Risk Level Badges */}
        <div className="flex items-center gap-3 text-xs flex-wrap">
          <span className="font-medium text-ink-700">ระดับความเสี่ยง:</span>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            <span className="text-ink-800 font-medium">ปกติ</span>
            <span className="text-ink-500 text-[11px]">(0–39)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
            <span className="text-ink-800 font-medium">เฝ้าระวัง</span>
            <span className="text-ink-500 text-[11px]">(40–69)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500" />
            <span className="text-ink-800 font-medium">เสี่ยงสูง</span>
            <span className="text-ink-500 text-[11px]">(70–100)</span>
          </div>
        </div>

        {/* Filter buttons */}
        <div className="flex items-center gap-1.5 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
              filter === 'all'
                ? 'bg-ink-900 text-white dark:bg-slate-100 dark:text-slate-900'
                : 'bg-white dark:bg-slate-700 text-ink-600 hover:text-ink-900'
            }`}
          >
            ทั้งหมด ({prediction.length})
          </button>
          <button
            type="button"
            onClick={() => setFilter('watch')}
            className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
              filter === 'watch'
                ? 'bg-amber-600 text-white'
                : 'bg-white dark:bg-slate-700 text-ink-600 hover:text-amber-700'
            }`}
          >
            ⚠️ เฝ้าระวัง ({watchCount})
          </button>
          <button
            type="button"
            onClick={() => setFilter('normal')}
            className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
              filter === 'normal'
                ? 'bg-emerald-600 text-white'
                : 'bg-white dark:bg-slate-700 text-ink-600 hover:text-emerald-700'
            }`}
          >
            🟢 ปกติ ({normalCount})
          </button>
        </div>
      </div>

      {/* 4. Timeline Table View */}
      {viewMode === 'table' && (
        <div className="overflow-x-auto rounded-xl border border-cream-200 dark:border-slate-800">
          <table className="w-full text-sm border-collapse min-w-[720px]">
            <thead>
              <tr className="bg-cream-100/70 dark:bg-slate-800/80 border-b border-cream-200 dark:border-slate-800 text-ink-600 text-xs font-medium">
                <th className="text-left py-2.5 px-3.5 w-60">โซนและเขตพื้นที่</th>
                <th className="text-center py-2.5 px-2 w-28">ฝนตกสะสมล่าสุด</th>
                {hourHeaders.map((h) => (
                  <th key={h.h} className="text-center py-2.5 px-1.5 min-w-[70px]">
                    <div className="font-semibold text-ink-900">+{h.h} ชม.</div>
                    {h.at && (
                      <div className="text-[10px] text-ink-500 font-normal">
                        {h.at} น.
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-cream-100 dark:divide-slate-800 bg-white dark:bg-slate-900/60">
              {filteredList.map((p) => {
                const peakStyle = LEVEL_STYLES[p.peak_level] || LEVEL_STYLES['ต่ำ'];
                const isWatch = p.peak_score >= 40;

                return (
                  <tr
                    key={p.zone}
                    className={`transition-colors hover:bg-cream-50/70 dark:hover:bg-slate-800/40 ${
                      isWatch ? 'bg-amber-50/20 dark:bg-amber-950/10' : ''
                    }`}
                  >
                    {/* Zone Info Column */}
                    <td className="py-3 px-3.5 align-middle">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-ink-900 text-sm">
                          {p.zone}
                        </span>
                        <span
                          className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${peakStyle.bg} ${peakStyle.border} ${peakStyle.text}`}
                        >
                          {peakStyle.label} (สูงสุด {p.peak_score})
                        </span>
                      </div>
                      <p className="text-[11px] text-ink-500 mt-1 line-clamp-1" title={p.areas}>
                        {p.areas}
                      </p>
                      {/* Sub summary: forecast rain total */}
                      <p className="text-[10px] text-ink-400 mt-0.5">
                        ฝนคาดการณ์ 6 ชม.: {p.rain_6h || 0} มม. (โอกาส {p.prob_6h || 0}%)
                      </p>
                    </td>

                    {/* Current Observed Rain */}
                    <td className="text-center py-3 px-2 align-middle">
                      <div className="inline-flex flex-col items-center justify-center py-1 px-2 rounded-lg bg-cream-100/60 dark:bg-slate-800/60 border border-cream-200 dark:border-slate-700/60">
                        <span className="text-[11px] text-ink-500">🌧️ ตกแล้ว</span>
                        <span className="text-xs font-semibold tabular-nums text-ink-800">
                          {p.rain_observed_mm || 0} มม.
                        </span>
                      </div>
                    </td>

                    {/* 6 Hour Forecast Boxes */}
                    {p.hours.map((h) => {
                      const st = LEVEL_STYLES[h.level] || LEVEL_STYLES['ต่ำ'];
                      return (
                        <td key={h.h} className="p-1.5 align-middle">
                          <div
                            className={`rounded-xl text-center py-2 px-1 border transition-transform hover:scale-[1.03] ${st.bg} ${st.border} ${st.text}`}
                            title={`เวลา ${h.at || `+${h.h} ชม.`} น. · คะแนนความเสี่ยง ${h.score}/100 (${st.label}) · ฝนสะสมคาดการณ์ ${h.cum_mm} มม.`}
                          >
                            <div className="flex items-center justify-center gap-1">
                              <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                              <span className="text-sm font-bold tabular-nums leading-none">
                                {h.score}
                              </span>
                            </div>
                            <div className="text-[10px] font-medium mt-1 leading-none opacity-85">
                              {st.label}
                            </div>
                            <div className="text-[10px] tabular-nums mt-1 font-normal opacity-75 leading-none">
                              ฝน {h.cum_mm} มม.
                            </div>
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* 5. Cards View (Mobile & Tablet Friendly) */}
      {viewMode === 'cards' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredList.map((p) => {
            const peakStyle = LEVEL_STYLES[p.peak_level] || LEVEL_STYLES['ต่ำ'];
            const isWatch = p.peak_score >= 40;

            return (
              <div
                key={p.zone}
                className={`p-4 rounded-xl border transition-all ${
                  isWatch
                    ? 'border-amber-300 dark:border-amber-700/70 bg-amber-50/30 dark:bg-slate-900/90'
                    : 'border-cream-200 dark:border-slate-800 bg-white dark:bg-slate-900/60'
                }`}
              >
                {/* Card Header */}
                <div className="flex items-start justify-between gap-2 pb-2.5 border-b border-cream-100 dark:border-slate-800">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-ink-900 text-sm">{p.zone}</span>
                      <span
                        className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${peakStyle.bg} ${peakStyle.border} ${peakStyle.text}`}
                      >
                        {peakStyle.label}
                      </span>
                    </div>
                    <p className="text-xs text-ink-600 mt-1">{p.areas}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="text-xs text-ink-500 block">คะแนนสูงสุด</span>
                    <span className={`text-base font-bold tabular-nums ${peakStyle.text}`}>
                      {p.peak_score}
                      <span className="text-xs font-normal text-ink-500">/100</span>
                    </span>
                  </div>
                </div>

                {/* Rain Metrics */}
                <div className="grid grid-cols-2 gap-2 my-3 text-xs">
                  <div className="p-2 rounded-lg bg-cream-50 dark:bg-slate-800/50 border border-cream-200 dark:border-slate-700/50">
                    <span className="text-ink-500 block text-[11px]">ฝนตกสะสมล่าสุด</span>
                    <span className="font-semibold text-ink-800 tabular-nums">
                      🌧️ {p.rain_observed_mm || 0} มม.
                    </span>
                  </div>
                  <div className="p-2 rounded-lg bg-cream-50 dark:bg-slate-800/50 border border-cream-200 dark:border-slate-700/50">
                    <span className="text-ink-500 block text-[11px]">ฝนคาดการณ์ 6 ชม.</span>
                    <span className="font-semibold text-ink-800 tabular-nums">
                      {p.rain_6h || 0} มม. (โอกาส {p.prob_6h || 0}%)
                    </span>
                  </div>
                </div>

                {/* 6-Hour Timeline Pills */}
                <div>
                  <span className="text-[11px] font-medium text-ink-500 block mb-1.5">
                    แนวโน้มคะแนนความเสี่ยงรายชั่วโมง (+1 ถึง +6 ชม.):
                  </span>
                  <div className="grid grid-cols-6 gap-1.5">
                    {p.hours.map((h) => {
                      const st = LEVEL_STYLES[h.level] || LEVEL_STYLES['ต่ำ'];
                      return (
                        <div
                          key={h.h}
                          className={`rounded-lg py-1.5 px-0.5 text-center border ${st.bg} ${st.border} ${st.text}`}
                          title={`เวลา ${h.at || `+${h.h} ชม.`} น. · เสี่ยง ${h.score}/100 · ฝนสะสม ${h.cum_mm} มม.`}
                        >
                          <span className="text-[10px] text-ink-500 block leading-none">
                            +{h.h}h
                          </span>
                          <span className="text-xs font-bold tabular-nums block mt-1 leading-none">
                            {h.score}
                          </span>
                          <span className="text-[9px] tabular-nums block mt-1 opacity-75 leading-none">
                            {h.cum_mm} มม.
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { aiStreamUrl, fetchAIStats, fetchTrafficSummary, fetchWaterSummary, sendChat, setAIConf, setAIFps, switchAICamera } from '../lib/api.js';

const SUGGESTIONS = [
  'สรุปสถานการณ์ทั้งหมดตอนนี้',
  'ถนนไหนติดที่สุดตอนนี้',
  'วิเคราะห์น้ำท่วมและฝนวันนี้ พื้นที่ไหนต้องเฝ้าระวัง',
  'พรุ่งนี้มีพายุฝนไหม ฝนตกหนักช่วงไหน',
  'วันนี้มีอุบัติเหตุที่ไหนบ้าง เขตไหนเสี่ยงสุด',
  'เขตไหนรถหนาแน่นสุดจากกล้อง กทม.',
  'ขับรถลุยน้ำท่วมยังไงให้ปลอดภัย',
  'เบอร์ฉุกเฉินที่ควรรู้',
  'ช่วยแปลประโยคนี้เป็นอังกฤษ: วันนี้ฝนตกหนักมาก',
  'แนะนำร้านอาหารแถวสยาม',
];
const WELCOME = 'สวัสดี! ถามได้ทุกเรื่อง ทั้งข้อมูลสดของเมือง (จราจรทุกสาย กล้องนับรถ กทม. 500+ ตัว น้ำท่วม-ฝน-พายุ 24 ชม.รายพื้นที่ อุบัติเหตุและเหตุการณ์ สถิติรายเขต) และคำถามทั่วไปอะไรก็ได้ เช่น แปลภาษา สรุปข้อความ คำนวณ สุขภาพ ท่องเที่ยว หรือให้ช่วยเขียนอะไรก็ได้เลย';
const LEVEL_CLS = { โล่ง: 'bg-sage-100 text-sage-700', ปานกลาง: 'bg-gold-100 text-gold-700', ติดขัด: 'bg-apricot-100 text-apricot-700' };
const WATCH = {
  green: { label: 'ปกติ', cls: 'bg-sage-100 text-sage-700' },
  yellow: { label: 'ติดตาม', cls: 'bg-gold-100 text-gold-700' },
  orange: { label: 'เฝ้าระวัง', cls: 'bg-apricot-100 text-apricot-700' },
  red: { label: 'เตือนภัย', cls: 'bg-red-100 text-red-700' },
};
const WINDY_RADAR = 'https://embed.windy.com/embed2.html?lat=13.750&lon=100.500&detailLat=13.750&detailLon=100.500&width=340&height=260&zoom=8&level=surface&overlay=radar&product=radar&menu=&message=true&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1';

function Bubble({ role, text, mode }) {
 const me = role === 'user';
 return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className={`flex ${me ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-xl px-4 py-3 text-[15px] leading-relaxed whitespace-pre-wrap ${me ? 'bg-lavender-600 text-white rounded-br-lg' : 'bg-white border border-cream-200 text-ink-900 rounded-bl-lg'}`}>
        {text}
        {!me && mode === 'gemini' && <span className="block mt-1 text-[11px] text-ink-400">Gemini Flash-Lite</span>}
        {!me && mode === 'offline' && <span className="block mt-1 text-[11px] text-ink-400">โหมดออฟไลน์ (สรุปจากข้อมูลสด ยังไม่ได้ใส่ GEMINI_API_KEY)</span>}
      </div>
    </motion.div>
  );
}

export default function AiPage({ active, cameras, camid, onPickCamera, onToast, pendingQuestion, onQuestionConsumed }) {
 const [messages, setMessages] = useState([{ role: 'assistant', content: WELCOME }]);
 const [input, setInput] = useState('');
 const [busy, setBusy] = useState(false);
 const [summary, setSummary] = useState(null);
 const [water, setWater] = useState(null);
 const [showRadar, setShowRadar] = useState(false);
 const [stats, setStats] = useState(null);
 const [streamSrc, setStreamSrc] = useState('');
 const [live, setLive] = useState(false);
 const [showOptions, setShowOptions] = useState(false);
 const [fps, setFps] = useState(5);
 const [conf, setConf] = useState(30);
 const listRef = useRef(null);
 const imgRef = useRef(null);
 const cam = cameras.find((c) => c.camid === camid);

 useEffect(() => {
 if (active && !cam && cameras.length) onPickCamera(cameras[0].camid);
  }, [active, cam, cameras, onPickCamera]);

  // Camera AI feed
 useEffect(() => {
 if (!active || !cam) return;
 let cancelled = false;
 setLive(false);
 switchAICamera(cam)
      .then(() => !cancelled && setStreamSrc(aiStreamUrl(cam.camid)))
      .catch(() => {});
 return () => {
 cancelled = true;
    };
  }, [active, cam?.camid]);

 useEffect(() => {
 if (!active) {
 setStreamSrc('');
 return;
    }
 const id = setInterval(() => {
 fetchAIStats()
        .then((s) => {
 setStats(s);
 if (s.active && s.camid === camid) setLive(true);
        })
        .catch(() => setStats(null));
    }, 1500);
 return () => clearInterval(id);
  }, [active, camid]);

  // Live traffic summary for the side panel
 useEffect(() => {
 if (!active) return;
 let alive = true;
 const tick = () => fetchTrafficSummary(6).then((s) => alive && setSummary(s)).catch(() => {});
 tick();
 const id = setInterval(tick, 60000);
 return () => {
 alive = false;
 clearInterval(id);
    };
  }, [active]);

  // Flood / rain watch for the side panel
 useEffect(() => {
 if (!active) return;
 let alive = true;
 const tick = () => fetchWaterSummary().then((w) => alive && setWater(w)).catch(() => {});
 tick();
 const id = setInterval(tick, 60000);
 return () => {
 alive = false;
 clearInterval(id);
    };
  }, [active]);

  // Question handed over from the dashboard / map
 useEffect(() => {
 if (active && pendingQuestion) {
 onQuestionConsumed?.();
 ask(pendingQuestion);
    }
  }, [active, pendingQuestion]);

 useEffect(() => {
 listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

 const ask = async (text) => {
 const q = (text || input).trim();
 if (!q || busy) return;
 setInput('');
 const next = [...messages, { role: 'user', content: q }];
 setMessages(next);
 setBusy(true);
 try {
 const res = await sendChat(next.filter((m) => m.role !== 'assistant' || m.content !== WELCOME).map((m) => ({ role: m.role, content: m.content })));
 setMessages([...next, { role: 'assistant', content: res.reply, mode: res.mode }]);
    } catch (e) {
 const msg = e?.message === 'rate_limited'
   ? 'ถามบ่อยเกินไป รอสักครู่แล้วลองใหม่นะ'
   : e?.message === 'too_long'
     ? 'ข้อความยาวเกินไป ลองย่อคำถามให้สั้นลง'
     : 'ผู้ช่วยยังไม่ตื่น ลองเปิด run_server.bat แล้วถามใหม่นะ';
 setMessages([...next, { role: 'assistant', content: msg, mode: 'offline' }]);
    } finally {
 setBusy(false);
    }
  };

 const captureView = () => {
 const img = imgRef.current;
 if (!img || !img.naturalWidth) return onToast('ยังไม่มีภาพให้บันทึก รอสักครู่นะ');
 const canvas = document.createElement('canvas');
 canvas.width = img.naturalWidth;
 canvas.height = img.naturalHeight;
 canvas.getContext('2d').drawImage(img, 0, 0);
 const a = document.createElement('a');
 a.href = canvas.toDataURL('image/jpeg', 0.92);
 a.download = `bkk-traffic-${cam?.camid || 'view'}-${Date.now()}.jpg`;
 a.click();
 onToast('บันทึกภาพวิวของคุณเรียบร้อย');
  };

 return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-4 lg:h-[calc(100vh-11rem)] min-h-[560px]">
      {/* Chat */}
      <section className="glass rounded-xl flex flex-col overflow-hidden" aria-label="แชทกับผู้ช่วยการจราจร">
        <div className="px-5 pt-5 pb-3 flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-semibold text-slate-900 leading-7">ถาม AI ได้ทุกเรื่อง</h1>
            <p className="text-[13px] text-slate-600 mt-0.5">ข้อมูลสด: จราจร · กล้องนับรถ · น้ำท่วม-ฝน-พายุ · อุบัติเหตุ · สถิติ — และคำถามทั่วไปทุกหัวข้อ</p>
          </div>
          {summary?.ready && (
            <span className="hidden sm:inline-flex items-center gap-1.5 rounded-lg bg-sage-50 border border-sage-100 px-3 py-1.5 text-xs text-sage-700">
              <span className="live-dot w-2 h-2 rounded-full bg-sage-400" />
              ดูอยู่ {summary.road_count} สาย
            </span>
          )}
        </div>

        <div ref={listRef} className="flex-1 overflow-y-auto scroll-soft px-5 py-2 space-y-3 min-h-[280px]">
          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} text={m.content} mode={m.mode} />
          ))}
          {busy && (
            <div className="flex items-center gap-2 text-sm text-ink-600 pl-10">
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" />
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce [animation-delay:120ms]" />
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce [animation-delay:240ms]" />
              กำลังดูเส้นจราจรให้...
            </div>
          )}
        </div>

        <div className="px-5 pb-5 pt-2">
          <div className="flex flex-wrap gap-1.5 mb-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" onClick={() => ask(s)} disabled={busy} className="cursor-pointer rounded-lg bg-white text-slate-700 border border-slate-300 px-3 py-1.5 text-xs hover:bg-slate-50 transition-colors duration-200 disabled:opacity-50">
                {s}
              </button>
            ))}
          </div>
          <form
 onSubmit={(e) => {
 e.preventDefault();
 ask();
            }}
 className="flex items-center gap-2 rounded-lg bg-white border border-cream-200 pl-5 pr-1.5 py-1.5 focus-within:border-lavender-400 transition-colors duration-200"
          >
            <label htmlFor="chat-input" className="sr-only">ถามผู้ช่วยการจราจร</label>
            <input id="chat-input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="ถามอะไรก็ได้ เช่น รัชดาตอนนี้ติดไหม, พรุ่งนี้ฝนตกไหม, ช่วยแปลประโยคนี้..." className="flex-1 bg-transparent outline-none text-base text-ink-900 placeholder:text-ink-400" disabled={busy} />
            <motion.button type="submit" whileTap={{ scale: 0.95 }} disabled={busy || !input.trim()} className="cursor-pointer rounded-lg bg-blue-600 text-white px-5 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors duration-200 disabled:opacity-50">
              ถาม
            </motion.button>
          </form>
        </div>
      </section>

      {/* Side: live insight + camera AI */}
      <aside className="flex flex-col gap-3 lg:overflow-y-auto scroll-soft">
        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <p className="text-xs text-ink-600 flex-1">เฝ้าระวังฝน / น้ำท่วม รายพื้นที่ (24 ชม.)</p>
            <button type="button" onClick={() => setShowRadar((v) => !v)} aria-expanded={showRadar} className="cursor-pointer h-7 px-2 rounded-md text-[11px] text-slate-600 hover:bg-slate-100">
              {showRadar ? 'ซ่อนเรดาร์' : 'เรดาร์ฝน'}
            </button>
          </div>
          {water?.flood_roads && (
            <p className="text-[11px] text-ink-600 mb-2">
              ถนนท่วม {water.flood_roads.flooding} จุด · ท่วมเล็กน้อย {water.flood_roads.slight} จุด · ล้นตลิ่ง {(water.river_counts?.overflow || 0) + (water.canal_counts?.overflow || 0)} สถานี
            </p>
          )}
          {!water?.weather?.length ? (
            <p className="text-sm text-ink-400">กำลังโหลดพยากรณ์ฝน...</p>
          ) : (
            <ul className="space-y-1">
              {water.weather.map((z) => {
                const w = WATCH[z.watch] || WATCH.green;
                return (
                  <li key={z.id}>
                    <button type="button" onClick={() => ask(`${z.name} (${z.areas}) วิเคราะห์น้ำท่วม ฝน พายุ และแนวทางป้องกัน`)} className="cursor-pointer w-full text-left rounded-lg px-2 py-1.5 hover:bg-cream-100 transition-colors duration-200">
                      <div className="flex items-center gap-2">
                        <span className="flex-1 min-w-0 text-sm text-ink-900 line-clamp-1">{z.name}</span>
                        <span className={`rounded-lg px-2 py-0.5 text-[11px] font-medium ${w.cls}`}>{w.label}</span>
                      </div>
                      <p className="text-[11px] text-ink-600 mt-0.5 line-clamp-1">
                        ฝน {z.rain_24h} มม. · ลม {z.gust_max} กม./ชม.
                        {z.storm_at ? ` · พายุ ${z.storm_at}` : z.peak_at ? ` · หนักสุด ${z.peak_at}` : ''}
                        {z.flood_roads?.length ? ` · ท่วม ${z.flood_roads.length} จุด` : ''}
                        {z.stations_overflow?.length ? ` · ล้น ${z.stations_overflow[0]}` : ''}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {showRadar && (
            <div className="mt-2 rounded-lg overflow-hidden border border-cream-200 bg-cream-100 h-[260px]">
              <iframe src={WINDY_RADAR} width="100%" height="100%" frameBorder="0" title="เรดาร์ฝน Windy" loading="lazy" className="w-full h-full block" />
            </div>
          )}
        </div>

        <div className="glass rounded-xl p-4">
          <p className="text-xs text-ink-600 mb-2">ติดขัดมากที่สุดตอนนี้</p>
          {!summary?.ready ? (
            <p className="text-sm text-ink-400">กำลังโหลดเส้นจราจร...</p>
          ) : (
            <ul className="space-y-1.5">
              {summary.congested.map((r) => (
                <li key={r.name}>
                  <button type="button" onClick={() => ask(`${r.name} ตอนนี้ระบายรถเป็นยังไง`)} className="cursor-pointer w-full text-left flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-cream-100 transition-colors duration-200">
                    <span className="flex-1 min-w-0 text-sm text-ink-900 line-clamp-1">{r.name}</span>
                    <span className={`rounded-lg px-2 py-0.5 text-[11px] font-medium ${LEVEL_CLS[r.level]}`}>{r.level}</span>
                    <span className="text-sm text-ink-900 w-8 text-right">{r.flow}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <p className="text-xs text-ink-600 flex-1">กล้อง AI นับรถ</p>
            <button type="button" onClick={() => setShowOptions((v) => !v)} aria-expanded={showOptions} className="cursor-pointer h-7 px-2 rounded-md text-[11px] text-slate-600 hover:bg-slate-100">
              ตั้งค่า
            </button>
          </div>
          <label htmlFor="ai-cam" className="sr-only">เลือกกล้อง</label>
          <select id="ai-cam" value={camid || ''} onChange={(e) => onPickCamera(e.target.value)} className="cursor-pointer w-full rounded-lg bg-white border border-cream-200 px-3 py-2 text-xs text-ink-900 outline-none focus:border-lavender-400">
            {cameras.map((c) => (
              <option key={c.camid} value={c.camid}>
                [{c.province}] {c.short_title}
              </option>
            ))}
          </select>
          <div className="mt-2 relative rounded-lg overflow-hidden bg-cream-100 aspect-video">
            {streamSrc && <img ref={imgRef} src={streamSrc} alt="ภาพสดพร้อมผลตรวจจับรถ" onError={() => setLive(false)} className={`w-full h-full object-contain transition-opacity duration-300 ${live ? 'opacity-100' : 'opacity-0'}`} />}
            {!live && (
              <div className="absolute inset-0 flex items-center justify-center text-xs text-ink-600">
                <span className="w-6 h-6 rounded-full border-4 border-slate-200 border-t-blue-600 animate-spin mr-2" />
                กำลังมองดูถนน...
              </div>
            )}
          </div>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            {[
              ['รถยนต์', stats?.cars],
              ['มอไซ', stats?.motorcycles],
              ['บรรทุก', stats?.trucks],
            ].map(([label, v]) => (
              <div key={label} className="rounded-lg bg-white border border-cream-200 px-2 py-1.5">
                <p className="text-[11px] text-slate-500">{label}</p>
                <p className="text-base text-ink-900 tabular-nums font-medium leading-5">{v ?? 0}</p>
              </div>
            ))}
          </div>
          <AnimatePresence>
            {showOptions && (
              <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
                <div className="mt-3 flex gap-1">
                  {[1, 3, 5, 10].map((v) => (
                    <button
 key={v}
 type="button"
 onClick={() => {
 setFps(v);
 setAIFps(v).catch(() => {});
                      }}
 aria-pressed={fps === v}
 className={`cursor-pointer flex-1 rounded-lg py-1 text-xs transition-colors duration-200 ${fps === v ? 'bg-lavender-600 text-white' : 'bg-lavender-50 text-lavender-700'}`}
                    >
                      {v} FPS
                    </button>
                  ))}
                </div>
                <label htmlFor="ai-conf" className="block text-[11px] text-ink-600 mt-2 mb-1">
                  ความมั่นใจขั้นต่ำ <span className="text-ink-900">{conf}%</span>
                </label>
                <input
 id="ai-conf"
 type="range"
 min="10"
 max="90"
 step="5"
 value={conf}
 onChange={(e) => {
 setConf(Number(e.target.value));
 setAIConf(Number(e.target.value) / 100).catch(() => {});
                  }}
 className="w-full accent-lavender-600"
                />
              </motion.div>
            )}
          </AnimatePresence>
          <button type="button" onClick={captureView} className="cursor-pointer mt-3 w-full rounded-lg bg-blue-600 text-white py-2 text-sm font-semibold hover:bg-blue-700 transition-colors duration-200">
            บันทึกวิวของฉัน
          </button>
        </div>
      </aside>
    </div>
  );
}

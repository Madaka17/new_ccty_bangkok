import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CarIcon, BikeIcon, TruckIcon, SparkleIcon, CameraIcon, SettingsIcon } from './Icons.jsx';
import { aiStreamUrl, fetchAIStats, fetchTrafficSummary, sendChat, setAIConf, setAIFps, switchAICamera } from '../lib/api.js';

const SUGGESTIONS = ['สรุปสภาพจราจรตอนนี้', 'ถนนไหนติดที่สุดตอนนี้', 'สุขุมวิทกับพระราม 4 ระบายรถเป็นยังไง', 'จากลาดพร้าวไปสีลม ควรไปทางไหน'];
const WELCOME = 'สวัสดี! ฉันดูเส้นจราจรทุกสายในกรุงเทพฯ ให้อยู่ ถามได้เลยว่าถนนไหนระบายรถดี ถนนไหนควรเลี่ยง หรือให้สรุปภาพรวมก็ได้นะ';
const LEVEL_CLS = { โล่ง: 'bg-sage-100 text-sage-700', ปานกลาง: 'bg-gold-100 text-gold-700', ติดขัด: 'bg-apricot-100 text-apricot-700' };

function Bubble({ role, text, mode }) {
 const me = role === 'user';
 return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className={`flex ${me ? 'justify-end' : 'justify-start'}`}>
      {!me && (
        <span className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center mr-2 shrink-0 mt-1">
          <SparkleIcon className="w-4 h-4" />
        </span>
      )}
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
    } catch {
 setMessages([...next, { role: 'assistant', content: 'ผู้ช่วยยังไม่ตื่น ลองเปิด run_server.bat แล้วถามใหม่นะ', mode: 'offline' }]);
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
          <div className="w-11 h-11 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
            <SparkleIcon />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="font-serif text-xl sm:text-2xl font-semibold text-ink-900">AI ผู้ช่วยการจราจร</h2>
            <p className="text-sm text-ink-600">วิเคราะห์การระบายรถทุกเส้นทางจากเส้นแผนที่จราจรสด</p>
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
            <input id="chat-input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="ถามเรื่องถนน เช่น รัชดาตอนนี้ติดไหม..." className="flex-1 bg-transparent outline-none text-base text-ink-900 placeholder:text-ink-400" disabled={busy} />
            <motion.button type="submit" whileTap={{ scale: 0.95 }} disabled={busy || !input.trim()} className="cursor-pointer rounded-lg bg-blue-600 text-white px-5 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors duration-200 disabled:opacity-50">
              ถาม
            </motion.button>
          </form>
        </div>
      </section>

      {/* Side: live insight + camera AI */}
      <aside className="flex flex-col gap-3 lg:overflow-y-auto scroll-soft">
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
                    <span className="font-serif text-sm text-ink-900 w-8 text-right">{r.flow}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="glass rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <CameraIcon className="w-4 h-4" />
            <p className="text-xs text-ink-600 flex-1">กล้อง AI นับรถ</p>
            <button type="button" onClick={() => setShowOptions((v) => !v)} aria-expanded={showOptions} aria-label="ตัวเลือกเพิ่มเติม" className="cursor-pointer w-7 h-7 rounded-full flex items-center justify-center hover:bg-lavender-50">
              <SettingsIcon className="w-4 h-4" />
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
              [CarIcon, stats?.cars],
              [BikeIcon, stats?.motorcycles],
              [TruckIcon, stats?.trucks],
            ].map(([Icon, v], i) => (
              <div key={i} className="rounded-lg bg-white border border-cream-200 px-2 py-1.5 flex items-center gap-1.5">
                <Icon className="w-5 h-5" />
                <span className="font-serif text-lg text-ink-900 tabular-nums">{v ?? 0}</span>
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
                  ความมั่นใจขั้นต่ำ <span className="font-serif text-ink-900">{conf}%</span>
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

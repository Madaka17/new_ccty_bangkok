import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { fetchTrafficSummary, sendChat } from '../lib/api.js';
import { PageHeader } from './dashboard/primitives.jsx';
import { PAGE_TITLES } from './Sidebar.jsx';

// The map library is big: load it only when an answer has a route to draw
const RouteCard = lazy(() => import('./RouteCard.jsx'));

const SUGGESTIONS = ['จากบางนาไปสีลม เลี่ยงน้ำท่วม', 'ถนนไหนใน กทม. ควรเลี่ยงตอนนี้', 'จังหวัดไหนน้ำท่วมหนักสุดตอนนี้', 'พรุ่งนี้กรุงเทพฯ ฝนจะตกไหม', 'คาดว่าน้ำจะท่วมที่ไหนบ้าง'];
const WELCOME = 'สวัสดี! ถามได้ทั่วประเทศ เช่น จังหวัดไหนน้ำท่วม เชียงใหม่รถติดไหม พรุ่งนี้ขอนแก่นฝนตกไหม ถ้าเป็นกรุงเทพฯ ถามได้ละเอียดถึงรายถนน และให้หาทางไปแบบเลี่ยงน้ำท่วมได้ พิมพ์ว่า "จาก ... ไป ..." หรือถามเรื่องทั่วไป เช่น แปลภาษา สรุปข้อความ ก็ได้';

function Bubble({ role, text, mode, model, route }) {
 const me = role === 'user';
 return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className={`flex ${me ? 'justify-end' : 'justify-start'}`}>
      <div className={`${route ? 'w-full sm:w-[85%]' : 'max-w-[85%]'} rounded-xl px-4 py-3 text-[15px] leading-relaxed whitespace-pre-wrap ${me ? 'bg-lavender-600 text-white rounded-br-lg' : 'bg-white border border-cream-200 text-ink-900 rounded-bl-lg'}`}>
        {text}
        {route && (
          <Suspense fallback={<div className="mt-3 h-56 rounded-lg bg-cream-100" />}>
            <RouteCard route={route} />
          </Suspense>
        )}
        {!me && mode === 'local' && <span className="block mt-1 text-[11px] text-ink-400">AI: {model || 'Qwen'}</span>}
        {!me && mode === 'offline' && <span className="block mt-1 text-[11px] text-ink-400">AI ไม่พร้อม คำตอบนี้สรุปจากข้อมูลสดโดยตรง</span>}
      </div>
    </motion.div>
  );
}

export default function AiPage({ active, pendingQuestion, onQuestionConsumed }) {
 const [messages, setMessages] = useState([{ role: 'assistant', content: WELCOME }]);
 const [input, setInput] = useState('');
 const [busy, setBusy] = useState(false);
 const [summary, setSummary] = useState(null);
 // Where the person is, for "ไปสีลมทางไหน" with no start: off / asking / on / denied
 const [loc, setLoc] = useState(null);
 const [locState, setLocState] = useState('off');
 const [needLoc, setNeedLoc] = useState(false);
 const listRef = useRef(null);

  // Live traffic summary for the header chip (roads being watched)
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

 const ask = async (text, where = loc, base = messages) => {
 const q = (text || input).trim();
 if (!q || busy) return;
 setInput('');
 const next = [...base, { role: 'user', content: q }];
 setMessages(next);
 setBusy(true);
 setNeedLoc(false);
 try {
 const res = await sendChat(next.filter((m) => m.role !== 'assistant' || m.content !== WELCOME).map((m) => ({ role: m.role, content: m.content })), where);
 setMessages([...next, { role: 'assistant', content: res.reply, mode: res.mode, model: res.model, route: res.route }]);
 setNeedLoc(!!res.need_location);
    } catch (e) {
 const msg = e?.message === 'rate_limited'
   ? 'ถามบ่อยเกินไป รอสักครู่แล้วลองใหม่นะ'
   : e?.message === 'too_long'
     ? 'ข้อความยาวเกินไป ลองย่อคำถามให้สั้นลง'
     : 'AI ยังไม่พร้อม ลองถามใหม่อีกครั้งในอีกสักครู่';
 setMessages([...next, { role: 'assistant', content: msg, mode: 'offline' }]);
    } finally {
 setBusy(false);
    }
  };

 // Share the position; if the bot just asked where the trip starts, ask that question again with it
 const useMyLocation = () => {
 if (locState === 'on') {
 setLoc(null);
 setLocState('off');
 return;
    }
 if (!navigator.geolocation) {
 setLocState('denied');
 return;
    }
 setLocState('asking');
 navigator.geolocation.getCurrentPosition(
      (p) => {
 const where = { lat: p.coords.latitude, lng: p.coords.longitude };
 setLoc(where);
 setLocState('on');
 const lastQ = needLoc && [...messages].reverse().find((m) => m.role === 'user');
 if (lastQ) ask(lastQ.content, where, messages.slice(0, messages.lastIndexOf(lastQ)));
      },
      () => setLocState('denied'),
      { timeout: 10000, maximumAge: 300000 }
    );
  };

  const fresh = messages.length === 1;
  const locLabel = { off: 'ใช้ตำแหน่งของฉัน', asking: 'กำลังหาตำแหน่ง...', on: 'ใช้ตำแหน่งของฉันอยู่ (กดเพื่อปิด)', denied: 'ไม่ได้รับตำแหน่ง ลองอีกครั้ง' }[locState];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={PAGE_TITLES.ai}
        description="ถามเรื่องรถติด น้ำท่วม ฝน ได้ทั่วประเทศ กรุงเทพฯ ละเอียดถึงรายถนน หรือถามเรื่องทั่วไปก็ได้"
        actions={
          summary?.ready && (
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-sage-50 border border-sage-100 px-3 py-1.5 text-xs text-sage-700">
              <span className="live-dot w-2 h-2 rounded-full bg-sage-400" />
              ติดตามถนน {summary.road_count} สาย
            </span>
          )
        }
      />

      <section className="glass rounded-xl flex flex-col overflow-hidden lg:h-[calc(100vh-13rem)] min-h-[480px]" aria-label="แชทกับ AI">
        <div ref={listRef} className="flex-1 overflow-y-auto scroll-soft px-5 pt-5 pb-2 space-y-3 min-h-[280px]">
          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} text={m.content} mode={m.mode} model={m.model} route={m.route} />
          ))}
          {fresh && (
            <div className="flex flex-wrap gap-2 pt-1" aria-label="ตัวอย่างคำถาม">
              {SUGGESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => ask(q)}
                  className="cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[13px] text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors duration-150"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
          {busy && (
            <div className="flex items-center gap-2 text-sm text-ink-600 pl-10">
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce" />
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce [animation-delay:120ms]" />
              <span className="w-2 h-2 rounded-full bg-slate-400 animate-bounce [animation-delay:240ms]" />
              กำลังหาคำตอบให้...
            </div>
          )}
        </div>

        <div className="px-5 pb-5 pt-2 space-y-2">
          <button
            type="button"
            onClick={useMyLocation}
            disabled={locState === 'asking' || busy}
            aria-pressed={locState === 'on'}
            className={`cursor-pointer inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[13px] transition-colors duration-150 disabled:opacity-60 ${
              locState === 'on' ? 'border-sage-300 bg-sage-50 text-sage-700' : needLoc ? 'border-blue-500 bg-blue-50 text-blue-700 ring-2 ring-blue-200' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z" />
              <circle cx="12" cy="9.5" r="2.5" />
            </svg>
            {locLabel}
          </button>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask();
            }}
            className="flex items-center gap-2 rounded-lg bg-white border border-cream-200 pl-5 pr-1.5 py-1.5 focus-within:border-lavender-400 transition-colors duration-200"
          >
            <label htmlFor="chat-input" className="sr-only">พิมพ์คำถาม</label>
            <input id="chat-input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="ถามอะไรก็ได้ เช่น อยุธยาน้ำท่วมไหม, รัชดาตอนนี้ติดไหม, พรุ่งนี้เชียงใหม่ฝนตกไหม..." className="flex-1 min-w-0 bg-transparent outline-none text-base text-ink-900 placeholder:text-ink-400" disabled={busy} />
            <motion.button type="submit" whileTap={{ scale: 0.95 }} disabled={busy || !input.trim()} className="cursor-pointer rounded-lg bg-blue-600 text-white px-5 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors duration-200 disabled:opacity-50">
              ถาม
            </motion.button>
          </form>
        </div>
      </section>
    </div>
  );
}

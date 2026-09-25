import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { fetchTrafficSummary, sendChat } from '../lib/api.js';

const WELCOME = 'สวัสดี! ถามได้ทุกเรื่อง ทั้งข้อมูลสดของเมือง (จราจรทุกสาย กล้องนับรถ กทม. 500+ ตัว น้ำท่วม-ฝน-พายุ 24 ชม.รายพื้นที่ อุบัติเหตุและเหตุการณ์ สถิติรายเขต) และคำถามทั่วไปอะไรก็ได้ เช่น แปลภาษา สรุปข้อความ คำนวณ สุขภาพ ท่องเที่ยว หรือให้ช่วยเขียนอะไรก็ได้เลย';

function Bubble({ role, text, mode, model }) {
 const me = role === 'user';
 return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className={`flex ${me ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-xl px-4 py-3 text-[15px] leading-relaxed whitespace-pre-wrap ${me ? 'bg-lavender-600 text-white rounded-br-lg' : 'bg-white border border-cream-200 text-ink-900 rounded-bl-lg'}`}>
        {text}
        {!me && mode === 'local' && <span className="block mt-1 text-[11px] text-ink-400">AI: {model || 'Qwen'}</span>}
        {!me && mode === 'offline' && <span className="block mt-1 text-[11px] text-ink-400">โหมดออฟไลน์ (สรุปจากข้อมูลสด เชื่อมต่อโมเดล AI ไม่ได้)</span>}
      </div>
    </motion.div>
  );
}

export default function AiPage({ active, pendingQuestion, onQuestionConsumed }) {
 const [messages, setMessages] = useState([{ role: 'assistant', content: WELCOME }]);
 const [input, setInput] = useState('');
 const [busy, setBusy] = useState(false);
 const [summary, setSummary] = useState(null);
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

 const ask = async (text) => {
 const q = (text || input).trim();
 if (!q || busy) return;
 setInput('');
 const next = [...messages, { role: 'user', content: q }];
 setMessages(next);
 setBusy(true);
 try {
 const res = await sendChat(next.filter((m) => m.role !== 'assistant' || m.content !== WELCOME).map((m) => ({ role: m.role, content: m.content })));
 setMessages([...next, { role: 'assistant', content: res.reply, mode: res.mode, model: res.model }]);
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

 return (
    <div className="flex flex-col lg:h-[calc(100vh-11rem)] min-h-[560px]">
      {/* Chat */}
      <section className="glass rounded-xl flex-1 flex flex-col overflow-hidden" aria-label="แชทกับผู้ช่วยการจราจร">
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
            <Bubble key={i} role={m.role} text={m.content} mode={m.mode} model={m.model} />
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

    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { StatTile } from './dashboard/primitives.jsx';
import { aiStreamUrl, fetchAIStats, setAIConf, setAIFps, setAINightMode, switchAICamera } from '../lib/api.js';
import AccuracyPanel from './yolo/AccuracyPanel.jsx';
import { PROVINCE_TONE } from '../lib/store.js';

const EMPTY = { cars: 0, motorcycles: 0, trucks: 0, total: 0, level: 'free', traffic_level: '', latency_ms: 0, fps: 0, active: false };

// Level comes from the backend, which looks at both how many vehicles are visible and whether they move
const LEVEL_TONE = {
 free: { text: 'ถนนโล่งสบาย', cls: 'bg-sage-100 text-sage-700', hint: 'ไปได้เลย ทางสะดวก' },
 moderate: { text: 'รถพอประมาณ', cls: 'bg-gold-100 text-gold-700', hint: 'เผื่อเวลาอีกนิดนะ' },
 heavy: { text: 'รถค่อนข้างเยอะ', cls: 'bg-apricot-100 text-apricot-700', hint: 'ลองเลี่ยงเส้นนี้ก่อนดีไหม' },
};
const levelTone = (level) => LEVEL_TONE[level] || LEVEL_TONE.free;

export default function YoloPage({ active, cameras, favorites, camid, incidents, onPickCamera, onToast, onAsk }) {
 const [stats, setStats] = useState(EMPTY);
 const [streamSrc, setStreamSrc] = useState('');
 const [feedState, setFeedState] = useState('loading'); // loading | live | error
 const [showOptions, setShowOptions] = useState(false);
 const [fps, setFps] = useState(10);
 const [conf, setConf] = useState(20);
 const [nightMode, setNightMode] = useState(false);
 const imgRef = useRef(null);
 const cam = cameras.find((c) => c.camid === camid);

 useEffect(() => {
 if (active && !cam && cameras.length) {
 const defCam = cameras.find((c) => c.camid === 'ITICM_BMAMI0188') || cameras[0];
 onPickCamera(defCam.camid);
    }
  }, [active, cam, cameras, onPickCamera]);

 useEffect(() => {
 if (!active || !cam) return;
 let cancelled = false;
 setFeedState('loading');
 setStats(EMPTY);
    (async () => {
 try {
 await switchAICamera(cam);
      } catch {
 if (!cancelled) setFeedState('error');
 return;
      }
 if (!cancelled) setStreamSrc(aiStreamUrl(cam.camid));
    })();
 return () => {
 cancelled = true;
    };
  }, [active, cam?.camid]);

  useEffect(() => {
    if (!active) return;
    const id = setInterval(async () => {
      try {
        const s = await fetchAIStats();
        setStats(s);
        if (typeof s.night_mode === 'boolean') setNightMode(s.night_mode);
        if (s.active && s.camid === camid) setFeedState('live');
      } catch {
        setFeedState('error');
      }
    }, 1000);
    return () => clearInterval(id);
  }, [active, camid]);

  useEffect(() => {
    if (!active) {
      setStreamSrc('');
      setShowOptions(false);
    }
  }, [active]);

  const toggleNightMode = async () => {
    const next = !nightMode;
    setNightMode(next);
    try {
      await setAINightMode(next);
      onToast?.(next ? '🌙 เปิดโหมดกลางคืน (เร่งแสงสว่าง)' : '☀️ ปิดโหมดกลางคืน');
    } catch {}
  };

  const applyFps = (v) => {
    setFps(v);
    setAIFps(v).catch(() => {});
  };
  const applyConf = (v) => {
    setConf(v);
    setAIConf(v / 100).catch(() => {});
  };

 const captureView = () => {
 const img = imgRef.current;
 if (!img || !img.naturalWidth) {
 onToast('ยังไม่มีภาพให้บันทึก รอสักครู่นะ');
 return;
    }
 const w = img.naturalWidth;
 const h = img.naturalHeight;
 const pad = 40;
 const footer = 150;
 const canvas = document.createElement('canvas');
 canvas.width = w + pad * 2;
 canvas.height = h + pad + footer;
 const ctx = canvas.getContext('2d');
 ctx.fillStyle = '#f8fafc';
 ctx.fillRect(0, 0, canvas.width, canvas.height);
 ctx.save();
 ctx.beginPath();
 ctx.roundRect(pad, pad, w, h, 12);
 ctx.clip();
 ctx.drawImage(img, pad, pad, w, h);
 ctx.restore();
 const level = levelTone(stats.level);
 const y = pad + h + 44;
 ctx.fillStyle = '#0f172a';
 ctx.font = '600 26px "Prompt", "Poppins", sans-serif';
 ctx.fillText('BKK StreetSmart', pad, y);
 ctx.font = '400 18px "Prompt", "Poppins", sans-serif';
 ctx.fillStyle = '#475569';
 ctx.fillText(`${cam?.short_title || ''}`, pad, y + 30);
 ctx.fillText(`รถยนต์ ${stats.cars || 0}  ·  มอเตอร์ไซค์ ${stats.motorcycles || 0}  ·  รถบรรทุก ${stats.trucks || 0}  ·  ${level.text}  ·  ${new Date().toLocaleString('th-TH')}`, pad, y + 60);
 const a = document.createElement('a');
 a.href = canvas.toDataURL('image/jpeg', 0.92);
 a.download = `yolo11x-${cam?.camid || 'view'}-${Date.now()}.jpg`;
 a.click();
 onToast('บันทึกภาพวิวของคุณเรียบร้อย');
  };

 const level = levelTone(stats.level);
 const incident = (incidents?.camera || []).find((i) => i.camid === camid);
 const tone = cam ? PROVINCE_TONE[cam.province] || 'bg-cream-200 text-ink-600' : '';
 const favList = cameras.filter((c) => favorites.has(c.camid));

 return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
      <section className="glass rounded-xl p-5 sm:p-6" aria-label="AI ตรวจจับรถ YOLO11x">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-slate-900 leading-7">AI ตรวจจับรถสด</h1>
          <p className="text-[13px] text-slate-600 mt-0.5">YOLO11x นับรถยนต์ มอเตอร์ไซค์ รถบรรทุก จากภาพกล้องที่เลือก ประมาณ 5 ภาพต่อวินาที</p>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <label htmlFor="yolo-cam" className="text-sm text-ink-600">กล้อง</label>
          <select id="yolo-cam" value={camid || ''} onChange={(e) => onPickCamera(e.target.value)} className="cursor-pointer flex-1 min-w-[220px] rounded-lg bg-white border border-cream-200 px-4 py-2.5 text-sm text-ink-900 focus:border-lavender-400 outline-none">
            {cameras.map((c) => (
              <option key={c.camid} value={c.camid}>
                [{c.province}] {c.short_title}
              </option>
            ))}
          </select>
          {cam && <span className={`rounded-lg px-3 py-1 text-xs font-medium ${tone}`}>{cam.province}</span>}
        </div>

        <div className="mt-4 relative rounded-lg overflow-hidden bg-cream-100 aspect-video">
          {streamSrc && (
            <img
              ref={imgRef}
              src={streamSrc}
              alt="ภาพสดจากกล้องพร้อมผลตรวจจับรถ"
              onError={() => setFeedState('error')}
              style={nightMode ? { filter: 'brightness(1.16) contrast(1.08)' } : undefined}
              className={`w-full h-full object-contain bg-cream-100 transition-all duration-300 ${feedState === 'live' ? 'opacity-100' : 'opacity-0'}`}
            />
          )}
          {feedState !== 'live' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-sm text-ink-600 bg-slate-50">
              {feedState === 'loading' ? (
                <>
                  <span className="w-9 h-9 rounded-full border-4 border-slate-200 border-t-blue-600 animate-spin" />
                  YOLO11x กำลังมองดูถนนให้คุณ...
                </>
              ) : (
                <>
                  <p className="font-medium text-ink-900">AI ยังไม่ทำงาน</p>
                  <p className="text-xs">เปิด run_server.bat แล้วลองใหม่อีกครั้งนะ</p>
                </>
              )}
            </div>
          )}
          {feedState === 'live' && <span className={`absolute bottom-3 left-3 rounded-lg px-3 py-1 text-xs font-medium  ${level.cls}`}>{level.text}</span>}
          {incident && (
            <div role="alert" className="absolute top-3 left-3 right-3 rounded-lg bg-red-600 text-white px-4 py-2.5 flex items-start gap-3">
              <div className="min-w-0">
                <p className="font-semibold text-sm">{incident.kind === 'breakdown' ? 'รถเสีย / จอดกีดขวางเลน' : 'อุบัติเหตุ'} · AI ตรวจพบ</p>
                <p className="text-xs opacity-90 line-clamp-2">{incident.description || `รถจอดนิ่ง ${incident.stopped_s} วินาทีขณะรถคันอื่นวิ่ง`}</p>
              </div>
            </div>
          )}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <motion.button type="button" whileTap={{ scale: 0.97 }} onClick={captureView} className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-blue-600 text-white px-5 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors duration-200">
            บันทึกวิวของฉัน
          </motion.button>
          <button
            type="button"
            onClick={toggleNightMode}
            className={`cursor-pointer inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
              nightMode
                ? 'bg-amber-500 hover:bg-amber-600 text-white shadow-md shadow-amber-500/20'
                : 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50'
            }`}
            title="เร่งความสว่างและคอนทราสต์ของภาพในเวลากลางคืน ช่วยให้มองเห็นถนนและรถในเงามืดได้ชัดเจนขึ้น"
          >
            <span>{nightMode ? '🌙 โหมดกลางคืน: เปิด' : '🌙 โหมดกลางคืน (เร่งแสงสว่าง)'}</span>
          </button>
          <button type="button" onClick={() => onAsk(cam?.short_title || '')} className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-white text-slate-800 border border-slate-300 px-4 py-2.5 text-sm hover:bg-slate-50 transition-colors duration-200">
            ถามผู้ช่วยเรื่องถนนนี้
          </button>
          <div className="relative">
            <button type="button" onClick={() => setShowOptions((v) => !v)} aria-expanded={showOptions} className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-white border border-slate-300 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50 transition-colors duration-200">
              ตัวเลือกเพิ่มเติม
            </button>
            <AnimatePresence>
              {showOptions && (
                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }} className="absolute left-0 bottom-full mb-2 z-10 glass-strong rounded-xl p-4 w-80">
                  <p className="text-xs text-ink-600 mb-2">ความเร็วประมวลผล (FPS)</p>
                  <div className="flex gap-1.5">
                    {[5, 10, 15, 20].map((v) => (
                      <button key={v} type="button" onClick={() => applyFps(v)} aria-pressed={fps === v} className={`cursor-pointer flex-1 rounded-lg py-1.5 text-sm font-medium transition-colors duration-200 ${fps === v ? 'bg-lavender-600 text-white ' : 'bg-lavender-50 text-lavender-700 hover:bg-lavender-100'}`}>
                        {v} FPS
                      </button>
                    ))}
                  </div>
                  <label htmlFor="yolo-conf" className="block text-xs text-ink-600 mt-4 mb-1">
                    ความมั่นใจขั้นต่ำ <span className="text-ink-900">{conf}%</span>
                  </label>
                  <input id="yolo-conf" type="range" min="10" max="90" step="5" value={conf} onChange={(e) => applyConf(Number(e.target.value))} className="w-full accent-lavender-600" />
                  
                  <div className="pt-3 mt-3 border-t border-slate-200 flex items-center justify-between">
                    <div>
                      <p className="text-xs font-medium text-slate-800">โหมดเร่งแสงกลางคืน (Night Boost)</p>
                      <p className="text-[11px] text-slate-500">ดึงแสงในเงามืดด้วย CLAHE + Gamma</p>
                    </div>
                    <button
                      type="button"
                      onClick={toggleNightMode}
                      className={`cursor-pointer relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 ${nightMode ? 'bg-amber-500' : 'bg-slate-300'}`}
                      aria-pressed={nightMode}
                    >
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${nightMode ? 'translate-x-6' : 'translate-x-1'}`} />
                    </button>
                  </div>

                  <p className="text-[11px] text-ink-400 mt-3">
                    หน่วง {stats.latency_ms || 0} ms · {stats.fps || 0} FPS
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </section>

      <aside className="flex flex-col gap-3">
        <div className="grid grid-cols-3 lg:grid-cols-1 gap-3">
          <StatTile label="รถยนต์" value={stats.cars || 0} />
          <StatTile label="มอเตอร์ไซค์" value={stats.motorcycles || 0} />
          <StatTile label="รถบรรทุก" value={stats.trucks || 0} />
        </div>
        <div className={`rounded-xl px-5 py-4 ${level.cls}`}>
          <p className="text-xs opacity-80">หน้ากล้องตอนนี้</p>
          <p className="text-lg font-semibold">{incident ? (incident.kind === 'breakdown' ? 'มีรถเสียกีดขวาง' : 'เกิดอุบัติเหตุ') : feedState === 'live' ? level.text : 'กำลังดูถนนให้อยู่...'}</p>
          {feedState === 'live' && <p className="text-sm mt-0.5">{level.hint}</p>}
        </div>
        {favList.length > 0 && (
          <div className="glass rounded-xl p-4">
            <p className="text-xs text-ink-600 mb-2">กล้องโปรดของคุณ</p>
            <div className="flex flex-col gap-1.5 max-h-56 overflow-y-auto scroll-soft">
              {favList.map((c) => (
                <button key={c.camid} type="button" onClick={() => onPickCamera(c.camid)} aria-pressed={c.camid === camid} className={`cursor-pointer text-left rounded-lg px-3 py-2 text-sm transition-colors duration-200 ${c.camid === camid ? 'bg-lavender-100 text-lavender-700' : 'hover:bg-lavender-50 text-ink-900'}`}>
                  <span className="line-clamp-1">{c.short_title}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </aside>

      {/* Manual-vs-AI accuracy check: full width under the stream */}
      <div className="lg:col-span-2">
        <AccuracyPanel active={active} stats={stats} camTitle={cam?.short_title} onToast={onToast} />
      </div>
    </div>
  );
}

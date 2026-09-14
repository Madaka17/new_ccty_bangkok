import { useCallback, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import TopBar from './components/TopBar.jsx';
import SidePanel from './components/SidePanel.jsx';
import CityWindow from './components/CityWindow.jsx';
import AiPage from './components/AiPage.jsx';
import MapPage from './components/MapPage.jsx';
import DashboardPage from './components/DashboardPage.jsx';
import YoloPage from './components/YoloPage.jsx';
import { fetchCameras, fetchAIStats, fetchIncidents, fetchSurveyRanking, fetchRoadCameras } from './lib/api.js';
import { useActiveCameras, useFavorites, useUserName } from './lib/store.js';

const PAGES = ['dashboard', 'cameras', 'map', 'yolo', 'ai'];

function pageFromHash() {
 const h = window.location.hash.replace(/^#\/?/, '');
 return PAGES.includes(h) ? h : 'dashboard';
}

export default function App() {
 const [cameras, setCameras] = useState([]);
 const [favorites, toggleFav] = useFavorites();
 const { active, toggle, remove, clear, addMany } = useActiveCameras();
 const [userName, saveName] = useUserName();
 const [page, setPage] = useState(pageFromHash);
 const [filter, setFilter] = useState('all');
 const [query, setQuery] = useState('');
 const [userPos, setUserPos] = useState(null);
 const [aiCamid, setAiCamid] = useState('ITICM_BMAMI0188');
 const [pendingQuestion, setPendingQuestion] = useState('');
 const [aiActive, setAiActive] = useState(false);
 const [toast, setToast] = useState('');
 const [incidents, setIncidents] = useState(null);
 const [camStatus, setCamStatus] = useState({}); // camid -> latest AI measurement (level, rate, ...)

 useEffect(() => {
 fetchCameras().then(setCameras).catch(() => setCameras([]));
  }, []);

  // Automatically remove stale / non-existent camera IDs from active slots
 useEffect(() => {
 if (!cameras.length || !active.length) return;
 const validSet = new Set(cameras.map((c) => c.camid));
 const dead = active.filter((id) => !validSet.has(id));
 if (dead.length > 0) {
 dead.forEach((id) => remove(id));
    }
  }, [cameras, active, remove]);

  // Hash routing
 useEffect(() => {
 const onHash = () => setPage(pageFromHash());
 window.addEventListener('hashchange', onHash);
 return () => window.removeEventListener('hashchange', onHash);
  }, []);

 const navigate = useCallback((p) => {
 setPage(p);
 window.location.hash = `/${p}`;
 window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  // Light AI heartbeat for the bell
 useEffect(() => {
 let alive = true;
 const tick = () =>
 fetchAIStats()
        .then((s) => alive && setAiActive(!!s.active))
        .catch(() => alive && setAiActive(false));
 tick();
 const id = setInterval(tick, 5000);
 return () => {
 alive = false;
 clearInterval(id);
    };
  }, []);

 const showToast = useCallback((msg) => {
 setToast(msg);
 setTimeout(() => setToast(''), 2600);
  }, []);

  // Per-camera traffic level for the camera page pills
 useEffect(() => {
 let alive = true;
 const tick = () =>
 fetchSurveyRanking()
        .then((r) => alive && setCamStatus(Object.fromEntries(r.cameras.filter((c) => c.ts).map((c) => [c.camid, c]))))
        .catch(() => {});
 tick();
 const id = setInterval(tick, 60000);
 return () => {
 alive = false;
 clearInterval(id);
    };
  }, []);

  // Accident alerts: poll, toast when a new one appears
 useEffect(() => {
 let alive = true;
 let known = null;
 const tick = () =>
 fetchIncidents()
        .then((d) => {
 if (!alive) return;
 setIncidents(d);
 const all = [...d.camera, ...d.longdo];
 if (known) {
 const fresh = all.filter((i) => !known.has(i.id));
 if (fresh.length) {
 const f = fresh[0];
 showToast(`${f.kind === 'breakdown' ? 'รถเสีย' : 'อุบัติเหตุ'}: ${f.title}${fresh.length > 1 ? ` และอีก ${fresh.length - 1} จุด` : ''}`);
            }
          }
 known = new Set(all.map((i) => i.id));
        })
        .catch(() => {});
 tick();
 const id = setInterval(tick, 30000);
 return () => {
 alive = false;
 clearInterval(id);
    };
  }, [showToast]);

 const handleFilter = (id) => {
 setFilter(id);
 if (id === 'near' && !userPos) {
 if (!navigator.geolocation) {
 showToast('เบราว์เซอร์นี้ไม่รองรับตำแหน่ง');
 return;
      }
 navigator.geolocation.getCurrentPosition(
        (p) => setUserPos({ lat: p.coords.latitude, lng: p.coords.longitude }),
        () => {
 showToast('ขอตำแหน่งไม่สำเร็จ แสดงกล้องทั้งหมดแทนนะ');
 setFilter('all');
        },
        { timeout: 8000 }
      );
    }
  };

 const openAI = useCallback(
    (camid) => {
 if (camid) setAiCamid(camid);
 navigate('yolo');
    },
    [navigate]
  );

  // Dashboard road rows: open the cameras on that road in the camera page
 const openRoadCameras = useCallback(
 async (road) => {
 let cams = [];
 let nearby = false;
 try {
 cams = await fetchRoadCameras(road);
 if (!cams.length) {
          // No camera on the road itself: fall back to cameras within ~600 m
 cams = await fetchRoadCameras(road, 0.6);
 nearby = true;
        }
      } catch {}
 if (!cams.length) {
 showToast(`ยังไม่มีกล้องใกล้ ${road}`);
 return;
      }
 const ids = cams.slice(0, 3).map((c) => c.camid);
 addMany(ids);
 navigate('cameras');
 showToast(nearby ? `ไม่มีกล้องบน ${road} เปิดกล้องใกล้เคียง ${ids.length} ตัวแทน` : `เปิดกล้องบน ${road} ${ids.length} ตัว`);
    },
    [addMany, navigate, showToast]
  );

 const askAI = useCallback(
    (road) => {
 setPendingQuestion(road ? `${road} ตอนนี้ระบายรถเป็นยังไง ควรเลี่ยงไหม` : '');
 navigate('ai');
    },
    [navigate]
  );

 const activeCams = useMemo(() => active.map((id) => cameras.find((c) => c.camid === id)).filter(Boolean), [active, cameras]);

 return (
    <div className="min-h-full flex flex-col gap-4 pb-6">
      <TopBar
 userName={userName}
 onSaveName={saveName}
 liveCount={activeCams.length}
 totalCount={cameras.length}
 aiActive={aiActive}
 page={page}
 onNavigate={navigate}
      />

      <main className="flex-1 px-4 sm:px-6 min-h-0">
          {page === 'dashboard' && (
            <motion.div key="dashboard" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
              <DashboardPage isActive liveCount={activeCams.length} cameras={cameras} incidents={incidents} onAsk={askAI} onOpenRoad={openRoadCameras} onNavigate={navigate} onOpenAI={openAI} />
            </motion.div>
          )}

          {page === 'cameras' && (
            <motion.div
 key="cameras"
 initial={{ opacity: 0, y: 10 }}
 animate={{ opacity: 1, y: 0 }}
 transition={{ duration: 0.22 }}
 className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4"
            >
              <div className="h-[46vh] lg:h-[calc(100vh-11rem)] lg:sticky lg:top-4">
                <SidePanel
 cameras={cameras}
 camStatus={camStatus}
 favorites={favorites}
 active={active}
 filter={filter}
 onFilter={handleFilter}
 query={query}
 onQuery={setQuery}
 userPos={userPos}
 onToggleActive={toggle}
 onToggleFav={toggleFav}
 onOpenAI={openAI}
 onClearAll={clear}
                />
              </div>
              <section aria-label="หน้าต่างเมือง" className="min-h-[360px]">
                <CityWindow cameras={activeCams} camStatus={camStatus} incidents={incidents} onClose={remove} onOpenAI={openAI} />
              </section>
            </motion.div>
          )}

          {page === 'map' && (
            <motion.div
 key="map"
 initial={{ opacity: 0, y: 10 }}
 animate={{ opacity: 1, y: 0 }}
 transition={{ duration: 0.22 }}
            >
              <MapPage isActive cameras={cameras} active={active} incidents={incidents} onToggle={toggle} onOpenAI={openAI} onToast={showToast} />
            </motion.div>
          )}

          {page === 'yolo' && (
            <motion.div key="yolo" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
              <YoloPage active cameras={cameras} favorites={favorites} camid={aiCamid} incidents={incidents} onPickCamera={setAiCamid} onToast={showToast} onAsk={askAI} />
            </motion.div>
          )}

          {page === 'ai' && (
            <motion.div
 key="ai"
 initial={{ opacity: 0, y: 10 }}
 animate={{ opacity: 1, y: 0 }}
 transition={{ duration: 0.22 }}
            >
              <AiPage active cameras={cameras} camid={aiCamid} onPickCamera={setAiCamid} onToast={showToast} pendingQuestion={pendingQuestion} onQuestionConsumed={() => setPendingQuestion('')} />
            </motion.div>
          )}
      </main>

      <AnimatePresence>
        {toast && (
          <motion.div
 role="status"
 initial={{ opacity: 0, y: 16 }}
 animate={{ opacity: 1, y: 0 }}
 exit={{ opacity: 0, y: 16 }}
 className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] rounded-lg bg-slate-900 text-white px-4 py-2.5 text-sm"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

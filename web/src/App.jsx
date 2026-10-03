import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import Sidebar, { PAGE_TITLES } from './components/Sidebar.jsx';
import { PageHeader } from './components/dashboard/primitives.jsx';
import DashboardPage from './components/DashboardPage.jsx';
import BottomNav from './components/BottomNav.jsx';
import NavIcon from './components/NavIcons.jsx';
import BotFace from './components/BotFace.jsx';
import ThemeToggle from './components/ThemeToggle.jsx';
import AlertPopups from './components/AlertPopups.jsx';
import { fetchCameras, fetchAllCameras, fetchAIStats, fetchIncidents, fetchSurveyRanking, fetchRoadCameras } from './lib/api.js';
import { useActiveCameras, useFavorites } from './lib/store.js';
import { trackView, startHeartbeat } from './lib/telemetry.js';

// Every page but the dashboard (the first page) loads when it is first opened: the maps (maplibre-gl),
// the live video (hls.js) and the camera AI pages stay out of the first download
const RELOADED = 'page-file-reload';
function lazyPage(load) {
  return lazy(() =>
    load().then(
      (mod) => {
        try { sessionStorage.removeItem(RELOADED); } catch {}
        return mod;
      },
      (err) => {
        // A tab left open over a new build asks for page files that build deleted: load the new site, once
        try {
          if (!sessionStorage.getItem(RELOADED)) {
            sessionStorage.setItem(RELOADED, '1');
            window.location.reload();
            return new Promise(() => {});
          }
        } catch {}
        throw err;
      }
    )
  );
}
const CameraWall = lazyPage(() => import('./components/CameraWall.jsx'));
const CityWindow = lazyPage(() => import('./components/CityWindow.jsx'));
const AiPage = lazyPage(() => import('./components/AiPage.jsx'));
const MapPage = lazyPage(() => import('./components/MapPage.jsx'));
const CameraAiPage = lazyPage(() => import('./components/CameraAiPage.jsx'));
const SafetyPage = lazyPage(() => import('./components/SafetyPage.jsx'));
const VisitorsPage = lazyPage(() => import('./components/VisitorsPage.jsx'));
const WaterPage = lazyPage(() => import('./components/WaterPage.jsx'));
const FloodPinPage = lazyPage(() => import('./components/FloodPinPage.jsx'));
const AlertsPage = lazyPage(() => import('./components/AlertsPage.jsx'));

function PageLoading() {
  return (
    <div role="status" className="py-16 grid place-items-center text-sm text-slate-500">
      กำลังโหลดหน้า...
    </div>
  );
}

const PAGES = ['dashboard', 'cameras', 'map', 'safety', 'water', 'report', 'yolo', 'ai', 'alerts', 'visitors', 'enviro'];
// Old links to pages that are now tabs of the camera AI page
const CAMERA_TAB_LINKS = { 'camera-search': 'search', 'bma-count': 'bma', helmet: 'helmet', wrongway: 'wrongway' };

function pageFromHash() {
 const h = window.location.hash.replace(/^#\/?/, '');
 if (CAMERA_TAB_LINKS[h]) return 'yolo';
 if (h === 'report-flood') return 'report';   // the first link handed out for the report page
 return PAGES.includes(h) ? h : 'dashboard';
}

export default function App() {
 const [cameras, setCameras] = useState([]);
 const [favorites, toggleFav] = useFavorites();
 const { active, toggle, remove, clear, addMany } = useActiveCameras();
 const [menuOpen, setMenuOpen] = useState(false);
 const [page, setPage] = useState(pageFromHash);
 const [filter, setFilter] = useState('all');
 const [query, setQuery] = useState('');
 const [userPos, setUserPos] = useState(null);
 const [aiCamid, setAiCamid] = useState('ITICM_BMAMI0188');
 const [cameraTab, setCameraTab] = useState(() => CAMERA_TAB_LINKS[window.location.hash.replace(/^#\/?/, '')] || 'live');
 const [pendingQuestion, setPendingQuestion] = useState('');
 const [aiActive, setAiActive] = useState(false);
 const [toast, setToast] = useState('');
 const [incidents, setIncidents] = useState(null);
 const [camStatus, setCamStatus] = useState({}); // camid -> latest AI measurement (level, rate, ...)
 // Every camera (ours, iTIC, BMA) for the live camera page; the other pages keep ours only
 const [allCameras, setAllCameras] = useState(null);
 const [allFailed, setAllFailed] = useState(false);   // then the page shows ours only

 useEffect(() => {
 fetchCameras().then(setCameras).catch(() => setCameras([]));
  }, []);

  // Loaded when the camera page opens, or at once when cameras are already open (from an earlier visit)
 useEffect(() => {
 if (allCameras || allFailed || !(page === 'cameras' || active.length)) return;
 fetchAllCameras()
      .then((items) => (items.length ? setAllCameras(items) : setAllFailed(true)))
      .catch(() => setAllFailed(true));
  }, [allCameras, allFailed, page, active.length]);
 const liveCameras = allCameras || cameras;
 const aiIds = useMemo(() => new Set(cameras.map((c) => c.camid)), [cameras]);   // the cameras the AI page knows

  // Automatically remove stale / non-existent camera IDs from active slots, once the full list is in
 useEffect(() => {
 if (!allCameras?.length || !active.length) return;
 const validSet = new Set(allCameras.map((c) => c.camid));
 const dead = active.filter((id) => !validSet.has(id));
 if (dead.length > 0) {
 dead.forEach((id) => remove(id));
    }
  }, [allCameras, active, remove]);

  // Visitor telemetry: one view per page, heartbeat while open
 useEffect(() => {
 trackView(page);
  }, [page]);
 useEffect(() => startHeartbeat(), []);

  // Hash routing
 useEffect(() => {
 const onHash = () => {
 const tab = CAMERA_TAB_LINKS[window.location.hash.replace(/^#\/?/, '')];
 if (tab) setCameraTab(tab);
 setPage(pageFromHash());
 };
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
 const id = setInterval(tick, 60000);
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
 const id = setInterval(tick, 60000);
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
 showToast('ไม่ได้รับตำแหน่งของคุณ จึงแสดงกล้องทั้งหมดแทน');
 setFilter('all');
        },
        { timeout: 8000 }
      );
    }
  };

 const openAI = useCallback(
    (camid) => {
 if (camid) setAiCamid(camid);
 setCameraTab('live');
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
 setPendingQuestion(road ? `${road} ตอนนี้รถติดไหม ควรเลี่ยงไหม` : '');
 navigate('ai');
    },
    [navigate]
  );

 const activeCams = useMemo(() => active.map((id) => liveCameras.find((c) => c.camid === id)).filter(Boolean), [active, liveCameras]);

 const openFloodReport = useCallback(() => navigate('report'), [navigate]);

 const sidebarProps = { page, onNavigate: navigate, aiActive, liveCount: activeCams.length };

  return (
    <div className="min-h-full lg:grid lg:grid-cols-[244px_1fr]">
      {/* Desktop sidebar */}
      <aside className="hidden lg:block sticky top-0 h-screen">
        <Sidebar {...sidebarProps} />
      </aside>

      {/* Mobile top bar + drawer */}
      <div className="lg:hidden sticky top-0 z-40 bg-[var(--c-surface)] border-b border-[var(--c-border)] pl-2 pr-2 h-14 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="เปิดเมนู"
          aria-haspopup="dialog"
          className="cursor-pointer shrink-0 w-11 h-11 rounded-full grid place-items-center text-[var(--c-ink)] hover:bg-[var(--c-raised)]"
        >
          <NavIcon name="menu" className="w-6 h-6" />
        </button>
        <div className="min-w-0 flex-1">
          <p className="font-display text-base font-bold leading-tight truncate">{PAGE_TITLES[page]}</p>
          <p className="text-xs text-[var(--c-muted)] leading-tight">BKK StreetSmart</p>
        </div>
        {activeCams.length > 0 && (
          <button type="button" onClick={() => navigate('cameras')} className="cursor-pointer shrink-0 min-h-11 px-2 text-xs text-[var(--c-muted)] hover:text-[var(--c-ink)]">
            ดูสด {activeCams.length} กล้อง
          </button>
        )}
        <ThemeToggle />
      </div>
      {menuOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label="เมนู">
          <div className="w-72 max-w-[85vw] h-full">
            <Sidebar {...sidebarProps} onClose={() => setMenuOpen(false)} />
          </div>
          <button type="button" aria-label="ปิดเมนู" onClick={() => setMenuOpen(false)} className="flex-1 bg-slate-900/50" />
        </div>
      )}
      <BottomNav page={page} onNavigate={navigate} onMenu={() => setMenuOpen(true)} onReport={openFloodReport} />

      {/* Earthquake scrolls inside its frame, so on desktop the page itself must fit the screen */}
      <div className={`min-h-full flex flex-col pt-4 pb-24 min-w-0 ${page === 'enviro' ? 'lg:pb-4' : ''}`}>
        <main className="flex-1 px-4 sm:px-6 min-w-0">
          {/* One width and one spacing rule for every page */}
          <motion.div
            key={page}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22 }}
            className="mx-auto w-full max-w-[1400px] flex flex-col gap-4"
          >
            <Suspense fallback={<PageLoading />}>
            {page === 'dashboard' && (
              <DashboardPage isActive liveCount={activeCams.length} cameras={cameras} incidents={incidents} onAsk={askAI} onOpenRoad={openRoadCameras} onNavigate={navigate} onOpenAI={openAI} onToast={showToast} />
            )}

            {page === 'cameras' && (
              <>
                <PageHeader title={PAGE_TITLES.cameras} description="กล้องทุกตัวทั่วประเทศ เลือกภาคแล้วเลือกจังหวัด แตะกล้องเพื่อดูภาพใหญ่" />
                {/* cameras opened from the map, a road row or "เปิดค้างไว้ด้านบน", large, above the wall */}
                {activeCams.length > 0 && (
                  <section aria-label="ภาพสดจากกล้องที่เลือก" className="flex flex-col gap-3">
                    <div className="flex items-center justify-between gap-2">
                      <h2 className="text-[15px] font-semibold text-slate-900">
                        กล้องที่เปิดค้างไว้ <span className="text-sm font-normal text-slate-500">{activeCams.length} กล้อง</span>
                      </h2>
                      <button type="button" onClick={clear} className="cursor-pointer rounded-lg px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 hover:text-red-700 transition-colors duration-200">
                        ปิดทุกกล้อง
                      </button>
                    </div>
                    <CityWindow cameras={activeCams} camStatus={camStatus} incidents={incidents} onClose={remove} onOpenAI={openAI} aiIds={aiIds} />
                  </section>
                )}
                <CameraWall
                  cameras={liveCameras}
                  loading={!allCameras && !allFailed}
                  camStatus={camStatus}
                  incidents={incidents}
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
                  aiIds={aiIds}
                />
              </>
            )}

            {page === 'map' && <MapPage isActive cameras={cameras} active={active} incidents={incidents} onToggle={toggle} onOpenAI={openAI} onToast={showToast} />}

            {page === 'water' && <WaterPage isActive onToast={showToast} onNavigate={navigate} onAsk={askAI} onOpenRoad={openRoadCameras} />}

            {page === 'report' && <FloodPinPage isActive />}

            {page === 'yolo' && (
              <CameraAiPage tab={cameraTab} onTab={setCameraTab} cameras={cameras} favorites={favorites} camid={aiCamid} incidents={incidents} onPickCamera={setAiCamid} onToast={showToast} onAsk={askAI} />
            )}

            {page === 'safety' && <SafetyPage isActive />}

            {page === 'visitors' && <VisitorsPage isActive />}

            {page === 'alerts' && <AlertsPage isActive onToast={showToast} />}

            {page === 'ai' && <AiPage active pendingQuestion={pendingQuestion} onQuestionConsumed={() => setPendingQuestion('')} />}

            {/* ENVIRO is its own app (launch\enviro), mounted at /enviro on the same address. Framed, it
                switches to this site's look itself (the `embed` class in ENVIRO/frontend/index.html). */}
            {page === 'enviro' && (
              <>
                <PageHeader
                  title={PAGE_TITLES.enviro}
                  description="แผ่นดินไหวล่าสุดทั่วโลกและใกล้ไทย อัปเดตสด จากกรมอุตุนิยมวิทยาและสถานีวัดแผ่นดินไหวต่างประเทศ"
                  actions={
                    <a
                      href="/enviro/"
                      target="_blank"
                      rel="noopener"
                      className="inline-flex items-center justify-center h-10 px-4 text-sm rounded-lg border font-medium bg-white text-slate-800 border-slate-300 hover:bg-slate-50 transition-colors duration-150"
                    >
                      เปิดเต็มจอ
                    </a>
                  }
                />
                <iframe
                  src="/enviro/"
                  title="ENVIRO Seismic Command"
                  className="w-full h-[calc(100dvh-17rem)] lg:h-[calc(100vh-7rem)] border-0 bg-transparent"
                />
              </>
            )}
            </Suspense>
          </motion.div>
        </main>

        {/* ปุ่มกลมไอคอน AI ลอยด้านล่างขวาทุกหน้า (ยกเว้นหน้าคุยกับ AI อยู่แล้ว) */}
        {page !== 'ai' && page !== 'enviro' && (
          <button
            type="button"
            onClick={() => askAI('')}
            className="fixed bottom-20 lg:bottom-8 right-5 lg:right-8 z-30 w-14 h-14 rounded-full bg-gradient-to-tr from-blue-600 to-indigo-600 text-white shadow-xl shadow-blue-500/35 hover:shadow-blue-500/55 hover:scale-108 active:scale-95 transition-all duration-200 flex items-center justify-center cursor-pointer group"
            title="ถาม AI"
            aria-label="ถาม AI"
          >
            <BotFace className="w-11 h-11 group-hover:scale-110 transition-transform duration-200" />
          </button>
        )}

        <AlertPopups onNavigate={navigate} />

        <AnimatePresence>
          {toast && (
            <motion.div
              role="status"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 16 }}
              className="fixed bottom-20 lg:bottom-6 left-1/2 -translate-x-1/2 z-[60] rounded-lg bg-slate-900 text-white px-4 py-2.5 text-sm max-w-[calc(100vw-2rem)]"
            >
              {toast}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

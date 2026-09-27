import { useEffect, useState } from 'react';
import { getBmaSnapshotUrl, getBmaStreamUrl, fetchBmaLiveAnalysis } from '../../lib/api.js';
import { Badge, Button, FOCUS } from '../dashboard/ui.jsx';
import { Modal } from '../dashboard/primitives.jsx';
import { levelOf } from './BmaOverview.jsx';

// One BMA camera: live YOLO stream (or a fresh snapshot) with its counts, polled while open.
// Used by the camera grid of the BMA count tab and by the camera search. Give it key={cam.camid}
// so each camera opens on the live stream.
export default function BmaCameraModal({ cam, onClose }) {
  const [live, setLive] = useState(true);
  const [tick, setTick] = useState(Date.now());
  const [liveStats, setLiveStats] = useState(null);

  useEffect(() => {
    if (!cam) return;
    let alive = true;
    const fetchStats = () => {
      fetchBmaLiveAnalysis(cam.camid)
        .then((st) => {
          if (alive && st && !st.error) setLiveStats(st);
        })
        .catch(() => {});
    };
    fetchStats();
    const id = setInterval(fetchStats, 2500);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [cam]);

  const cur = liveStats || cam;
  const lv = levelOf(cur?.level);

  return (
    <Modal
      open={!!cam}
      onClose={onClose}
      title={cam?.title}
      subtitle={
        cam ? `${cam.district || 'กทม.'}${cam.road ? ` · ${cam.road}` : ''}${cam.direction ? ` · ${cam.direction}` : ''} · ${cam.camera_code || cam.camid}` : ''
      }
      footer={
        cam && (
          <>
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <Badge tone={lv.tone}>{lv.label}</Badge>
                <p className="text-sm text-slate-800 tabular-nums">
                  รถยนต์ <b>{cur.cars || 0}</b> · มอเตอร์ไซค์ <b>{cur.motorcycles || 0}</b> · บรรทุก/บัส <b>{cur.trucks || 0}</b> · รวม <b>{cur.total || 0}</b> คัน
                </p>
                {liveStats?.live && (
                  <span className="text-xs text-emerald-600 font-medium flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" /> วิเคราะห์สด Real-time
                  </span>
                )}
              </div>
              <span className="text-xs text-slate-500">สะสมรอบนี้ {cam.acc_total || 0} คัน</span>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant={live ? 'secondary' : 'primary'} onClick={() => setLive((v) => !v)}>
                {live ? 'สลับเป็นภาพนิ่งสด' : 'ดูสตรีมสดต่อเนื่อง (YOLO)'}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setTick(Date.now())} title="ดึงภาพใหม่อีกครั้ง">
                รีเฟรชภาพ
              </Button>
              {cam.bma_url && (
                <a
                  href={cam.bma_url}
                  target="_blank"
                  rel="noreferrer"
                  className={`inline-flex items-center h-8 px-3 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-800 hover:bg-slate-50 ${FOCUS}`}
                >
                  เปิดที่เว็บ กทม.
                </a>
              )}
            </div>
          </>
        )
      }
    >
      {cam && (
        <div className="relative aspect-video bg-slate-900 rounded-lg overflow-hidden flex items-center justify-center">
          {/* Background cached image: renders in 0ms so user never sees a black screen */}
          <img src={getBmaSnapshotUrl(cam.camid, false)} alt="" className="absolute inset-0 w-full h-full object-contain opacity-70" />
          {/* Live stream or fresh snapshot */}
          <img
            key={`${cam.camid}-${live}-${tick}`}
            src={live ? getBmaStreamUrl(cam.camid, tick) : getBmaSnapshotUrl(cam.camid, true, tick)}
            alt={cam.title}
            className="relative z-10 w-full h-full object-contain"
            onError={() => {
              if (live) setLive(false);
            }}
          />
          <div className="absolute top-3 left-3 flex items-center gap-2 z-20">
            <span className="rounded-md bg-red-600/90 text-white text-xs font-semibold px-2 py-0.5 flex items-center gap-1.5 shadow backdrop-blur-xs">
              <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
              {live ? 'สตรีมสด Real-time (YOLO)' : 'ภาพสด Real-time'}
            </span>
          </div>
        </div>
      )}
    </Modal>
  );
}

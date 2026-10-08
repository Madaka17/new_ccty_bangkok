// One CCTV pin of the traffic map. Its popup plays the camera while open (HLS, else the snapshot) and has
// "open this camera" and "ask AI" buttons, which MapPage handles by delegation (data-act / data-camid).
import * as maplibregl from 'maplibre-gl';
import Hls from 'hls.js';
import { PIN, PIN_COLOR, esc, pinEl } from './markers.js';

// on: the camera is open in the viewer; floodcam: mark the cameras near a high water gauge
export function cameraMarker(map, c, on, floodcam) {
  const pinColor = PIN_COLOR[c.province] || PIN;
  const el = pinEl(pinColor, on, floodcam ? c.floodRisk : null);
  el.setAttribute('aria-label', c.short_title || c.title);

  const orgTag = c.organization ? `<span style="display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;background:#e0f2fe;color:#0369a1;margin-bottom:6px">${esc(c.organization)}</span>` : '';

  const floodHtml = c.floodRisk
    ? `<div style="background:${c.floodRisk.isOverflow ? '#fef2f2' : '#fffbeb'};border:1px solid ${c.floodRisk.isOverflow ? '#fecaca' : '#fde68a'};border-radius:6px;padding:6px 8px;margin-bottom:8px;font-size:11px;color:${c.floodRisk.isOverflow ? '#991b1b' : '#92400e'}">
        <div style="font-weight:700;display:flex;align-items:center;gap:4px">
          ${esc(c.floodRisk.badgeText)} · น้ำเต็ม ${c.floodRisk.storagePct}%
        </div>
        <div style="font-size:10px;margin-top:2px;color:${c.floodRisk.isOverflow ? '#b91c1c' : '#b45309'}">
          จุดวัดน้ำใกล้กล้อง: ${esc(c.floodRisk.stationName)} ห่าง ${c.floodRisk.distanceKm} กม.
        </div>
      </div>`
    : '';

  const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px', anchor: 'bottom' }).setHTML(
    `<div style="width:260px">
      <div style="position:relative;border-radius:8px;overflow:hidden;background:#e2e8f0;aspect-ratio:16/9;margin-bottom:8px">
        <video data-live="${c.camid}" muted autoplay playsinline style="display:none;width:100%;height:100%;object-fit:cover;background:#000"></video>
        <img data-img="${c.camid}" alt="" style="display:block;width:100%;height:100%;object-fit:cover" />
        <span data-status="${c.camid}" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:#475569;background:#f8fafc">กำลังเปิดภาพ...</span>
      </div>
      ${orgTag}
      ${floodHtml}
      <p style="margin:0 0 8px;font-weight:500;color:#0f172a;font-size:13px;line-height:1.35">${esc(c.short_title || c.title)}</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button data-act="toggle" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:${on ? '#fee2e2' : '#2563eb'};color:${on ? '#b91c1c' : '#fff'};font-size:12px;font-family:inherit">${on ? 'ปิดกล้องนี้' : 'เปิดดูกล้องนี้'}</button>
        <button data-act="ai" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:#f1f5f9;color:#0f172a;border:1px solid #cbd5e1;font-size:12px;font-family:inherit">${c.floodRisk ? 'ถาม AI เรื่องน้ำท่วม' : 'ถาม AI'}</button>
      </div>
    </div>`
  );

  let hls = null;
  popup.on('open', () => {
    map.easeTo({ center: [c.longitude, c.latitude], offset: [0, 130], duration: 400 });
    const root = popup.getElement();
    const video = root?.querySelector(`video[data-live="${c.camid}"]`);
    const img = root?.querySelector(`img[data-img="${c.camid}"]`);
    const status = root?.querySelector(`span[data-status="${c.camid}"]`);
    if (!img || !video) return;
    const hide = () => status && (status.style.display = 'none');
    const fail = () => status && (status.textContent = 'ยังดูภาพจากกล้องนี้ไม่ได้ ลองใหม่อีกครั้ง');

    // Snapshot fallback: iTIC Motion entries carry placeholder X.X.X.X urls, so only real hosts count
    const still = [c.imgurl, c.vdourl].find((u) => u && !u.includes('X.X.X.X'));
    const showImage = () => {
      if (!still) return fail();
      img.onload = hide;
      img.onerror = fail;
      img.src = `${still}${still.includes('?') ? '&' : '?'}t=${Date.now()}`;
    };

    // Prefer the HLS stream (works for every Longdo camera); same setup as VideoSlot
    if (c.hls_url && Hls.isSupported()) {
      video.style.display = 'block';
      img.style.display = 'none';
      hls = new Hls({ enableWorker: true, lowLatencyMode: true, backBufferLength: 30, maxBufferLength: 10, manifestLoadingTimeOut: 8000 });
      hls.loadSource(c.hls_url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
      video.onplaying = hide;
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (!data.fatal) return;
        hls.destroy();
        hls = null;
        video.style.display = 'none';
        img.style.display = 'block';
        showImage();
      });
    } else if (c.hls_url && video.canPlayType('application/vnd.apple.mpegurl')) {
      video.style.display = 'block';
      img.style.display = 'none';
      video.src = c.hls_url;
      video.onplaying = hide;
      video.onerror = showImage;
      video.play().catch(() => {});
    } else if (still) {
      showImage();
    } else if (status) {
      status.textContent = 'กล้องนี้ไม่มีภาพสด';
    }
  });

  popup.on('close', () => {
    if (hls) {
      hls.destroy();
      hls = null;
    }
    const root = popup.getElement();
    root?.querySelectorAll('video[data-live]').forEach((v) => {
      v.pause();
      v.removeAttribute('src');
      v.load();
    });
    root?.querySelectorAll('img[data-img]').forEach((img) => (img.src = ''));
  });

  return new maplibregl.Marker({ element: el }).setLngLat([c.longitude, c.latitude]).setPopup(popup).addTo(map);
}

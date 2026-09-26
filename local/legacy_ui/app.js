/**
 * Bangkok & Metropolitan Traffic CCTV Application
 * Developed for Longdo Traffic CCTV Cameras
 */

// State Management
const state = {
  cameras: [],           // All loaded cameras
  filteredCameras: [],   // Filtered for sidebar
  activeSlots: new Array(16).fill(null), // 16 slots, holds camera objects or null
  hlsPlayers: new Array(16).fill(null),  // HLS.js instances for each slot
  layoutSize: 4,         // 1, 4, 9, 16
  multiCam: true,        // multiple cameras allowed
  currentProvince: 'all',// 'all', 'กรุงเทพมหานคร', etc., or 'favorites'
  searchQuery: '',
  sortBy: 'name',
  favorites: new Set(),
  mapInstance: null,
  mapMarkers: []
};

// Province color mappings
const PROVINCE_CLASSES = {
  'กรุงเทพมหานคร': 'bkk',
  'นนทบุรี': 'nonthaburi',
  'นครปฐม': 'nakhonpathom',
  'สมุทรปราการ': 'samutprakan',
  'ปทุมธานี': 'pathumthani'
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  loadFavorites();
  initSlots();
  initEventListeners();
  loadCameraData();
});

/* ==========================================================
 * Data Loading
 * ========================================================== */
function loadFavorites() {
  try {
    const saved = localStorage.getItem('bkk_cctv_favs');
    if (saved) {
      const arr = JSON.parse(saved);
      state.favorites = new Set(arr);
    }
  } catch (e) {
    console.warn('Could not read favorites from localStorage', e);
  }
  updateFavBadgeCount();
}

function saveFavorites() {
  try {
    localStorage.setItem('bkk_cctv_favs', JSON.stringify(Array.from(state.favorites)));
  } catch (e) {
    console.warn('Could not save favorites to localStorage', e);
  }
  updateFavBadgeCount();
}

function updateFavBadgeCount() {
  const badge = document.getElementById('chip-fav-count');
  if (badge) {
    badge.textContent = state.favorites.size;
  }
}

async function loadCameraData() {
  // 1. First use embedded fallback data if available
  if (window.BKK_CAMERAS && window.BKK_CAMERAS.items) {
    state.cameras = [...window.BKK_CAMERAS.items];
    document.getElementById('total-cam-count').textContent = state.cameras.length;
    applyFilterAndSort();
    checkUrlOrStorageInit();
  }

  // 2. Fetch live data from Longdo API if online
  try {
    const res = await fetch('https://traffic.longdo.com/camera.json');
    if (res.ok) {
      const data = await res.json();
      const items = data.item || [];
      const bkkProvs = ['กรุงเทพมหานคร', 'นนทบุรี', 'ปทุมธานี', 'สมุทรปราการ', 'สมุทรสาคร', 'นครปฐม'];
      const validGeos = ['10', '11', '12', '13', '73', '74'];
      
      const filtered = [];
      for (const it of items) {
        const title = (it.title || '').trim();
        const geo = String(it.geocode || '').trim();
        const m = title.match(/^\(([^)]+)\)/);
        const provInTag = m ? m[1].replace('จ.', '').trim() : '';

        let matchedProv = null;
        if (bkkProvs.includes(provInTag)) {
          matchedProv = provInTag;
        } else {
          for (const [pCode, pName] of [['10','กรุงเทพมหานคร'], ['11','สมุทรปราการ'], ['12','นนทบุรี'], ['13','ปทุมธานี'], ['73','นครปฐม'], ['74','สมุทรสาคร']]) {
            if (geo.startsWith(pCode) && (title.includes(pName) || !provInTag)) {
              matchedProv = pName;
              break;
            }
          }
        }

        if (matchedProv) {
          filtered.push({
            camid: it.camid || '',
            title: title,
            short_title: title.replace(/^\([^)]+\)\s*/, ''),
            province: matchedProv,
            organization: it.organization || 'Longdo Traffic',
            hls_url: it.hls_url || '',
            vdourl: it.vdourl || '',
            imgurl: it.imgurl || '',
            latitude: parseFloat(it.latitude) || 0,
            longitude: parseFloat(it.longitude) || 0,
            geocode: geo,
            lastupdate: it.lastupdate || ''
          });
        }
      }

      if (filtered.length > 0) {
        state.cameras = filtered;
        document.getElementById('total-cam-count').textContent = state.cameras.length;
        applyFilterAndSort();
        // refresh active cameras references
        for (let i = 0; i < state.activeSlots.length; i++) {
          if (state.activeSlots[i]) {
            const fresh = state.cameras.find(c => c.camid === state.activeSlots[i].camid);
            if (fresh) state.activeSlots[i] = fresh;
          }
        }
      }
    }
  } catch (err) {
    console.info('Live Longdo fetch bypassed (using bundled camera list):', err);
  }
}

function checkUrlOrStorageInit() {
  const urlParams = new URLSearchParams(window.location.search);
  const openParam = urlParams.get('open');

  if (openParam) {
    const camIds = openParam.split(',').filter(Boolean);
    let opened = 0;
    camIds.forEach(id => {
      const cam = state.cameras.find(c => c.camid === id);
      if (cam && opened < 16) {
        state.activeSlots[opened] = cam;
        opened++;
      }
    });
    if (opened > 0) {
      if (opened > 9) setLayoutSize(16);
      else if (opened > 4) setLayoutSize(9);
      else if (opened > 1) setLayoutSize(4);
      else setLayoutSize(1);

      renderAllActiveSlots();
      renderCameraList();
      return;
    }
  }

  // Load from local storage
  try {
    const savedActive = localStorage.getItem('bkk_cctv_active_slots');
    if (savedActive) {
      const ids = JSON.parse(savedActive);
      let opened = 0;
      ids.forEach((id, idx) => {
        if (id && idx < 16) {
          const cam = state.cameras.find(c => c.camid === id);
          if (cam) {
            state.activeSlots[idx] = cam;
            opened++;
          }
        }
      });
      if (opened > 0) {
        const savedLayout = parseInt(localStorage.getItem('bkk_cctv_layout') || '4');
        setLayoutSize(savedLayout || (opened > 4 ? 9 : 4));
        renderAllActiveSlots();
        renderCameraList();
        return;
      }
    }
  } catch (e) {
    console.warn(e);
  }

  // Default: Open 4 prominent Bangkok & Metropolitan cameras
  const defaultCams = [
    state.cameras.find(c => c.camid === 'ITICM_BMAMI0074') || state.cameras[0], // พระราม 4
    state.cameras.find(c => c.camid === 'DOH-PER-3-008') || state.cameras[1],   // วิภาวดี ดอนเมือง
    state.cameras.find(c => c.camid === 'ITICM_BMAMI0046') || state.cameras[2], // ห้าแยกปากเกร็ด
    state.cameras.find(c => c.camid === 'ITICM_BMAMI0164') || state.cameras[3]  // รัชดาภิเษก
  ].filter(Boolean);

  defaultCams.forEach((cam, idx) => {
    state.activeSlots[idx] = cam;
  });
  setLayoutSize(4);
  renderAllActiveSlots();
  renderCameraList();
}

function saveActiveSlotsToStorage() {
  try {
    const ids = state.activeSlots.map(c => c ? c.camid : null);
    localStorage.setItem('bkk_cctv_active_slots', JSON.stringify(ids));
    localStorage.setItem('bkk_cctv_layout', state.layoutSize.toString());
  } catch (e) {
    console.warn(e);
  }
}

/* ==========================================================
 * Grid & Slot Management
 * ========================================================== */
function initSlots() {
  const grid = document.getElementById('video-grid');
  grid.innerHTML = '';

  for (let i = 0; i < 16; i++) {
    const slotEl = document.createElement('div');
    slotEl.className = 'video-slot';
    slotEl.id = `video-slot-${i}`;
    slotEl.dataset.slotIndex = i;

    // Drag & drop support
    slotEl.addEventListener('dragover', handleDragOver);
    slotEl.addEventListener('dragleave', handleDragLeave);
    slotEl.addEventListener('drop', handleDrop);

    slotEl.innerHTML = getEmptySlotHTML(i);
    grid.appendChild(slotEl);
  }
  updateActiveCountUI();
}

function getEmptySlotHTML(index) {
  return `
    <div class="slot-empty" onclick="handleEmptySlotClick(${index})">
      <div class="slot-empty-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"></line>
          <line x1="5" y1="12" x2="19" y2="12"></line>
        </svg>
      </div>
      <p>ช่องแสดงที่ ${index + 1}<br><span style="font-size:0.7rem;opacity:0.7;">คลิกหรือลากกล้องมาใส่</span></p>
    </div>
  `;
}

function setLayoutSize(size) {
  state.layoutSize = Number(size);
  const grid = document.getElementById('video-grid');
  grid.className = `video-grid-container layout-${size}`;

  // Update layout button styles
  document.querySelectorAll('#layout-buttons .layout-btn').forEach(btn => {
    btn.classList.toggle('active', parseInt(btn.dataset.size) === state.layoutSize);
  });

  document.getElementById('layout-max-count').textContent = state.layoutSize;

  // Show/hide slots based on layout size
  for (let i = 0; i < 16; i++) {
    const slotEl = document.getElementById(`video-slot-${i}`);
    if (slotEl) {
      if (i < state.layoutSize) {
        slotEl.style.display = 'flex';
      } else {
        slotEl.style.display = 'none';
        // If there was an active player in hidden slot, pause it
        if (state.hlsPlayers[i]) {
          state.hlsPlayers[i].destroy();
          state.hlsPlayers[i] = null;
        }
      }
    }
  }

  saveActiveSlotsToStorage();
}

function openCamera(camera, targetSlotIndex = -1) {
  if (!camera) return;

  // If already open, do nothing or highlight
  const existingIndex = state.activeSlots.findIndex(c => c && c.camid === camera.camid);
  if (existingIndex !== -1) {
    showToast(`กล้อง "${camera.short_title}" กำลังแสดงอยู่ที่ช่อง ${existingIndex + 1} แล้ว`);
    return;
  }

  // Single Camera Mode
  if (!state.multiCam) {
    clearAllSlots();
    targetSlotIndex = 0;
    setLayoutSize(1);
  } else {
    // Determine slot
    if (targetSlotIndex === -1 || targetSlotIndex >= state.layoutSize) {
      // Find first empty visible slot
      targetSlotIndex = state.activeSlots.findIndex((c, idx) => c === null && idx < state.layoutSize);
      if (targetSlotIndex === -1) {
        // Need to expand layout if possible
        if (state.layoutSize === 1) {
          setLayoutSize(4);
          targetSlotIndex = 1;
        } else if (state.layoutSize === 4) {
          setLayoutSize(9);
          targetSlotIndex = 4;
        } else if (state.layoutSize === 9) {
          setLayoutSize(16);
          targetSlotIndex = 9;
        } else {
          // Grid is full (16 cameras)
          showToast('แสดงกล้องเต็มทั้ง 16 ช่องแล้ว กรุณาปิดช่องที่ไม่ต้องการก่อน');
          return;
        }
      }
    }
  }

  // Assign to slot
  state.activeSlots[targetSlotIndex] = camera;
  renderSlotVideo(targetSlotIndex, camera);
  updateActiveCountUI();
  renderCameraList();
  saveActiveSlotsToStorage();
  updateMapMarkerStates();
}

function closeSlot(slotIndex) {
  const cam = state.activeSlots[slotIndex];
  if (!cam) return;

  // Cleanup HLS instance
  if (state.hlsPlayers[slotIndex]) {
    try {
      state.hlsPlayers[slotIndex].destroy();
    } catch (e) {}
    state.hlsPlayers[slotIndex] = null;
  }

  state.activeSlots[slotIndex] = null;
  const slotEl = document.getElementById(`video-slot-${slotIndex}`);
  if (slotEl) {
    slotEl.innerHTML = getEmptySlotHTML(slotIndex);
  }

  updateActiveCountUI();
  renderCameraList();
  saveActiveSlotsToStorage();
  updateMapMarkerStates();
}

function clearAllSlots() {
  for (let i = 0; i < 16; i++) {
    if (state.hlsPlayers[i]) {
      try {
        state.hlsPlayers[i].destroy();
      } catch (e) {}
      state.hlsPlayers[i] = null;
    }
    state.activeSlots[i] = null;
    const slotEl = document.getElementById(`video-slot-${i}`);
    if (slotEl) {
      slotEl.innerHTML = getEmptySlotHTML(i);
    }
  }
  updateActiveCountUI();
  renderCameraList();
  saveActiveSlotsToStorage();
  updateMapMarkerStates();
  showToast('ปิดกล้องทั้งหมดเรียบร้อย');
}

function renderAllActiveSlots() {
  for (let i = 0; i < state.layoutSize; i++) {
    const cam = state.activeSlots[i];
    if (cam) {
      renderSlotVideo(i, cam);
    } else {
      const slotEl = document.getElementById(`video-slot-${i}`);
      if (slotEl) slotEl.innerHTML = getEmptySlotHTML(i);
    }
  }
  updateActiveCountUI();
}

function renderSlotVideo(slotIndex, camera) {
  const slotEl = document.getElementById(`video-slot-${slotIndex}`);
  if (!slotEl) return;

  // Cleanup existing player if any
  if (state.hlsPlayers[slotIndex]) {
    try {
      state.hlsPlayers[slotIndex].destroy();
    } catch (e) {}
    state.hlsPlayers[slotIndex] = null;
  }

  const provClass = PROVINCE_CLASSES[camera.province] || 'bkk';

  slotEl.innerHTML = `
    <!-- Top Floating Header -->
    <div class="video-slot-header" draggable="true" data-slot="${slotIndex}">
      <div class="video-slot-title-area" title="${camera.title}">
        <span class="live-badge-mini">LIVE</span>
        <span class="prov-tag ${provClass}" style="font-size:0.65rem;">${camera.province}</span>
        <span class="video-slot-title">${camera.short_title}</span>
      </div>
      <div class="video-slot-actions">
        <button class="slot-action-btn" title="เปิด AI YOLO11x ตรวจจับรถบนกล้องนี้" onclick="openAIStudioForCamera('${camera.camid}')" style="color:#a371f7;">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="11" width="18" height="10" rx="2"></rect>
            <circle cx="12" cy="5" r="2"></circle>
            <path d="M12 7v4"></path>
            <line x1="8" y1="16" x2="8" y2="16"></line>
            <line x1="16" y1="16" x2="16" y2="16"></line>
          </svg>
        </button>
        <button class="slot-action-btn" title="จับภาพนิ่ง (Snapshot)" onclick="captureSnapshot(${slotIndex})">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
            <circle cx="12" cy="13" r="4"></circle>
          </svg>
        </button>
        <button class="slot-action-btn" title="รีโหลดสัญญาณ" onclick="reloadSlotStream(${slotIndex})">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M23 4v6h-6"></path>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
          </svg>
        </button>
        <button class="slot-action-btn" title="ขยายเต็มจอ" onclick="fullscreenSlot(${slotIndex})">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
          </svg>
        </button>
        <button class="slot-action-btn btn-close" title="ปิดกล้องนี้" onclick="closeSlot(${slotIndex})">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
    </div>

    <!-- Video Player Container -->
    <div class="slot-player-container" id="player-wrap-${slotIndex}">
      <div class="video-loading-overlay" id="loading-overlay-${slotIndex}">
        <div class="spinner"></div>
        <span>กำลังเชื่อมต่อกล้องสด...</span>
      </div>
      <video 
        id="video-player-${slotIndex}" 
        autoplay 
        muted 
        playsinline
        crossorigin="anonymous">
      </video>
    </div>
  `;

  // Drag handler on header
  const headerEl = slotEl.querySelector('.video-slot-header');
  headerEl.addEventListener('dragstart', (e) => {
    e.dataTransfer.setData('text/plain', JSON.stringify({ type: 'slot_swap', fromSlot: slotIndex }));
  });

  // Attach Stream
  attachStreamToPlayer(slotIndex, camera);
}

function attachStreamToPlayer(slotIndex, camera) {
  const video = document.getElementById(`video-player-${slotIndex}`);
  const overlay = document.getElementById(`loading-overlay-${slotIndex}`);
  if (!video) return;

  const hlsUrl = camera.hls_url;

  if (hlsUrl && Hls.isSupported()) {
    const hls = new Hls({
      enableWorker: true,
      lowLatencyMode: true,
      backBufferLength: 30,
      maxBufferLength: 10,
      manifestLoadingTimeOut: 8000
    });

    state.hlsPlayers[slotIndex] = hls;
    hls.loadSource(hlsUrl);
    hls.attachMedia(video);

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      video.play().catch(e => console.log('Autoplay deferred:', e));
      if (overlay) overlay.style.display = 'none';
    });

    hls.on(Hls.Events.ERROR, (event, data) => {
      if (data.fatal) {
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            console.warn(`HLS Network error on slot ${slotIndex}, trying to recover...`);
            hls.startLoad();
            break;
          case Hls.ErrorTypes.MEDIA_ERROR:
            console.warn(`HLS Media error on slot ${slotIndex}, recovering...`);
            hls.recoverMediaError();
            break;
          default:
            hls.destroy();
            state.hlsPlayers[slotIndex] = null;
            showSlotError(slotIndex, camera);
            break;
        }
      }
    });

  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    // Native Safari/iOS HLS
    video.src = hlsUrl;
    video.addEventListener('loadedmetadata', () => {
      video.play();
      if (overlay) overlay.style.display = 'none';
    });
    video.addEventListener('error', () => {
      showSlotError(slotIndex, camera);
    });
  } else {
    // Fallback: image/mjpeg stream
    showSlotImageFallback(slotIndex, camera);
  }
}

function showSlotError(slotIndex, camera) {
  const wrap = document.getElementById(`player-wrap-${slotIndex}`);
  if (!wrap) return;

  wrap.innerHTML = `
    <div class="video-error-overlay">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#f85149" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
      <span style="font-weight: 500;">ไม่สามารถโหลดสัญญาณสดได้</span>
      <span style="font-size:0.72rem; opacity:0.8;">อาจเป็นช่วงที่กล้องปิดปรับปรุงสัญญาณ</span>
      <div style="display:flex; gap:8px; margin-top:4px;">
        <button class="btn btn-icon-only" style="padding:4px 10px; font-size:0.75rem;" onclick="reloadSlotStream(${slotIndex})">
          ลองใหม่
        </button>
        <button class="btn btn-icon-only" style="padding:4px 10px; font-size:0.75rem;" onclick="showSlotImageFallback(${slotIndex}, state.activeSlots[${slotIndex}])">
          ดูภาพนิ่ง
        </button>
      </div>
    </div>
  `;
}

function showSlotImageFallback(slotIndex, camera) {
  const wrap = document.getElementById(`player-wrap-${slotIndex}`);
  if (!wrap || !camera) return;

  const imgSrc = camera.imgurl || camera.vdourl;
  wrap.innerHTML = `
    <img src="${imgSrc}?t=${Date.now()}" alt="${camera.title}" onerror="this.onerror=null; this.src='https://traffic.longdo.com/sites/all/themes/traffic_theme/images/no_image.png';">
  `;
}

function reloadSlotStream(slotIndex) {
  const cam = state.activeSlots[slotIndex];
  if (cam) {
    renderSlotVideo(slotIndex, cam);
  }
}

function fullscreenSlot(slotIndex) {
  const slotEl = document.getElementById(`video-slot-${slotIndex}`);
  if (slotEl) {
    if (!document.fullscreenElement) {
      slotEl.requestFullscreen().catch(err => {
        alert(`Error enabling fullscreen: ${err.message}`);
      });
    } else {
      document.exitFullscreen();
    }
  }
}

function captureSnapshot(slotIndex) {
  const video = document.getElementById(`video-player-${slotIndex}`);
  const cam = state.activeSlots[slotIndex];
  if (!video || !cam) return;

  try {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 360;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.download = `cctv_${cam.camid}_${Date.now()}.png`;
    link.href = dataUrl;
    link.click();
    showToast(`บันทึกภาพนิ่งจาก ${cam.short_title} เรียบร้อย`);
  } catch (err) {
    console.warn('Canvas capture error (CORS restricted):', err);
    // Fallback: open image url
    if (cam.imgurl) {
      window.open(cam.imgurl, '_blank');
    } else {
      showToast('ไม่สามารถบันทึกภาพได้เนื่องจากข้อจำกัดสิทธิ์ของเบราว์เซอร์');
    }
  }
}

function updateActiveCountUI() {
  const activeCount = state.activeSlots.filter(Boolean).length;
  const countEl = document.getElementById('active-cam-count');
  if (countEl) countEl.textContent = activeCount;
}

/* ==========================================================
 * Drag and Drop Support
 * ========================================================== */
function handleDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add('dragover');
}

function handleDragLeave(e) {
  e.currentTarget.classList.remove('dragover');
}

function handleDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove('dragover');
  const targetSlotIndex = parseInt(e.currentTarget.dataset.slotIndex);

  try {
    const rawData = e.dataTransfer.getData('text/plain');
    if (!rawData) return;
    const data = JSON.parse(rawData);

    if (data.type === 'camera_item') {
      const cam = state.cameras.find(c => c.camid === data.camid);
      if (cam) openCamera(cam, targetSlotIndex);
    } else if (data.type === 'slot_swap') {
      const fromSlot = data.fromSlot;
      if (fromSlot === targetSlotIndex) return;

      const temp = state.activeSlots[fromSlot];
      state.activeSlots[fromSlot] = state.activeSlots[targetSlotIndex];
      state.activeSlots[targetSlotIndex] = temp;

      renderAllActiveSlots();
      renderCameraList();
      saveActiveSlotsToStorage();
    }
  } catch (err) {
    console.error('Drop error:', err);
  }
}

function handleEmptySlotClick(slotIndex) {
  // If user clicks an empty slot, show suggestion toast or open first un-opened camera
  const unopened = state.filteredCameras.find(c => !state.activeSlots.some(s => s && s.camid === c.camid));
  if (unopened) {
    openCamera(unopened, slotIndex);
    showToast(`เปิด "${unopened.short_title}" ในช่อง ${slotIndex + 1}`);
  } else {
    showToast('กรุณาเลือกกล้องจากรายการทางซ้ายมือ');
  }
}

/* ==========================================================
 * Sidebar & Filtering
 * ========================================================== */
function applyFilterAndSort() {
  let list = [...state.cameras];

  // 1. Filter by Province
  if (state.currentProvince === 'favorites') {
    list = list.filter(c => state.favorites.has(c.camid));
  } else if (state.currentProvince !== 'all') {
    list = list.filter(c => c.province === state.currentProvince);
  }

  // 2. Filter by Search Query
  if (state.searchQuery.trim()) {
    const q = state.searchQuery.trim().toLowerCase();
    list = list.filter(c => 
      c.title.toLowerCase().includes(q) ||
      c.camid.toLowerCase().includes(q) ||
      c.province.toLowerCase().includes(q) ||
      c.organization.toLowerCase().includes(q)
    );
  }

  // 3. Sort
  list.sort((a, b) => {
    if (state.sortBy === 'name') {
      return a.short_title.localeCompare(b.short_title, 'th');
    } else if (state.sortBy === 'province') {
      return a.province.localeCompare(b.province, 'th') || a.short_title.localeCompare(b.short_title, 'th');
    } else if (state.sortBy === 'camid') {
      return a.camid.localeCompare(b.camid);
    }
    return 0;
  });

  state.filteredCameras = list;
  renderCameraList();
}

function renderCameraList() {
  const container = document.getElementById('camera-list');
  if (!container) return;

  if (state.filteredCameras.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="8" y1="12" x2="16" y2="12"></line>
        </svg>
        <p>ไม่พบกล้องที่ตรงตามเงื่อนไข</p>
      </div>
    `;
    return;
  }

  const activeCamIds = new Set(state.activeSlots.filter(Boolean).map(c => c.camid));

  container.innerHTML = state.filteredCameras.map((cam, idx) => {
    const isActive = activeCamIds.has(cam.camid);
    const isStarred = state.favorites.has(cam.camid);
    const provClass = PROVINCE_CLASSES[cam.province] || 'bkk';

    return `
      <div 
        class="camera-card ${isActive ? 'active' : ''}" 
        id="camera-item-${cam.camid}"
        draggable="true"
        data-camid="${cam.camid}"
        onclick="handleCameraCardClick('${cam.camid}', event)"
      >
        <div class="camera-checkbox-wrapper" onclick="event.stopPropagation()">
          <input 
            type="checkbox" 
            class="custom-checkbox" 
            ${isActive ? 'checked' : ''}
            onchange="toggleCameraActive('${cam.camid}', this.checked)"
          >
        </div>

        <button 
          class="camera-star-btn ${isStarred ? 'starred' : ''}" 
          title="${isStarred ? 'ยกเลิกรายการโปรด' : 'เพิ่มในรายการโปรด'}"
          onclick="toggleFavorite('${cam.camid}', event)"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="${isStarred ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
          </svg>
        </button>

        <div class="camera-info">
          <div class="camera-title" title="${cam.title}">${cam.short_title}</div>
          <div class="camera-meta">
            <span class="prov-tag ${provClass}">${cam.province}</span>
            <span class="org-tag">${cam.organization}</span>
          </div>
        </div>

        <button 
          class="camera-info-btn" 
          title="ดูข้อมูลกล้องเพิ่มเติม"
          onclick="showCameraDetails('${cam.camid}', event)"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="16" x2="12" y2="12"></line>
            <line x1="12" y1="8" x2="12.01" y2="8"></line>
          </svg>
        </button>
      </div>
    `;
  }).join('');

  // Add dragstart events to cards
  container.querySelectorAll('.camera-card').forEach(card => {
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', JSON.stringify({
        type: 'camera_item',
        camid: card.dataset.camid
      }));
    });
  });
}

function handleCameraCardClick(camid, e) {
  const cam = state.cameras.find(c => c.camid === camid);
  if (!cam) return;

  const activeIndex = state.activeSlots.findIndex(c => c && c.camid === camid);
  if (activeIndex !== -1) {
    closeSlot(activeIndex);
  } else {
    openCamera(cam);
  }
}

function toggleCameraActive(camid, checked) {
  const cam = state.cameras.find(c => c.camid === camid);
  if (!cam) return;

  if (checked) {
    openCamera(cam);
  } else {
    const activeIndex = state.activeSlots.findIndex(c => c && c.camid === camid);
    if (activeIndex !== -1) closeSlot(activeIndex);
  }
}

function toggleFavorite(camid, e) {
  if (e) e.stopPropagation();

  if (state.favorites.has(camid)) {
    state.favorites.delete(camid);
    showToast('นำออกจากรายการโปรด');
  } else {
    state.favorites.add(camid);
    showToast('เพิ่มลงในรายการโปรดแล้ว ⭐');
  }

  saveFavorites();
  applyFilterAndSort();
}

/* ==========================================================
 * Interactive Map (Leaflet)
 * ========================================================== */
function initMap() {
  if (state.mapInstance) return;

  // Center on Bangkok (Victory Monument / Siam area)
  state.mapInstance = L.map('leaflet-map').setView([13.7563, 100.5018], 11);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(state.mapInstance);

  // Plot cameras
  state.mapMarkers = [];
  state.cameras.forEach(cam => {
    if (!cam.latitude || !cam.longitude) return;

    const isActive = state.activeSlots.some(s => s && s.camid === cam.camid);
    const marker = createMapMarker(cam, isActive);
    marker.addTo(state.mapInstance);
    state.mapMarkers.push({ camid: cam.camid, marker: marker, cam: cam });
  });
}

function createMapMarker(cam, isActive) {
  const color = isActive ? '#2ea043' : '#388bfd';
  const customIcon = L.divIcon({
    className: 'custom-leaflet-pin',
    html: `
      <div style="
        background-color: ${color}; 
        width: 24px; 
        height: 24px; 
        border-radius: 50%; 
        border: 2px solid white; 
        box-shadow: 0 2px 6px rgba(0,0,0,0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
      ">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
        </svg>
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12]
  });

  const marker = L.marker([cam.latitude, cam.longitude], { icon: customIcon });

  const popupHtml = `
    <div class="map-popup-card">
      <div class="map-popup-title">${cam.short_title}</div>
      <div class="map-popup-meta">
        <strong>${cam.province}</strong> • ${cam.organization}<br>
        <span style="font-size:0.7rem; color:#8b949e;">รหัส: ${cam.camid}</span>
      </div>
      <button class="map-popup-btn" onclick="openCameraFromMap('${cam.camid}')">
        เปิดดูกล้องนี้
      </button>
    </div>
  `;

  marker.bindPopup(popupHtml);
  return marker;
}

window.openCameraFromMap = function(camid) {
  const cam = state.cameras.find(c => c.camid === camid);
  if (cam) {
    openCamera(cam);
    showToast(`เปิดกล้อง "${cam.short_title}" เรียบร้อย`);
  }
};

function updateMapMarkerStates() {
  if (!state.mapInstance) return;

  const activeCamIds = new Set(state.activeSlots.filter(Boolean).map(c => c.camid));
  state.mapMarkers.forEach(item => {
    const isActive = activeCamIds.has(item.camid);
    const color = isActive ? '#2ea043' : '#388bfd';
    const newIcon = L.divIcon({
      className: 'custom-leaflet-pin',
      html: `
        <div style="
          background-color: ${color}; 
          width: 24px; 
          height: 24px; 
          border-radius: 50%; 
          border: 2px solid white; 
          box-shadow: 0 2px 6px rgba(0,0,0,0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
        ">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
          </svg>
        </div>
      `,
      iconSize: [24, 24],
      iconAnchor: [12, 12]
    });
    item.marker.setIcon(newIcon);
  });
}

function openMapModal() {
  const modal = document.getElementById('map-modal');
  modal.classList.add('open');
  setTimeout(() => {
    initMap();
    state.mapInstance.invalidateSize();
  }, 200);
}

function closeMapModal() {
  document.getElementById('map-modal').classList.remove('open');
}

/* ==========================================================
 * Camera Details Modal
 * ========================================================== */
function showCameraDetails(camid, e) {
  if (e) e.stopPropagation();

  const cam = state.cameras.find(c => c.camid === camid);
  if (!cam) return;

  const modal = document.getElementById('info-modal');
  document.getElementById('info-modal-title').textContent = cam.short_title;

  const body = document.getElementById('info-modal-body');
  body.innerHTML = `
    <table class="details-table">
      <tr>
        <td>รหัสกล้อง</td>
        <td><code>${cam.camid}</code></td>
      </tr>
      <tr>
        <td>ชื่อตำแหน่งเต็ม</td>
        <td>${cam.title}</td>
      </tr>
      <tr>
        <td>จังหวัด</td>
        <td><span class="prov-tag ${PROVINCE_CLASSES[cam.province] || 'bkk'}">${cam.province}</span></td>
      </tr>
      <tr>
        <td>หน่วยงาน</td>
        <td>${cam.organization}</td>
      </tr>
      <tr>
        <td>พิกัด GPS</td>
        <td>
          <a href="https://maps.google.com/?q=${cam.latitude},${cam.longitude}" target="_blank" style="color:var(--accent-blue); text-decoration:none;">
            ${cam.latitude.toFixed(6)}, ${cam.longitude.toFixed(6)} (เปิด Google Maps ↗)
          </a>
        </td>
      </tr>
      <tr>
        <td>รหัสพื้นที่ (Geocode)</td>
        <td>${cam.geocode || '-'}</td>
      </tr>
      <tr>
        <td>ลิงก์สตรีม HLS</td>
        <td>
          <input type="text" readonly value="${cam.hls_url}" style="width:100%; background:var(--bg-primary); color:var(--text-secondary); border:1px solid var(--border-color); padding:4px; font-size:0.75rem; border-radius:4px;">
        </td>
      </tr>
    </table>
    <div style="margin-top: 16px; display:flex; justify-content:flex-end; gap:8px;">
      <button class="btn btn-primary" onclick="openCamera(state.cameras.find(c => c.camid === '${cam.camid}')); document.getElementById('info-modal').classList.remove('open');">
        เปิดดูกล้องนี้ทันที
      </button>
    </div>
  `;

  modal.classList.add('open');
}

/* ==========================================================
 * Share & Notifications
 * ========================================================== */
function shareCurrentCameras() {
  const activeIds = state.activeSlots.filter(Boolean).map(c => c.camid);
  if (activeIds.length === 0) {
    showToast('ยังไม่มีกล้องที่เปิดอยู่ กรุณาเลือกกล้องก่อนแชร์');
    return;
  }

  const url = new URL(window.location.href);
  url.searchParams.set('open', activeIds.join(','));

  navigator.clipboard.writeText(url.toString()).then(() => {
    showToast('คัดลอกลิงก์แชร์การดูกล้องชุดนี้แล้ว! 📋');
  }).catch(() => {
    prompt('คัดลอกลิงก์แชร์นี้:', url.toString());
  });
}

function showToast(message) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2ea043" stroke-width="2.5">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
      <polyline points="22 4 12 14.01 9 11.01"></polyline>
    </svg>
    <span>${message}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3000);
}

/* ==========================================================
 * Event Listeners Setup
 * ========================================================== */
function initEventListeners() {
  // Search
  const searchInput = document.getElementById('search-input');
  const clearBtn = document.getElementById('search-clear-btn');
  searchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value;
    clearBtn.style.display = state.searchQuery ? 'block' : 'none';
    applyFilterAndSort();
  });

  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    state.searchQuery = '';
    clearBtn.style.display = 'none';
    applyFilterAndSort();
  });

  // Province chips
  document.querySelectorAll('#province-chips .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#province-chips .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.currentProvince = chip.dataset.province;
      applyFilterAndSort();
    });
  });

  // Sort
  document.getElementById('sort-select').addEventListener('change', (e) => {
    state.sortBy = e.target.value;
    applyFilterAndSort();
  });

  // Layout buttons
  document.querySelectorAll('#layout-buttons .layout-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      setLayoutSize(btn.dataset.size);
    });
  });

  // Multi camera toggle
  document.getElementById('toggle-multi-cam').addEventListener('change', (e) => {
    state.multiCam = e.target.checked;
    if (!state.multiCam) {
      // Keep only first active camera, close others
      const firstActive = state.activeSlots.find(Boolean);
      clearAllSlots();
      if (firstActive) {
        openCamera(firstActive, 0);
      }
      setLayoutSize(1);
    }
  });

  // Header Actions
  document.getElementById('btn-open-map').addEventListener('click', openMapModal);
  document.getElementById('btn-close-map-modal').addEventListener('click', closeMapModal);
  document.getElementById('map-modal').addEventListener('click', (e) => {
    if (e.target.id === 'map-modal') closeMapModal();
  });

  document.getElementById('btn-close-info-modal').addEventListener('click', () => {
    document.getElementById('info-modal').classList.remove('open');
  });
  document.getElementById('info-modal').addEventListener('click', (e) => {
    if (e.target.id === 'info-modal') document.getElementById('info-modal').classList.remove('open');
  });

  document.getElementById('btn-share-link').addEventListener('click', shareCurrentCameras);
  document.getElementById('btn-clear-all').addEventListener('click', clearAllSlots);

  // Fullscreen Grid
  document.getElementById('btn-fullscreen-grid').addEventListener('click', () => {
    const grid = document.getElementById('video-grid');
    if (!document.fullscreenElement) {
      grid.requestFullscreen().catch(err => alert(err.message));
    } else {
      document.exitFullscreen();
    }
  });

  // Quick Random 4 Cameras
  document.getElementById('btn-quick-random').addEventListener('click', () => {
    clearAllSlots();
    const shuffled = [...state.cameras].sort(() => 0.5 - Math.random());
    const picked = shuffled.slice(0, 4);
    picked.forEach((c, idx) => {
      state.activeSlots[idx] = c;
    });
    setLayoutSize(4);
    renderAllActiveSlots();
    renderCameraList();
    saveActiveSlotsToStorage();
    showToast('สุ่มเปิดกล้องจราจร 4 ตัวแล้ว');
  });

  // AI Studio Events
  const btnAiStudio = document.getElementById('btn-open-ai-studio');
  if (btnAiStudio) {
    btnAiStudio.addEventListener('click', () => openAIStudio());
  }

  const btnCloseAi = document.getElementById('btn-close-ai-modal');
  if (btnCloseAi) {
    btnCloseAi.addEventListener('click', closeAIStudio);
  }

  const aiModal = document.getElementById('ai-modal');
  if (aiModal) {
    aiModal.addEventListener('click', (e) => {
      if (e.target.id === 'ai-modal') closeAIStudio();
    });
  }

  const aiCamSelect = document.getElementById('ai-camera-select');
  if (aiCamSelect) {
    aiCamSelect.addEventListener('change', (e) => {
      switchAICamera(e.target.value);
    });
  }

  // FPS buttons
  document.querySelectorAll('#ai-fps-group .fps-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#ai-fps-group .fps-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const fps = parseFloat(btn.dataset.fps);
      setAITargetFps(fps);
    });
  });

  // Confidence slider
  const confSlider = document.getElementById('ai-conf-slider');
  if (confSlider) {
    confSlider.addEventListener('input', (e) => {
      const conf = parseInt(e.target.value);
      document.getElementById('ai-conf-val').textContent = `${conf}%`;
      setAIConfidence(conf / 100.0);
    });
  }

  // AI Snapshot button
  const btnAiSnap = document.getElementById('btn-ai-snapshot');
  if (btnAiSnap) {
    btnAiSnap.addEventListener('click', captureAISnapshot);
  }
}

/* ==========================================================
 * AI YOLO11x Studio Functions
 * ========================================================== */
let aiStatsInterval = null;
let currentAICamid = null;

function openAIStudioForCamera(camid) {
  openAIStudio(camid);
}

function openAIStudio(preferCamid = null) {
  const modal = document.getElementById('ai-modal');
  if (!modal) return;

  populateAICameraDropdown();

  // If no camera selected, pick first active camera or default to Rama 4 / first camera
  if (preferCamid) {
    currentAICamid = preferCamid;
  } else if (!currentAICamid) {
    const firstActive = state.activeSlots.find(Boolean);
    currentAICamid = firstActive ? firstActive.camid : (state.cameras[0] ? state.cameras[0].camid : '');
  }

  const aiCamSelect = document.getElementById('ai-camera-select');
  if (aiCamSelect && currentAICamid) {
    aiCamSelect.value = currentAICamid;
  }

  modal.classList.add('open');
  switchAICamera(currentAICamid);
  startAIStatsPolling();
}

function closeAIStudio() {
  const modal = document.getElementById('ai-modal');
  if (modal) modal.classList.remove('open');

  stopAIStatsPolling();
  const videoFeed = document.getElementById('ai-video-feed');
  if (videoFeed) videoFeed.src = '';
}

function populateAICameraDropdown() {
  const select = document.getElementById('ai-camera-select');
  if (!select || select.children.length > 0) return;

  select.innerHTML = state.cameras.map(cam => {
    return `<option value="${cam.camid}">[${cam.province}] ${cam.short_title} (${cam.camid})</option>`;
  }).join('');
}

async function switchAICamera(camid) {
  currentAICamid = camid;
  const cam = state.cameras.find(c => c.camid === camid);
  
  const provEl = document.getElementById('ai-selected-prov');
  if (provEl && cam) {
    provEl.textContent = cam.province;
    provEl.className = `prov-tag ${PROVINCE_CLASSES[cam.province] || 'bkk'}`;
  }

  const loadingEl = document.getElementById('ai-stream-loading');
  const feedEl = document.getElementById('ai-video-feed');
  if (loadingEl) {
    loadingEl.style.display = 'flex';
    loadingEl.innerHTML = `
      <div class="spinner"></div>
      <span>กำลังประมวลผล YOLO11x (5 FPS)...</span>
    `;
  }

  const streamUrl = cam ? (cam.hls_url || cam.vdourl || '') : '';
  const camTitle = cam ? (cam.short_title || cam.title || '') : '';
  const camProv = cam ? (cam.province || '') : '';

  try {
    // Notify server to switch camera with fallback stream url
    const params = new URLSearchParams({
      camid: camid,
      stream_url: streamUrl,
      title: camTitle,
      province: camProv
    });
    await fetch(`/api/ai/switch_camera?${params.toString()}`, { method: 'POST' });
  } catch (err) {
    console.warn('Switch camera API error:', err);
  }

  // Set stream source
  if (feedEl) {
    feedEl.src = `/api/ai/stream?camid=${encodeURIComponent(camid)}&t=${Date.now()}`;
    feedEl.onload = () => {
      if (loadingEl) loadingEl.style.display = 'none';
    };
    feedEl.onerror = () => {
      if (loadingEl) {
        loadingEl.innerHTML = `
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f85149" stroke-width="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <span>ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ AI YOLO11x ได้</span>
          <small style="opacity:0.8;">กรุณารันไฟล์ launch/localhost_8000/start.bat หรือ server.py</small>
        `;
      }
    };
  }
}

async function setAITargetFps(fps) {
  document.getElementById('ai-target-fps-val').textContent = `${fps} FPS`;
  try {
    await fetch(`/api/ai/set_fps?fps=${fps}`, { method: 'POST' });
    showToast(`ปรับอัตราตรวจจับเป็น ${fps} FPS เรียบร้อย`);
  } catch (e) {
    console.warn(e);
  }
}

async function setAIConfidence(conf) {
  try {
    await fetch(`/api/ai/set_conf?conf=${conf}`, { method: 'POST' });
  } catch (e) {
    console.warn(e);
  }
}

function startAIStatsPolling() {
  stopAIStatsPolling();
  updateAIStats();
  aiStatsInterval = setInterval(updateAIStats, 400); // 400ms interval for smooth digital counters
}

function stopAIStatsPolling() {
  if (aiStatsInterval) {
    clearInterval(aiStatsInterval);
    aiStatsInterval = null;
  }
}

async function updateAIStats() {
  try {
    const res = await fetch('/api/ai/stats');
    if (res.ok) {
      const stats = await res.json();
      
      // If stats are active, hide stream loading indicator
      if (stats.active) {
        const loadingEl = document.getElementById('ai-stream-loading');
        if (loadingEl && loadingEl.style.display !== 'none') {
          loadingEl.style.display = 'none';
        }
      }

      const carsEl = document.getElementById('ai-count-cars');
      const motosEl = document.getElementById('ai-count-motorcycles');
      const trucksEl = document.getElementById('ai-count-trucks');
      const totalEl = document.getElementById('ai-count-total');
      const statusEl = document.getElementById('ai-traffic-status');
      const latencyEl = document.getElementById('ai-latency-val');
      const fpsEl = document.getElementById('ai-fps-display');

      if (carsEl) carsEl.textContent = stats.cars || 0;
      if (motosEl) motosEl.textContent = stats.motorcycles || 0;
      if (trucksEl) trucksEl.textContent = stats.trucks || 0;
      if (totalEl) totalEl.textContent = stats.total || 0;

      if (latencyEl) latencyEl.textContent = `${stats.latency_ms || 0} ms`;
      if (fpsEl) fpsEl.textContent = `${stats.fps || stats.target_fps || 5.0} FPS`;

      if (statusEl) {
        statusEl.textContent = stats.traffic_level || 'กำลังวิเคราะห์สภาพจราจร...';
        const total = stats.total || 0;
        statusEl.className = 'traffic-status-banner';
        if (total <= 4) {
          statusEl.classList.add('light');
        } else if (total <= 12) {
          statusEl.classList.add('moderate');
        } else {
          statusEl.classList.add('congested');
        }
      }
    }
  } catch (err) {
    // Silent fail if server offline
  }
}

function captureAISnapshot() {
  const img = document.getElementById('ai-video-feed');
  if (!img || !img.src) return;

  try {
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth || 704;
    canvas.height = img.naturalHeight || 576;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/jpeg');
    a.download = `yolo11x_traffic_${currentAICamid || 'cctv'}_${Date.now()}.jpg`;
    a.click();
    showToast('บันทึกภาพผลตรวจจับ YOLO11x เรียบร้อย 📸');
  } catch (err) {
    window.open(img.src, '_blank');
  }
}


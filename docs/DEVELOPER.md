# BKK StreetSmart: คู่มือนักพัฒนา

รายละเอียดเชิงเทคนิคสำหรับคนที่จะแก้โค้ดหรือดูแลเซิร์ฟเวอร์ ภาพรวมแบบอ่านง่ายอยู่ที่ [README](../README.md)

## 🤖 ฟังก์ชันระบบ AI ตรวจจับยานพาหนะ (YOLO26x)
- **โมเดลที่ใช้**: `yolo26x.pt` ค่าเริ่มต้น (COCO) + ByteTrack
- **อัตราการประมวลผล (Target Frame Rate)**: **~10 FPS** บนกล้องสดที่เลือก (ปรับได้ในหน้า Camera AI) และนับรถหลายกล้องในพื้นหลังที่ 0.5 FPS
- **การจำแนกประเภทยานพาหนะ**:
  1. 🚗 **รถยนต์ (Cars)**: สีฟ้า/น้ำเงินนีออน พร้อมกรอบและข้อความเปอร์เซ็นต์ความมั่นใจ
  2. 🏍️ **มอไซ (Motorcycles)**: สีส้ม/เหลืองทอง พร้อมกรอบและข้อความเปอร์เซ็นต์ความมั่นใจ
  3. 🚚 **รถบรรทุก (Trucks / Buses)**: สีแดงส้ม พร้อมกรอบและข้อความเปอร์เซ็นต์ความมั่นใจ
- **การนับและประเมินสภาพจราจรแบบเรียลไทม์**:
  - แสดงตัวเลขดิจิทัลนับแยกตามประเภทแบบสดๆ
  - ประเมินสถานะการจราจร: `🟢 คล่องตัว` / `🟡 ปานกลาง` / `🔴 หนาแน่น`
  - รองรับการเปิดดูกล้อง CCTV ใดก็ได้จาก `config/cameras_bkk.json` (34 ตัว) และกล้อง กทม. ทุกตัว
- **เปลี่ยนโมเดลได้ผ่าน `.env`**: `AI_MODEL=yolo26x.pt` (YOLO26x: mAP 57.5 vs YOLO11x 54.7, NMS-free, เร็วกว่าเล็กน้อย — ทดสอบบน RTX 3080 FP16 ได้ ~36 ms/เฟรม) ไฟล์ `.pt` ดาวน์โหลดอัตโนมัติถ้ายังไม่มี
- **ติดตั้ง PyTorch แบบ CUDA** (ถ้า `torch.cuda.is_available()` เป็น False ระบบจะตกไปใช้ CPU ช้ากว่า ~30 เท่า):

```bash
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130 --force-reinstall --no-deps
```

- **รองรับ GPU Acceleration**: ใช้งาน PyTorch CUDA 12.4 บนการ์ดจอ **NVIDIA GeForce RTX 3050** ความเร็ว Latency เพียง ~65 ms ต่อเฟรม!

---

## 🌸 หน้าเว็บใหม่ (React + Tailwind + framer-motion)

โค้ดหน้าเว็บอยู่ใน `web/` แต่ละเซิร์ฟเวอร์ใช้ไฟล์เว็บที่ build แยกกัน:

- Production (`:8000`): `instances\production\dist`
- Test (`:8001`): `instances\test\dist`

ถ้ายังไม่มีไฟล์เว็บ เซิร์ฟเวอร์ยังเปิด API ได้ แต่หน้าแรกจะแสดงข้อผิดพลาด `503` ให้ build หน้าเว็บก่อน โดยต้องติดตั้ง Node.js ไว้ในเครื่อง

```bash
cd web
npm install
npm run build -- --outDir ../instances/test/dist   # สร้างหน้าเว็บสำหรับ Test (:8001)
npm run dev        # แก้หน้าเว็บและดูผลที่ http://localhost:5173 โดยใช้ API ของ :8000
npm run dev:8001   # เหมือนกัน แต่ใช้ API ของ Test (:8001)
```

ไฟล์ที่ build แล้วไม่เก็บใน Git ตอนเปิดเซิร์ฟเวอร์ สคริปต์จะลองสร้างหน้าเว็บให้ถ้ายังไม่มี `dist` ถ้าแก้หน้าเว็บแล้วมี `dist` อยู่เดิม ให้ build ใหม่ด้วยคำสั่งด้านล่าง เพราะการ restart อย่างเดียวจะยังใช้หน้าเว็บเดิม คำสั่ง `npm run build` แบบไม่มี `--outDir` จะสร้าง `web/dist` ซึ่งเซิร์ฟเวอร์ไม่ได้ใช้

---

## 🗺️ แผนที่จราจร / 🤖 AI ผู้ช่วยการจราจร / 📊 แดชบอร์ด

เมนูซ้ายแบ่งเป็น 4 กลุ่ม: **ภาพรวม** (ภาพรวมจราจร, แผนที่จราจร) · **กล้อง** (กล้อง AI, ดูกล้องสด) · **เฝ้าระวังเมือง** (น้ำท่วม, อุบัติเหตุ, แจ้งเตือน, แผ่นดินไหว) · **เครื่องมือ** (ถาม AI, แจ้งน้ำท่วม, สถิติผู้ใช้) ชื่อหน้ามาจาก `PAGE_TITLES` ใน `web/src/components/Sidebar.jsx`

- **เส้นจราจร (เขียว/เหลือง/แดง)** ดึงจาก Longdo Traffic vector tiles (`msv.longdo.com/maps/traffic`) ผ่านเซิร์ฟเวอร์ของเราที่แคชไว้ในโฟลเดอร์ `instances\production\cache\` ถ้าเน็ตหลุดจะแสดงข้อมูลล่าสุดที่บันทึกไว้
- **แผนที่ออฟไลน์**: แผนที่พื้นฐาน (OpenStreetMap) จะถูกเก็บลงเครื่องอัตโนมัติเมื่อเปิดดู หรือดาวน์โหลดล่วงหน้าทั้งกรุงเทพฯ ด้วย

```bash
.venv\Scripts\python local\pipeline\prefetch_tiles.py
```

- **AI ผู้ช่วยการจราจร** วิเคราะห์การระบายรถรายถนนจากเส้นจราจรทุกสาย (จับคู่ชื่อถนนจาก Longdo base map) ใช้ **Gemini Flash-Lite** เมื่อใส่ key ในไฟล์ `.env` (สร้าง key ฟรีที่ https://aistudio.google.com/apikey):

```
GEMINI_API_KEY=AIza...
# ไม่บังคับ: เปลี่ยนรุ่น (ค่าเริ่มต้น gemini-3.5-flash-lite) รุ่นฟรีจำกัด 500 ครั้ง/วัน หมดแล้วแชทจะตกไปโหมดออฟไลน์
GEMINI_MODEL=gemini-3.5-flash-lite
# ไม่บังคับ: ตัวสำรองเมื่อ Gemini ใช้ไม่ได้ (โควตาหมด/ล่ม)
ANTHROPIC_API_KEY=
# โมเดล vision สำหรับตรวจภาพ (อุบัติเหตุ/หมวก) ใช้รุ่น lite ที่ไม่ใช่ thinking จะเร็วกว่ามาก (2-6 วิ/ภาพ)
GEMINI_VISION_MODEL=gemini-3.5-flash-lite
# ตรวจหมวก: ใช้ AI ตัวไหน (qwen = โมเดล Qwen vision ตัวเดียวกับ LOCAL_LLM_* ค่าเริ่มต้น, cloud = Gemini/Claude), จำกัดการเรียกต่อชั่วโมง, โมเดล Gemini เมื่อใช้ cloud
HELMET_AGENT=qwen
HELMET_PATROL_MAX_PER_HOUR=600
HELMET_AGENT_MODEL=gemini-3.1-flash-lite
# สแกนกล้อง กทม.: ดึงภาพพร้อมกันกี่ตัว, เริ่มรอบใหม่ทุกกี่วินาที (ตรวจหมวกทุกกล้องตามรอบนี้)
BMA_SCAN_WORKERS=5
BMA_SCAN_INTERVAL=180
# ตรวจย้อนศร: โมเดลทิศทางรถ (เทรนด้วย local\pipeline\wrongway_pipeline.bat), งบ AI ต่อชั่วโมง, จำนวนรถขั้นต่ำต่อช่องก่อนตัดสิน
WRONGWAY_DET=wrongway_det.pt
WRONGWAY_MAX_PER_HOUR=120
WRONGWAY_MIN_VOTES=40
# AI ดูน้ำท่วมจากกล้อง กทม. (ใช้โมเดล Qwen vision ตัวเดียวกับ LOCAL_LLM_*): ตรวจกล้องแห้งทุกกี่วินาที, กล้องที่มีน้ำทุกกี่วินาที, งบเรียกต่อชั่วโมง
FLOOD_CAM_INTERVAL=300
FLOOD_CAM_WET_INTERVAL=300
FLOOD_CAM_MAX_PER_HOUR=1500
# กล้อง iTIC ที่ให้ AI ดูน้ำท่วมด้วย: จังหวัด (คั่นด้วย , หรือ all = ทุกตัว ~210 ตัว โหลด ~150 MB/รอบ) และรอบดึงภาพ (วินาที)
FLOOD_CAM_ITIC_PROVINCES=กรุงเทพมหานคร,นนทบุรี,ปทุมธานี,สมุทรปราการ,สมุทรสาคร,นครปฐม
FLOOD_CAM_ITIC_SECONDS=300
# ประชาชนแจ้งน้ำท่วมพร้อมรูป: แสดงบนแผนที่กี่ชั่วโมง, จำกัดต่อ IP ต่อชั่วโมง/วัน, ขนาดคำขอสูงสุด (ไบต์)
USER_REPORT_HOURS=6
USER_REPORT_RATE_PER_HOUR=5
USER_REPORT_RATE_PER_DAY=20
USER_REPORT_MAX_BODY=6291456
# ป้องกันสาธารณะ: ตั้งแล้วส่ง header X-Admin-Token เพื่อกดปุ่มควบคุมจากนอก LAN
ADMIN_TOKEN=
# โฟลเดอร์เก็บ CSV รอบนับกล้อง กทม. + ภาพหลักฐานฝ่าฝืน (ค่าเริ่มต้น D:\Data)
BMA_DATA_DIR=E:\data smartstreet
```

ลำดับผู้ให้บริการ: Gemini (`GEMINI_API_KEY`) → Claude (`ANTHROPIC_API_KEY`) → โหมดออฟไลน์ (สรุปจากข้อมูลสด ไม่ต้องใช้ key)

### 🌐 เปิดเว็บให้คนอื่นเข้าดู

ลิงก์สาธารณะ (ชื่อเดียว):

| เว็บ | ลิงก์ |
|---|---|
| BKK StreetSmart | https://bkksmartstreet.com |
| ENVIRO | https://bkksmartstreet.com/enviro/ (หน้า "แผ่นดินไหว" ใน BKK ก็ฝังหน้านี้ไว้) |

- เปิดให้คนนอกเข้าผ่าน **Cloudflare Tunnel** อย่างเดียว ไม่ใช้ Tailscale Funnel แล้ว (Tailscale ยังเปิดอยู่สำหรับเข้าเครื่องจาก tailnet)
- Tunnel รันเป็น Windows service ชื่อ `cloudflared` เปิดเองตอนบูต ไม่ขึ้นกับสคริปต์ start/stop ตั้งค่าอยู่ที่ `launch\cloudflare\config.yml` (tunnel `bkk-streetsmart`) ไฟล์ลับของ tunnel อยู่ที่ `C:\Users\user\.cloudflared\` ไม่เก็บใน Git
  - หลังแก้ `config.yml`: `Restart-Service cloudflared` (ต้องเปิด PowerShell แบบ admin)
  - ติดตั้งใหม่หรือซ่อม service: `launch\cloudflare\install_service.ps1` (แบบ admin)
  - `/enviro` ส่งไปที่ ENVIRO (:5050) ส่วนที่เหลือส่งไปที่ BKK ซึ่งต้องชี้ไปที่ `http://127.0.0.2:8000` ไม่ใช่ `127.0.0.1` เพราะ `access_guard.py` อ่าน IP จริงของผู้เข้าชมจาก `CF-Connecting-IP` เฉพาะการเชื่อมต่อที่เข้ามาทาง `127.0.0.2`
- `launch\production\start.bat` เช็คว่า service `cloudflared` รันอยู่ แล้วแสดงลิงก์สาธารณะ
- `start_local.bat` ไม่ได้ปิดลิงก์สาธารณะ ถ้าจะใช้แค่ในเครื่อง/เครือข่ายภายใน ต้องหยุด service ด้วย `Stop-Service cloudflared` (แบบ admin)
- `launch\production\stop.bat` หยุดเซิร์ฟเวอร์ Production ระหว่างนั้นลิงก์สาธารณะจะขึ้นหน้า error ของ Cloudflare

ดูวิธีเริ่มและหยุดเซิร์ฟเวอร์ได้ในหัวข้อ **🚀 วิธีเปิดใช้งาน** ด้านล่าง

- API: `GET /api/traffic/summary`, `GET /api/traffic/roads?q=`, `POST /api/chat`, tiles ที่ `/api/traffic/tile/{z}/{x}/{y}.pbf` และ `/api/tiles/base/{z}/{x}/{y}.png`

#### 🔒 การป้องกันเมื่อเปิดสาธารณะ (`backend/core/access_guard.py`)

เปิดใช้อัตโนมัติ ไม่ต้องตั้งค่าเพิ่ม:

- **endpoint ควบคุม** (POST/PUT/DELETE เช่น เปลี่ยนกล้อง, ตั้ง FPS, สแกน BMA, ลบผลตรวจ) ใช้ได้เฉพาะ localhost / LAN / tailnet (ผู้เข้าชมผ่าน Cloudflare นับเป็นคนนอกเสมอ) หรือส่ง header `X-Admin-Token` ให้ตรงกับ `ADMIN_TOKEN` ใน `.env` — คนนอกได้ `403`
- **`/api/chat`** (ใช้ key Gemini/Claude) จำกัดต่อ IP ค่าเริ่มต้น 6 ครั้ง/นาที, 60 ครั้ง/วัน, body ไม่เกิน 8000 bytes — เกินได้ `429` / `413`
- request ทั่วไปจากคนนอกจำกัด 600 ครั้ง/นาที ต่อ IP
- **กันดึง API** (คนนอกเท่านั้น): `/api/` ตอบเฉพาะคำขอที่เบราว์เซอร์ส่งจากหน้าเว็บนี้ (`Sec-Fetch-Site: same-origin`) **และ**มี cookie `bkk_s` ที่ server เซ็นให้ตอนเปิดหน้าเว็บ (HMAC ของเวลา, key อยู่ที่ `instances\<ชื่อ>\cache\session_secret`, HttpOnly, SameSite=Strict, Secure เมื่อมาทาง Cloudflare, อายุ 12 ชม. ต่ออายุเองทุก 1 ชม. ระหว่างหน้าเว็บเปิดอยู่) — สคริปต์ที่ปลอม header แต่ไม่ได้เปิดหน้าเว็บได้ `403` · หน้าเว็บที่เปิดค้างไว้ตั้งแต่ก่อน deploy ต้อง reload หนึ่งครั้ง · `robots.txt` ห้ามบอตทั้งเว็บ · ปิดได้ด้วย `API_BROWSER_ONLY=0` / `API_SESSION=0` · กันได้แค่ระดับหนึ่ง: คนที่ตั้งใจจริงยังเปิดหน้าเว็บแล้วเก็บ cookie ไปใช้ได้ ชั้นที่แรงกว่านี้คือ Bot Fight Mode / WAF rate limit ของ Cloudflare

ปรับได้ใน `.env`:

```
ADMIN_TOKEN=รหัสลับสำหรับสั่งงานจากข้างนอก
CHAT_RATE_PER_MIN=6
CHAT_RATE_PER_DAY=60
CHAT_MAX_BODY=8000
GENERAL_RATE_PER_MIN=600
API_BROWSER_ONLY=1
API_SESSION=1
```

หมายเหตุ: endpoint เส้นจราจรของ Longdo เป็นการใช้งานแบบไม่เป็นทางการ อาจเปลี่ยนหรือต้องใช้ key ในอนาคต

---

## 🌊 น้ำท่วมรายจังหวัด (หน้าน้ำท่วม แท็บ "น้ำท่วมทั่วประเทศ")

- `backend/water/province_flood.py` อ่านข้อมูลทั้งประเทศจากคลังข้อมูลน้ำแห่งชาติ (`api-v3.thaiwater.net/.../public/thailand` ไม่ต้องใช้ key) ทุก 30 นาที: จุดวัดระดับน้ำ ~800 จุด (% ของตลิ่ง, น้ำขึ้นหรือลง) และจุดวัดฝน ~4,600 จุด รวมกับทางหลวงที่น้ำท่วมจากกรมทางหลวง (HDMS ทุกจังหวัด `hdms_floods.national()`)
- ระดับของแต่ละจังหวัด (ดูความกว้าง ไม่ใช่จุดเดียว): วิกฤต (ล้นตลิ่ง ≥ 3 จุด และ ≥ 30% ของจุดวัดในจังหวัด, หรือล้นและยังขึ้น ≥ 2 จุด, หรือทางหลวงท่วมที่ยังเปิดอยู่ ≥ 5) / น้ำล้นตลิ่ง/ท่วม (ล้นตลิ่ง ≥ 1 หรือทางหลวงท่วม ≥ 1 หรือคนแจ้ง ≥ 5) / เฝ้าระวัง (น้ำสูง ≥ 2 จุด หรือ 1 จุดที่เป็น ≥ 20% ของจุดวัด, ฝน 24 ชม. เกิน 90 มม. หรือเกิน 35 มม. ≥ 3 จุด, คนแจ้ง ≥ 2) / ปกติ
- AI (โมเดล `LOCAL_LLM_*`) เขียนภาพรวมและบทวิเคราะห์ + คำแนะนำของจังหวัดที่ไม่ปกติ (สูงสุด 30 จังหวัด) เฉพาะตอนข้อมูลเปลี่ยน หรือทุก 1 ชม. ไม่มีโมเดลก็แสดงสรุปจากตัวเลข
- API: `GET /api/flood/provinces` · เก็บผลล่าสุดที่ `instances\<ชื่อ>\province_flood.json`
- ยังไม่มีจำนวนผู้ประสบภัยของ ปภ. (ไม่มี API เปิด)
- ปรับใน `.env`: `PROVINCE_FLOOD_SECONDS=1800`, `PROVINCE_FLOOD_AI_MAX_AGE=3600`

---

## 📍 ขอบเขตพื้นที่กล้อง
- **กล้องสตรีมสด (`config/cameras_bkk.json`, 34 ตัว)**: กรุงเทพมหานคร 22, นครปฐม 5, นนทบุรี 3, สมุทรปราการ 3, ปทุมธานี 1
- **กล้อง กทม. (`config/cameras_bma.json`, 574 ตัว)**: snapshot ทุก ~3 นาที (`BMA_SCAN_INTERVAL`) นับรถด้วย YOLO และใช้ตรวจหมวกกันน็อก/ย้อนศร
- **กล้อง iTIC (Longdo `traffic.longdo.com/camera.json`)**: ~170 ตัวที่ยังเปิดอยู่ ใน 39 จังหวัด
- **กล้องกรมทางหลวง (`backend/vision/doh_cameras.py`)**: อ่านจาก `highwaytraffic.go.th` วันละครั้ง (~210 จุด ลองลิงก์ทุกตัว เก็บเฉพาะที่เล่นได้ ~100 สตรีม) เก็บไว้ที่ `cache\doh_cameras.json` ตัวที่ Longdo มีอยู่แล้วจะไม่ซ้ำ
- **กล้องทั่วประเทศอื่น ๆ (`backend/vision/world_cameras.py`)**: อ่านรายชื่อตรงจากหน่วยงานเจ้าของกล้อง วันละครั้ง เก็บที่ `cache\world_cameras.json`: กทม. ระบายน้ำ (floodbangkok ~876 ภาพนิ่งผ่าน `/api/proxy` ของเขา), เมืองพัทยา (~580 ดูภาพได้ที่เว็บพัทยาเท่านั้นเพราะมี Cloudflare Turnstile), นครศรีธรรมราช (~220 ฝัง player ของเขา), กรมทรัพยากรน้ำ (~127 ภาพผ่าน `/api/cameras/image/{camid}` เก็บ 10 นาทีใน `cache\world_images`), ปากเกร็ด (~40), เกาะสมุย (24 วิดีโอ webm) ไม่ใช้ API ของ JK World (เขาจำกัดให้ใช้กับเว็บเขาเท่านั้น) และไม่ใช้ลิงก์กล้องที่มีรหัสผ่านในรายชื่อของกรมทรัพยากรน้ำ
- **หน้าดูกล้องสด แท็บ "แผนที่"** (`cameras/MapPanel.jsx`): กล้องทุกตัวบนแผนที่ประเทศไทย รวมกลุ่มจุด เรดาร์ฝน RainViewer และช่องกล้องในกรอบแผนที่ด้านขวา
- **หน้าดูกล้องสด แท็บ "กล้องทั่วประเทศ"**: กล้องทุกแหล่งรวมกัน (~800 ตัว) เลือกภาค แล้วเลือกจังหวัด พร้อมแผนที่จุดกล้อง ภาคและจังหวัดมาจาก `backend/core/thai_regions.py` (6 ภาค 77 จังหวัด จาก geocode หรือชื่อจังหวัด ถ้าไม่มีจะถามตำแหน่งจาก Nominatim ครั้งเดียวแล้วเก็บไว้ที่ `cache\province_at.json`)

---

## 🚀 วิธีเปิดใช้งาน

มีเซิร์ฟเวอร์ 2 ตัว ใช้โค้ดชุดเดียวกัน แต่เก็บข้อมูลไว้คนละโฟลเดอร์ ทั้งสองตัวเริ่มและหยุดได้จากสคริปต์ใน `launch\production` และ `launch\test`

| เซิร์ฟเวอร์ | ที่อยู่ | ใช้ทำอะไร | สคริปต์ใน `launch\` | โฟลเดอร์ข้อมูล |
|---|---|---|---|---|
| 🌐 **Production** | `http://localhost:8000` และลิงก์สาธารณะ | เซิร์ฟเวอร์หลัก | `production\start.bat` เปิดลิงก์สาธารณะ · `production\start_local.bat` เปิดในเครื่อง/เครือข่าย · `production\restart.bat` เริ่มใหม่ · `production\stop.bat` หยุดและปิดลิงก์ | `instances\production\` |
| 🧪 **Test** | `http://localhost:8001` | ทดลองการแก้ไขก่อนอัปเดต Production | `test\start.bat` เริ่ม · `test\restart.bat` เริ่มใหม่ · `test\stop.bat` หยุด | `instances\test\` |

- Production กับ Test เปิดพร้อมกันได้ เพราะใช้คนละพอร์ตและฐานข้อมูล
- Test ใช้ cache แผนที่และ API key เดียวกับ Production และรันงาน AI เบื้องหลังด้วย จึงควรปิดเมื่อไม่ใช้งาน
- เปิด Test ครั้งแรก ระบบจะคัดลอก cache บางส่วนและฐานข้อมูลจาก Production ไปไว้ใน `instances\test\` ถ้าจะลบโฟลเดอร์นี้เพื่อเริ่มใหม่ ให้หยุด Test และสำรองข้อมูลก่อน (ข้อมูลใน Test จะถูกลบ)
- หลังแก้หน้าเว็บ ให้ build สำหรับ Test ด้วย `npm run build -- --outDir ../instances/test/dist` จากโฟลเดอร์ `web` แล้วเปิดหรือรีโหลดหน้า `:8001`
- เมื่อตรวจหน้าเว็บบน Test แล้ว ให้ build สำหรับ Production ลงโฟลเดอร์ใหม่ก่อน ห้าม build ลง `dist` ตรง ๆ ขณะ :8000 รันอยู่ (Vite จะลบไฟล์เก่าไปครึ่งทาง แล้วบางหน้าจะเสีย):
  1. `npx vite build --outDir ../instances/production/dist_next` (ในโฟลเดอร์ `web`)
  2. คัดลอกไฟล์ใหม่ใน `dist_next/assets/` ไปที่ `dist/assets/` (ไม่ทับไฟล์เดิม)
  3. คัดลอก `index.html` เป็นไฟล์สุดท้าย หน้าเว็บจะเปลี่ยนโดยไม่ต้อง restart
- **ทั้งเว็บในปุ่มเดียว:** `launch\site\start.bat` / `restart.bat` / `stop.bat` เปิด/เริ่มใหม่/ปิด Production และ ENVIRO (:5050) พร้อมกัน (shortcut "BKK ALL ..." บน Desktop)
- **เฝ้าเว็บล่ม:** scheduled task "BKK StreetSmart watchdog" (ติดตั้งด้วย `launch\watchdog\install.ps1`, ลบด้วย `install.ps1 -Remove`) รัน `launch\watchdog\watchdog.ps1` ทุก 2 นาทีขณะ login อยู่: ถ้า `http://127.0.0.1:8000/` หรือ `:5050/` ไม่ตอบ (หรือตอบ 5xx) 2 รอบติด จะสั่ง `restart.bat` ของตัวนั้นในหน้าต่างย่อ แล้วรอ 5 นาทีก่อนเช็คใหม่ · ปิดด้วย `stop.bat` / `kill_server.ps1` จะทิ้งไฟล์ `launch\watchdog\state\stopped_<port>` ไว้ watchdog จึงไม่เปิดคืน (`start.bat` ลบไฟล์นี้) · log: `launch\watchdog\state\watchdog.log` · server ที่เปิดใหม่ push "เซิร์ฟเวอร์เริ่มทำงาน" หัวข้อระบบขัดข้องถึงผู้ดูแล
- ทดลองแก้หน้าเว็บโดยไม่ build ได้ด้วย `npm run dev` (ใช้ API ของ `:8000`) หรือ `npm run dev:8001` (ใช้ API ของ `:8001`)

ขั้นตอน:
1. ดับเบิลคลิก **`launch\production\start.bat`** เพื่อเปิดลิงก์สาธารณะ หรือ **`launch\production\start_local.bat`** เพื่อใช้ในเครื่อง/เครือข่ายภายในเท่านั้น
2. รอให้เซิร์ฟเวอร์เริ่มทำงาน แล้วเปิด `http://localhost:8000` ในเว็บเบราว์เซอร์
3. ระบบเริ่มงาน AI โดยใช้ GPU ถ้ามีและพร้อมใช้งาน หากไม่มี GPU การประมวลผลอาจช้าลง
4. เลือกหน้า **กล้อง AI** จากเมนูซ้าย หรือกดไอคอนหุ่นยนต์บนหน้าต่างกล้องเพื่อดูผลวิเคราะห์การจราจร

## 📁 โครงสร้างโฟลเดอร์หลัก

โฟลเดอร์หลักมีโค้ดและการตั้งค่าของเซิร์ฟเวอร์ ส่วน `instances/` เก็บฐานข้อมูล cache และหน้าเว็บที่ build แล้ว ข้อมูลใน `instances/` ไม่เก็บใน Git จึงควรสำรองแยกต่างหาก โฟลเดอร์ `local/` ใช้เก็บสคริปต์ทำงานในเครื่อง ชุดข้อมูลฝึกโมเดล บันทึก และไฟล์เก่า

```
<project root>\
├── server.py                     ← 🌐 จุดเริ่มต้นเซิร์ฟเวอร์ (FastAPI, REST API ทั้งหมด)
├── backend/                      ← 🌐 โค้ด backend แยกตามหมวด (Python package)
│   ├── core/     instance (พอร์ต/โฟลเดอร์ข้อมูล), access_guard, telemetry, alert, local_llm
│   ├── vision/   yolo_detector, count_workers, survey, vehicle_log, helmet, wrongway, violation, incident
│   ├── bma/      กล้อง กทม.: bma_service, bma_archive, bma_events
│   ├── traffic/  traffic, road, guidance, rsc, analytics
│   ├── water/    water, flood, flood_feeds, weather_now, air
│   └── agents/   AI วิเคราะห์: flood, riskbkk, traffy (+history), water, chat
├── config/                       ← 🌐 ข้อมูลกล้อง cameras_bkk.json, cameras_bma.json
├── launch/                       ← ▶️ ตัวรัน
│   ├── production/      start / restart / stop / start_local   (:8000)
│   ├── test/            start / restart / stop                 (ทดสอบ :8001)
│   ├── cloudflare/      config.yml + install_service.ps1        (Cloudflare Tunnel → bkksmartstreet.com)
│   ├── enviro/, bma_watch/
│   ├── kill_server.ps1  (ใช้ร่วม: หยุดเซิร์ฟเวอร์ตามพอร์ต)
│   └── build_web.bat
├── instances/                    ← ฐานข้อมูลและ cache ของแต่ละเซิร์ฟเวอร์ (ไม่เก็บใน Git)
│   ├── production/      cache/, vehicle_counts.db, *_agent.json, dist/   ← ของ :8000
│   └── test/            cache/, vehicle_counts.db, data/, dist/          ← ของ :8001
├── web/  (src/ = ซอร์ส React)    ← 🌐 หน้าเว็บ (build ลง instances\<ชื่อ>\dist)
├── tests/                        ← pytest
├── requirements.txt, .env        ← config (.env ห้าม commit)
├── yolo26x.pt (+ yolo26l/m), *_bkk.pt, helmet_*.pt, wrongway_*.pt ← 🌐 โมเดล ใช้ร่วมทั้งสองเซิร์ฟเวอร์ (gitignore, ต้องคัดลอกเอง)
│
└── local/                                            ← 💻 ใช้ในเครื่องเท่านั้น
    ├── pipeline/   สคริปต์เก็บภาพ/label/เทรน + .bat/.sh ทั้งหมด (pipeline.bat, collect.bat, status.bat, watch_training.bat ...)
    ├── dataset/, dataset_helmet/, runs/, logs/         ข้อมูลเทรนและผลลัพธ์ (gitignore)
    ├── scratch/    ไฟล์ทดลอง
    └── archive/    ของเก่า/สำรอง
```

- ไฟล์ `.bat` ใน `local/pipeline/` ดับเบิลคลิกได้เหมือนเดิม (สคริปต์ `cd` กลับไป root เอง) ผลลัพธ์โมเดล `*_bkk.pt` / `helmet_cls.pt` ยังถูกเขียนลง root ให้เซิร์ฟเวอร์หยิบใช้
- เซิร์ฟเวอร์ส่งให้ผู้ใช้เฉพาะหน้าเว็บใน `instances\<ชื่อ>\dist` ไม่ได้เปิดให้เข้าถึงไฟล์ทั้งโฟลเดอร์โปรเจกต์

---

## 🧪 Tests

```bash
.venv\Scripts\python -m pytest tests
```

ครอบคลุมเกณฑ์ระดับน้ำบนถนน/ฝน/ตลิ่งใน `backend/traffic/road_service.py`, การคาดการณ์น้ำเหนือใน `backend/water/north_flow.py` และผลกระทบรายเขตใน `backend/agents/north_impact_agent.py`, การป้องกันใน `backend/core/access_guard.py` และ context ของ chatbot

---

## แผนผังโค้ด (Code map)

### Backend (Python, FastAPI)
| ไฟล์ | หน้าที่ |
|---|---|
| `backend/core/instance.py` | พอร์ตและโฟลเดอร์ข้อมูลของ instance นี้ (`PORT`, `INSTANCE_DIR`): ทุก service ดึง path ของ `cache/`, `vehicle_counts.db` และ `dist/` จากที่นี่ (`instances/production` หรือ `instances/test`) ให้เซิร์ฟเวอร์จริง (:8000, `launch/production`) กับเซิร์ฟเวอร์ทดสอบ (:8001, `launch/test`) รันพร้อมกันได้โดยไม่เขียนทับกัน |
| `server.py` | จุดเริ่มต้น: โหลดกล้อง, สร้าง detector/scanner/services, ประกาศ REST API ทั้งหมด, เสิร์ฟหน้าเว็บจาก `<instance>/dist` |
| `backend/vision/yolo_detector.py` | YOLO26x + ByteTrack บนสตรีมกล้องเดียว (หน้า AI ตรวจจับรถสด), นับรถผ่าน, ประเมินระดับจราจร, ตรวจรถจอดนิ่ง/ชน |
| `backend/vision/count_workers.py` | นับรถต่อเนื่องหลายกล้องในพื้นหลัง (แดชบอร์ด "จำนวนรถที่ผ่านกล้อง AI") |
| `backend/vision/survey.py` | วนสำรวจทุกกล้องสั้น ๆ เพื่อให้ป้ายระดับ โล่ง/ปานกลาง/ติดขัด ในหน้ากล้อง |
| `backend/vision/vehicle_log.py` | SQLite `vehicle_counts.db`: ยอดรายชั่วโมง, sample จาก survey, เหตุการณ์จากกล้อง |
| `backend/vision/incident_service.py` | รวมเหตุการณ์: กล้อง AI (ยืนยันด้วย Claude vision) + รายงาน Longdo |
| `backend/traffic/traffic_service.py` | ดึง tile จราจร Longdo, สรุปการระบายรถรายถนน, proxy tile แผนที่ |
| `backend/traffic/area_traffic.py` | คะแนนรถคล่อง **รายจังหวัดและรายอำเภอ** ทั้งประเทศ ทุก 5 นาที: อ่าน tile จราจร Longdo ระดับ z11 ทั้งประเทศ (~1,700 tile, ไม่เกิน 6 tile/วินาที, ใช้ tile ใน cache ที่อายุไม่ถึง 4 นาทีซ้ำ) ส่วนเขตของ กทม. ใช้ tile z12 ที่ `traffic_service` ดึงอยู่แล้ว แล้วจัดเส้นเข้าอำเภอตามขอบเขตใน `config/thailand_districts.geojson` (928 อำเภอ จาก OpenGISData-Thailand) · `GET /api/traffic/areas` · เก็บผลที่ `instances\<ชื่อ>\cacherea_traffic.json` · ตัวกรองจังหวัด/อำเภอในการ์ด "รถติดแค่ไหนตอนนี้" |
| `backend/traffic/near_traffic.py` · `GET /api/traffic/near?lat=&lng=` | ปุ่ม "ใกล้ฉัน" ในการ์ด "รถติดแค่ไหนตอนนี้": อ่าน tile จราจร Longdo z12 ที่คลุมรัศมี 3 กม. (2-4 tile, ใช้ cache 60 วิของ `traffic_service`) ตั้งชื่อเส้นจากถนนใกล้สุดใน base tile แล้วรวม กม. เขียว/เหลือง/แดงรายถนน เรียงตาม กม. สีแดง · ใส่อำเภอ (`area_traffic.locate`) และอุบัติเหตุ/ถนนปิด/น้ำท่วมในรัศมี · หน้าเว็บปัดพิกัดเป็นทศนิยม 2 ตำแหน่ง (~1 กม.) ก่อนส่ง และ server ปัดซ้ำ ตำแหน่งจริงจึงไม่ถึง server หรือ log · ผลเก็บ 60 วิต่อช่อง ~1 กม. · เป็น GET เพราะ `access_guard` ไม่ให้ POST จากภายนอก |
| `backend/traffic/area_roads.py` · `GET /api/traffic/guidance/area?province=&amphoe=` | การ์ด "ถนนสายหลัก: ติดตรงไหน เลี่ยงทางไหน" เมื่อเลือกจังหวัด/อำเภอในการ์ด "รถติดแค่ไหนตอนนี้" (เลือกกรุงเทพฯ ทั้งจังหวัดยังเป็น 12 เส้นทางเดิมของ `guidance_service`): เส้นจราจร Longdo ที่จุดกลางอยู่ในเขตพื้นที่ (z11 นอก กทม. = tile ที่ `area_traffic` อ่านทุก 5 นาที, z12 ใน กทม.) ตั้งชื่อจากถนนใกล้สุดใน base tile การ์ดละถนน (≥ 1 กม. ในพื้นที่ สูงสุด 24) จุดที่ติด = ก้อนสีแดงราย ~1 กม. ตั้งชื่อด้วยถนนอื่นที่ใกล้สุด · ทางเลี่ยง = ถนนในพื้นที่ห่างไม่เกิน 8 กม. ที่รถคล่องก่อน · เหตุ = อุบัติเหตุ/ถนนปิด/น้ำท่วมห่างถนนไม่เกิน 300 ม. · คำแนะนำใช้ template ของ `guidance_service` (ไม่เรียก AI) · เก็บผล 5 นาทีต่อพื้นที่ · ตอนเปิด server `area_roads.warm()` ดึง base tile z11 ทั้งประเทศครั้งเดียว (~1,700 tile, 3 tile/วินาที, เก็บถาวร) ก่อนดึงครบ จังหวัดที่เปิดครั้งแรกอาจรอ ~1 นาที |
| `GET /api/road/events` (`server.py`) | อุบัติเหตุและถนนปิด **ทั่วประเทศ** สำหรับแผนที่จราจร: จาก Longdo event feed (`incident_service.road_events()`: อุบัติเหตุ/รถเสียทุกจังหวัด, type 19 ถนนปิด, type 18 เบี่ยงจราจร และน้ำท่วมทางหลวงที่กรมทางหลวงระบุว่า "ผ่านไม่ได้") รวมกับอุบัติเหตุ (3 ชม.ล่าสุด) และงานปิด/เบี่ยงถนน (24 ชม.) ของศูนย์จราจร กทม. แต่ละจุดมีจังหวัดและอำเภอจาก `area_traffic.locate()` · รายการเดิม `/api/incidents` ยังเป็นเฉพาะ กทม. และปริมณฑล |
| `GET /api/flood/national-map` (`server.py`) | จุดน้ำท่วม **ทั่วประเทศ** สำหรับหมุด "น้ำท่วม" บนแผนที่จราจร: ถนนน้ำท่วมจาก Longdo feed (กรมทางหลวงและคนแจ้ง, ผ่านได้/ผ่านไม่ได้จากชื่อเรื่อง) เติมความลึกน้ำจาก HDMS เมื่อตำแหน่งตรงกัน (ห่างไม่เกิน ~300 ม.) บวกใบงาน HDMS ที่ Longdo ไม่มี และจุดวัดแม่น้ำที่ล้นตลิ่ง (`province_flood`) · ถนนที่ผ่านไม่ได้ซ่อนจากหมุดน้ำท่วมเมื่อเปิดหมุดถนนปิดอยู่ (ขึ้นเป็นถนนปิดแทน) |
| `GET /api/water/map` (`server.py`) | แผนที่น้ำ (แท็บ "ระดับน้ำตอนนี้") เป็น**ทั่วประเทศ**ทุกชั้น: ระดับน้ำ = จุดวัดของ กทม./ปริมณฑลจาก `water_service.get_map()` บวกจุดวัดแม่น้ำทั่วประเทศจาก `province_flood.gauges()` (~790 จุด; `situation_level` 5 ล้นตลิ่ง / 4 ใกล้ล้น / 3 ปกติ / 1-2 น้ำน้อย) · ฝน 24 ชม. = จุดวัดฝนทั้งหมด ~4,600 จุด (`province_flood.rain_points()`, เกณฑ์ `_rain_level`) · เขื่อน = เขื่อนใหญ่ 35 แห่ง (`province_flood.dams()`, จังหวัดจาก `area_traffic.locate`) · น้ำท่วมถนน = เซ็นเซอร์ กทม. + ใบงาน HDMS ทุกจังหวัด (`hdms_floods.national()` เติมรูปจากรายการ กทม.) + ข่าวน้ำท่วม Longdo ทุกจังหวัดที่ไม่ซ้ำกับใบงาน HDMS (ห่างเกิน ~300 ม.) + เรื่องที่คนแจ้ง (สถานะ `people`, ยังไม่ยืนยัน): Traffy Fondue ใน กทม. (มีรูป ลิงก์ และสถานะเรื่อง), แจ้งผ่านเว็บนี้ (รูป + ผล AI ตรวจรูป), ข่าวน้ำท่วมของศูนย์จราจร กทม. · `roads_text` = ข่าววิทยุ JS100 ที่ไม่มีพิกัด แสดงเป็นข้อความข้างแผนที่ · จุดทั่วประเทศข้ามเมื่อห่างจากจุดของ กทม. ไม่ถึง ~100 ม. และไม่มี `station_id` (รหัสใน snapshot ไม่ตรงกับ API กราฟ) · ข้อมูลทั่วประเทศอัปเดตทุก 30 นาทีตามรอบของ `province_flood` |
| `backend/agents/chat_service.py` | หน้า "Ask AI": รวมข้อมูลสดทุกหมวด (จราจร น้ำ/ฝน PM2.5 อุบัติเหตุ เส้นเลี่ยง น้ำท่วมรายถนน การฝ่าฝืน analytics) เป็น context ดึงถนน/เขตที่ผู้ใช้ถามขึ้นก่อน แล้วให้ Gemini → Claude → rule-based ตอบตามลำดับ |
| `backend/bma/bma_service.py` | สแกนกล้อง กทม. 574 ตัว (snapshot ทุก ~3 นาที) นับรถด้วย YOLO, เก็บ `bma_latest`/`bma_history`, สตรีม MJPEG · อ่านจากเว็บ BMA Traffic ตามที่อยู่ใน `bma_site.py` (`www.bmatraffic.com` ก่อน, `cpudapp.bangkok.go.th/bmatraffic/` สำรอง) ทุกรอบเช็คว่าส่งภาพใหม่หรือไม่ (`scan_status.source`: `ok` / `down` = ได้ภาพไม่ถึง 5% / `frozen` = ภาพเดิมซ้ำ) ถ้าล่ม หน้าเว็บขึ้นป้ายแดง ตัวเลขจราจรจากกล้อง กทม. ไม่นับเป็นข้อมูลสด และ push หัวข้อ "ระบบขัดข้อง" ถึงผู้ดูแล · รอบที่ `down` เรียก `bma_site.failover()` ย้ายไปที่อยู่แรกที่ `index.aspx` ตอบ (ใช้ร่วมกับ `bma_events.py`) |
| `backend/bma/bma_archive.py` | รอบนับอัตโนมัติ: สะสมยอดต่อกล้อง, รีเซ็ตทุกชั่วโมง, เขียน CSV รายวัน/สัปดาห์/เดือน/รายถนน ที่ `BMA_DATA_DIR` (ตั้งใน `.env` ตอนนี้ `E:\data smartstreet`), ข้อมูลเปรียบเทียบ |
| `backend/bma/bma_events.py` | ดึงรายงานสด (น้ำท่วม/อุบัติเหตุ) จากเว็บ BMA Traffic (`bma_site.base()`) ทุก 60 วินาที |
| `backend/water/water_service.py` | ระดับน้ำ/คลอง/น้ำทะเลหนุน/ฝน จาก thaiwater.net + คาดการณ์ (ทางการ 7 วัน หรือโมเดลในเครื่อง 48 ชม.) + หาคีย์ API ใหม่อัตโนมัติ |
| `backend/water/north_flow.py` | **น้ำเหนือ → ภาคกลาง** (แท็บ "น้ำเหนือ → ภาคกลาง" ในหน้า Water Forecast, `/api/water/north`): ปริมาณน้ำไหลผ่าน (ลบ.ม./วินาที) รายชั่วโมงของสถานีหลักกรมชลประทาน 17 สถานี ปิง วัง ยม น่าน → นครสวรรค์ (C.2) → ท้ายเขื่อนเจ้าพระยา (C.13) → สิงห์บุรี → อ่างทอง → อยุธยา (C.35) + สะแกกรัง ป่าสัก จาก ThaiWater เทียบ **ความจุลำน้ำ** (qmax) ของแต่ละสถานี (≥ 70% น้ำมาก, ≥ 100% ล้นตลิ่ง ตามเกณฑ์คลังข้อมูลน้ำ) + คาดการณ์ 4 วันด้วย flow routing: แต่ละช่วงแม่น้ำส่งการเปลี่ยนแปลงของน้ำต้นทางลงมาตามเวลาเดินทาง สัดส่วนและเวลาเดินทางปรับจากข้อมูล 14 วันล่าสุดทุกรอบ (ทดสอบย้อนหลัง ก.ย. 2569: คลาดเคลื่อน 4-6% ที่ 24 ชม., 8-12% ที่ 48 ชม.) + **ปริมาณน้ำทุก 10 นาที** (กรมชลฯ รายงานรายชั่วโมง จึงประมาณจากระดับน้ำ 10 นาทีของสถานี สสน. ใกล้เคียงภายใน 15 กม. ด้วย rating curve ที่ปรับทุก 6 ชม. ใช้เฉพาะคู่ที่ทดสอบย้อนหลัง 48 ชม. คลาดเคลื่อน ≤ 5% ตอนนี้ 11 จาก 17 จุด) ระบบดึงใหม่เองทุก 10 นาที + เขื่อนภูมิพล/สิริกิติ์/แควน้อย/ป่าสัก + คาดการณ์ระดับน้ำ 7 วันของ สสน. ที่นครสวรรค์ อยุธยา นนทบุรี → คำเตือนภาษาไทยรายสถานี ส่งต่อให้ AI สรุปสถานการณ์ (น้ำเหนือ) และ Ask AI ด้วย |
| `backend/agents/north_impact_agent.py` | **AI อธิบายน้ำเหนือแบบเข้าใจง่าย + ผลกระทบต่อเขตในกรุงเทพฯ + ถนนเสี่ยงน้ำท่วม** (สรุปง่าย ๆ 3-4 ข้อ, คำอธิบายรายจุดทุกสถานีจากค่า 10 นาที, รายเขต; ถนน: คัดจาก `road_service` ทุกสายด้วยทำเลเขต/อำเภอริมเจ้าพระยา ขอบเมืองด้านเหนือ จุดวัดน้ำท่วม กทม. บนถนน น้ำบนถนนตอนนี้ คลองข้างถนนเต็ม ฝน แล้วเรียก AI รอบที่ 2 เลือก 5-15 สายพร้อมเหตุผล ช่วงเวลา และคำแนะนำผู้ใช้ถนน ชื่อถนนต้องอยู่ในรายการที่คัดมา · นนทบุรีไม่มีเซ็นเซอร์บนถนน จึงประเมินจากทำเลเท่านั้น) (การ์ดในแท็บ "น้ำเหนือ → ภาคกลาง", `/api/water/north/impact`, สั่งรันใหม่ `POST /api/water/north/impact/run` เฉพาะ operator): รวมคาดการณ์น้ำเหนือ + สสน. คาดระดับน้ำ 7 วันที่สะพานนวลฉวี + น้ำทะเลหนุน + สถานีนนทบุรี/ปทุมธานี/นครปฐมที่ล้น + รายเขต 50 เขต (ทำเล: ริมเจ้าพระยา / ติดนนทบุรี-ปทุมธานี / ทุ่งตะวันออก / ฝั่งตะวันตก, คลอง-แม่น้ำในเขตเทียบตลิ่ง, น้ำบนถนน, ฝน 24 ชม.) ให้คะแนนตามเกณฑ์ แล้วให้ Qwen (`LOCAL_LLM_*`) เขียนว่าเขตไหนจะได้รับผลกระทบ เมื่อไร เพราะอะไร ควรทำอะไร วิเคราะห์ใหม่ทุก 30 นาที (`NORTH_IMPACT_SECONDS`; ตัวเลขน้ำบนหน้าเว็บยังอัปเดตทุก 10 นาที) เขตต้องอยู่ใน 50 เขตของ กทม. เท่านั้น ไม่มีโมเดลใช้รายงานตามเกณฑ์แทน |
| `backend/traffic/guidance_service.py` | คำแนะนำระบายรถรายเส้นทางหลัก 12 สาย ทุก 1 นาที จากเส้นสี Longdo (hotspots) + กล้อง กทม. + เหตุการณ์; Gemini เรียบเรียงข้อความทุก 5 นาที (`/api/traffic/guidance`) |
| `backend/water/flood_service.py` | จุดน้ำท่วมขังถนน กทม. ~250 จุด จากเซ็นเซอร์สำนักการระบายน้ำ (`weather.bangkok.go.th/flood`) ดึงทุก 5 นาที: ระดับน้ำเหนือผิวถนนหน่วย ซม. ต่อจุด + ถนน/เขต/พิกัด/เวลาเริ่มท่วม/สูงสุด เกณฑ์ตามเว็บต้นทาง (≤5 ปกติ, 5-10 เล็กน้อย, >10 ท่วม) เก็บประวัติในหน่วยความจำเพื่อบอกแนวโน้มขึ้น/ลงเทียบ 25 นาทีก่อน และให้ Gemini เขียนบทวิเคราะห์ (ระดับความรุนแรง จุดที่ต้องจับตา คำแนะนำ แนวโน้ม) ทุก 5 นาทีเมื่อสถานการณ์เปลี่ยน มี template ภาษาไทยสำรองเมื่อไม่มี key (`/api/flood/status|stations|roads|analysis`) — เฉพาะ กทม. 50 เขต ปริมณฑลไม่มีเซ็นเซอร์สาธารณะ |
| `backend/traffic/road_service.py` | ประเมินความเสี่ยงน้ำท่วมขัง **รายถนน** ทั้ง กทม. และปริมณฑล ทุก 2 นาที: รวมถนนทุกสายจาก `traffic_service` (ชื่อ+จุดกึ่งกลาง+% รถติด) เข้ากับเซ็นเซอร์น้ำบนถนน (`flood_service`, เฉพาะ กทม.), สถานีวัดฝน 24 ชม. ~180 จุด และสถานีระดับน้ำคลอง/แม่น้ำ ~70 จุด (`water_service`) ด้วยระยะทางจริง แล้วจัดระดับตาม **เกณฑ์ทางการ** (น้ำบนถนน: สนน. กทม. 5/10 ซม. + ปภ. 20/60/80 ซม. · ฝน 24 ชม.: กรมอุตุนิยมวิทยา 10/35/90 มม. · ระดับตลิ่ง: คลังข้อมูลน้ำแห่งชาติ 80%/100%) + Gemini เขียนบทวิเคราะห์สายที่เสี่ยงสุด · สายที่ไม่มีเซ็นเซอร์บนถนนจะทำเครื่องหมาย `measured: false` (`/api/roads/risk`) |
| `backend/water/air_service.py` | PM2.5 / AQI รายสถานีจาก Air4Thai ทุก 10 นาที (`/api/air/stations`) |
| `backend/vision/flood_cam_service.py` | AI ดูน้ำท่วมจากภาพกล้อง กทม. ทุกตัว: รับภาพดิบจากรอบสแกน (และกล้อง iTIC จาก `itic_frames.py`) → รวม 9 กล้องเป็นภาพตาราง 3×3 ถาม Qwen vision (`LOCAL_LLM_*`) ครั้งเดียว (~5 วิ) → ช่องที่ดูเหมือนมีน้ำถามซ้ำทีละภาพเพื่อยืนยันก่อนขึ้นแผนที่ ระดับ: ไม่ท่วม / น้ำขังเล็กน้อย / น้ำท่วมผิวจราจร / น้ำท่วมหนัก / มองไม่ชัด กล้องแห้งตรวจซ้ำทุก 10 นาที กล้องที่มีน้ำทุก 5 นาที ภาพค้าง (feed ไม่ขยับ) ไม่ถามซ้ำ ผลเก็บที่ `cache/flood_cams.json` + ภาพที่ใช้ตัดสินใน `cache/flood_cams/` (`/api/flood/cameras*`, ชั้น "กล้องเห็นน้ำท่วม (AI)" ในหน้า Traffic Map) |
| `backend/vision/itic_frames.py` + `ts_decode.py` | ภาพจากกล้อง iTIC (หมุด CCTV บนแผนที่ จากรายการ Longdo) ให้ AI ดูน้ำท่วม: ลิงก์ JPEG ของ iTIC (`camera1.iticfoundation.org`) ใช้ไม่ได้ จึงดึง segment ล่าสุดของ HLS ทุก 5 นาที แล้วถอดเฟรมแรกใน process แยก (`ts_decode.py`) ไม่ถอดใน server เพราะ FFmpeg เคยทำ server ล่มกับ stream ที่เสีย ค่าเริ่มต้นเฉพาะกรุงเทพฯ-ปริมณฑล ~35 ตัว (`FLOOD_CAM_ITIC_PROVINCES`) |
| `backend/water/user_reports.py` | ประชาชนแจ้งน้ำท่วม (หมุด ระดับน้ำ รูป 1 รูป ข้อความสั้น) จากหน้า "แจ้งน้ำท่วม" (`#/report`, ปุ่มกลางแถบเมนูล่างบนมือถือ และปุ่มบนสุดของเมนูซ้าย): รูปถูกย่อและบันทึกใหม่เป็น JPEG ไม่มี EXIF/GPS → Qwen vision ตรวจว่าเป็นรูปน้ำท่วมจริงและเหมาะสม → ขึ้นแผนที่ 6 ชม. ในชื่อ "ประชาชนแจ้ง ยังไม่ยืนยัน" (ไม่ผ่านถูกปฏิเสธและลบรูป, AI ไม่ตอบรอคิวลองใหม่ทุก 60 วิ) `POST /api/flood/user-reports` เป็นช่องเขียนสาธารณะช่องเดียว จำกัดขนาดและจำนวนต่อ IP ใน `access_guard.py` ส่วนการลบ (`DELETE`) เฉพาะ operator |
| `backend/vision/helmet_service.py` | ตรวจหมวกกันน็อกทุกกล้อง กทม.: crop มอไซจากรอบสแกน → โมเดลในเครื่อง (`HELMET_DET`, ค่าปัจจุบัน `helmet_det_blur.pt`) คัดกรอง → AI agent (Qwen ตาม `HELMET_AGENT=qwen` หรือ Gemini/Claude) ยืนยัน (ถ้า AI ไม่ได้ตรวจ ภาพที่โมเดลในเครื่องว่าไม่ใส่หมวกจะเป็น "รอตรวจ" และถามใหม่ทุก 5 นาที) → ผู้ไม่สวมหมวกเก็บภาพ+CSV ที่ `BMA_DATA_DIR\helmet\` (`/api/helmet/*`) |
| `backend/vision/wrongway_service.py` | ตรวจรถย้อนศรทุกกล้อง กทม. จากภาพนิ่ง: กรอบรถจาก yolo26x ตัวเดียวกับที่นับรถ → โมเดลจำแนกทิศ `wrongway_cls.pt` (YOLO26s-cls, `toward` เห็นหน้ารถ / `away` เห็นท้ายรถ) อ่านรถทีละคัน (ไม่มีไฟล์นี้จะใช้ `wrongway_det.pt` ตัวเก่าที่หารถไม่ค่อยเจอ) → กล้องแต่ละตัวเรียนรู้ทิศปกติต่อช่องกริด 12×9 (`cache/heading/`) → รถที่หันสวนช่องที่รู้ทิศแล้วส่ง AI agent (Gemini) ยืนยัน จากภาพที่มีแค่กรอบแดง ไม่มีลูกศรและไม่บอกคำตอบของโมเดล (ถ้า AI ไม่ได้ตรวจ จะเป็น "รอตรวจ" และถามใหม่ทุก 5 นาที โมเดลในเครื่องอย่างเดียวไม่ตัดสินว่าย้อนศร) → หลักฐาน+CSV ที่ `BMA_DATA_DIR\wrongway\` (`/api/wrongway/*`) |
| `local/pipeline/collect_wrongway_dataset.py`, `train_wrongway_det.py`, `wrongway_pipeline.bat`, `wrongway_status.bat` | dataset ทิศทางรถแบบไม่ต้อง label มือ: เก็บ burst จากทุกกล้อง (BMA ~1 เฟรม/วิ + HLS) ติดตามรถ ทิศจากการเคลื่อนที่ (รถจอดใช้แผนที่ทิศของกล้อง) → fine-tune `yolo26x.pt` เป็น `wrongway_det.pt`; `wrongway_pipeline.bat [รอบ] [นาทีห่าง] [epochs] [batch]` ทำครบทั้งสองขั้น + หน้าต่างสถานะ |
| `local/pipeline/prep_wrongway_cls.py`, `train_wrongway_cls.py` | ตัดกรอบ `toward/away` จาก `dataset_wrongway` เป็นภาพครอป (`local/dataset_wrongway_cls/`) → เทรน `yolo26s-cls` 128 px (`--clean` ย้ายภาพที่ label น่าจะผิดไป `rejected/` แล้วเทรนซ้ำ) → `wrongway_cls.pt`; รันข้างเซิร์ฟเวอร์ได้ ใช้ GPU ~1-2 GB |
| `backend/water/river_roads.py` + `config/chao_phraya.json` + `config/nonthaburi_areas.json` | **นนทบุรี: ถนนทุกสาย ช่วงไหนท่วมก่อน + โอกาสน้ำท่วม** (`/api/water/north/nonthaburi`): แนวกลางแม่น้ำเจ้าพระยาและเขตจังหวัด/อำเภอ/ตำบลนนทบุรีจาก OpenStreetMap (ODbL, สร้างใหม่ด้วย `local/pipeline/fetch_river_areas.py`) × ถนนทุกเส้นใน road index ของ Longdo ที่อยู่ในนนทบุรี (~160 สาย) ตัดเป็นช่วงละ ~330 ม. แต่ละช่วงมีระยะห่างจากแม่น้ำ ตำบล/อำเภอ และถนนที่ตัดผ่าน เรียงช่วงเสี่ยงที่สุด → รองลงมา · AI เรียกรอบที่ 3 อธิบายแต่ละสาย · โอกาสน้ำสูงกว่าตลิ่งรายวันที่สะพานนวลฉวี = 1 − Φ((ตลิ่ง − ระดับสูงสุดที่ สสน. คาด)/σ) โดย σ มาจากประวัติคาดการณ์ สสน. ที่ระบบเก็บเอง (`cache/hii_1132_forecasts.json`, ใช้เมื่อครบ 5 ค่าต่อช่วงล่วงหน้า) ไม่งั้นใช้การเปลี่ยนแปลงของระดับน้ำสูงสุดรายวันจริง 30 วัน · ภาพรวม 7 วัน = วันที่โอกาสสูงสุด · ถนน = โอกาส × น้ำหนักระยะ (≤200 ม. 1, ≤500 ม. 0.6, ≤1 กม. 0.3, ≤2 กม. 0.1 เป็นสมมติฐาน) ส่งต่อให้ AI อธิบายด้วย |
| `backend/core/local_llm.py` | ไคลเอนต์ AI (OpenAI-compatible, `LOCAL_LLM_*`) ที่ทุกงานใช้ร่วมกัน จำกัด 3 คำขอพร้อมกันต่อ key และ **นับ token ทุกคำขอแยกตามโมดูลที่เรียก** (จาก `usage` ที่ gateway ส่งกลับ เก็บ 24 ชม.) ดูได้ที่ `GET /api/ai/usage?minutes=30` (เฉพาะ LAN/operator) |
| `backend/core/access_guard.py` | ป้องกันเมื่อเปิดสาธารณะผ่าน Cloudflare Tunnel: POST ควบคุมทำได้จาก LAN/tailnet หรือ `X-Admin-Token`; `/api/chat` จำกัดต่อ IP (IP จริงจาก `CF-Connecting-IP` บนการเชื่อมต่อทาง `127.0.0.2`) |
| `local/pipeline/backup_db.py` (`backup_db.bat`) | งานกลางคืน: ลบ `bma_history`/`samples` เกิน 90 วัน, VACUUM, สำเนา DB + CSV + .env ไป `BMA_DATA_DIR\backup\` (ลงทะเบียน Task Scheduler 03:30 แล้ว) |
| `local/pipeline/watchdog.bat` | ping `/api/health` ทุก 1 นาที ล้ม 3 ครั้งติดจึงรัน `launch\production\restart.bat` |
| `local/pipeline/prep_helmet_det.py`, `train_helmet_det.py`, `watch_train.*` | dataset Kaggle helmet-detection → YOLO format → fine-tune `yolo26x.pt` เป็น `helmet_det.pt` (helmet / no_helmet) + หน้าต่าง % ความคืบหน้า |
| `local/pipeline/` (`collect_dataset.py`, `relabel_dataset.py`, `clean_dataset.py`, `train_model.py`, `pipeline_status.py`, `*.bat`) | pipeline เก็บภาพ-ทำ label (tiled 2×2 + เกณฑ์ conf รายคลาส)-เทรน YOLO (oversample เฟรมที่มีมอเตอร์ไซค์ `--moto-boost`) ให้เข้ากับกล้องไทย |
| `backend/traffic/rsc_service.py` | สถิติอุบัติเหตุ Thai RSC รายเขต + จุดเสี่ยงรอบกล้อง BMA (`/api/rsc/*`) |
| `backend/vision/violation_service.py` | จับผิดกฎจราจรจากกล้อง AI สด: ย้อนศร (เรียนรู้ทิศทางจราจรต่อกล้องเอง) และไม่สวมหมวกกันน็อก (โมเดล `helmet_cls.pt` ถ้ามี ไม่งั้นใช้ vision API) → `/api/ai/violations` สำเนาภาพลง `BMA_DATA_DIR\violations` |
| `local/pipeline/collect_helmet_dataset.py`, `local/pipeline/train_helmet.py` | สร้างชุดข้อมูล crop ผู้ขี่ (label โดย vision API) แล้วเทรน YOLO11 classifier หมวก/ไม่หมวก → `helmet_cls.pt` |
| `local/pipeline/qwen_label.py`, `label_review.py`, `train_from_labels.py` | เทรนโมเดลย้อนศร/หมวกใหม่จากภาพจริงของกล้อง กทม.: Qwen ติดป้ายหน้ารถ/ท้ายรถ (`local/labels/heading_qwen.jsonl`) → หน้าตรวจป้ายในเครื่อง http://127.0.0.1:8010 (ชุดทดสอบไม่แสดงคำตอบของ AI, หมวกให้คนติดป้ายเองเพราะ Qwen ดูหมวกบนภาพเล็กผิดบ่อย) → เทรน yolo26s-cls และวัดผลเทียบตัวเดิมบนชุดทดสอบ ไม่เขียนทับโมเดลที่ใช้งานอยู่ |
| `local/pipeline/prefetch_tiles.py` | ดาวน์โหลด tile แผนที่ไว้ใช้ออฟไลน์ (รันครั้งเดียว) |

### Frontend (`web/src`, React + Tailwind v4)
| ไฟล์ | หน้าที่ |
|---|---|
| `App.jsx` | เลย์เอาต์หลัก (Sidebar ซ้าย + เนื้อหา), routing ด้วย hash, state กล้องที่เปิด, toast, poll เหตุการณ์ |
| `components/Sidebar.jsx` | เมนูซ้าย (กลุ่มหน้า), ชื่อผู้ใช้, สถานะกล้อง, สลับธีม สว่าง/มืด/ตามเครื่อง |
| `components/dashboard/ui.jsx` | ชิ้นส่วนพื้นฐาน: Card, Badge, Button, Segmented, Skeleton, EmptyState, ErrorState |
| `components/dashboard/primitives.jsx` | ชิ้นส่วนระดับหน้า: PageHeader, StatTile, StatusBanner, Tabs, Modal, ShareBar |
| `components/dashboard/format.js` | ฟอร์แมตเวลา/ตัวเลข/สีสถานะ |
| `components/DashboardPage.jsx` + `dashboard/*` | แดชบอร์ดจราจร 4 แท็บ: ภาพรวมจราจร, **วิเคราะห์รายถนน** (`dashboard/RoadRiskPanel.jsx`), เหตุการณ์สด, รายงานสดจากศูนย์ |
| `components/CameraWall.jsx`, `CityWindow.jsx`, `VideoSlot.jsx` | หน้า "ดูกล้องสด": กล้อง iTIC (วิดีโอสด) และกล้อง กทม. (ภาพนิ่ง) ทุกตัว |
| `components/BmaCountPage.jsx` + `bma/*` | นับรถจากกล้อง กทม.: ภาพรวมตอนนี้, เทียบวัน/สัปดาห์/เดือน, กล้องทุกตัว + สตรีม YOLO |
| `components/HelmetPage.jsx`, `components/WrongWayPage.jsx` | ตรวจหมวกกันน็อก / ตรวจรถย้อนศร จากกล้อง กทม. ทุกตัว: หลักฐาน, รถที่สงสัย (สั่งตรวจซ้ำด้วยโมเดลในเครื่องหรือ AI), กล้องทุกตัว + ตรวจตอนนี้ |
| `components/AnalyticsPage.jsx` | วิเคราะห์เมือง: ดัชนีความแออัด ความหนาแน่นถนน คาดการณ์น้ำท่วม 1-6 ชม. จุดเสี่ยงอุบัติเหตุ ผู้เข้าชม + export CSV/JSON |
| `components/CameraAiPage.jsx` | หน้า "กล้อง AI": รวมแท็บกล้องสด / AI ตรวจจับ / นับรถกล้อง กทม. |
| `components/YoloPage.jsx` | AI ตรวจจับรถสดจากกล้องเดียว ปรับ FPS/ความมั่นใจ |
| `components/MapPage.jsx` | แผนที่ MapLibre: เส้นจราจร, หมุดกล้อง, เหตุการณ์, เรดาร์ฝน, PM2.5, ลม, อาคาร 3D/ผังอาคาร+ชื่อสถานที่, **น้ำท่วมขังถนน กทม.** (ป้ายความลึก ซม. จากเซ็นเซอร์ สนน.) และ **ระดับน้ำแม่น้ำ/คลองปริมณฑล** (% ความจุตลิ่ง จากคลังข้อมูลน้ำแห่งชาติ ครอบคลุม กทม. นนทบุรี ปทุมธานี สมุทรปราการ นครปฐม สมุทรสาคร) |
| `components/WaterPage.jsx` + `water/*` | คาดการณ์น้ำ: กราฟรายสถานี, ตารางสถานี, น้ำทะเลหนุน, คลอง/ถนน, ฝน, รายงานสด กทม., น้ำเหนือ → ภาคกลาง (`water/NorthFlowSection.jsx`, 2 มุมมอง: **สรุปง่าย** ค่าเริ่มต้นสำหรับคนทั่วไป `water/NorthFlowSimple.jsx` = หัวข้อ+สรุปจาก AI, แผนที่น้ำไหล, เส้นทางน้ำ 6 จุด นครสวรรค์ → นนทบุรี-กทม. (เต็มลำน้ำกี่ % กำลังขึ้น/ลง จะขึ้นถึงเท่าไร), เขตที่ควรเตรียมตัว, ควรทำอะไร, แม่น้ำเหนือสายละบรรทัด, แผนที่ · **ข้อมูลละเอียด** = อธิบายศัพท์ + ตารางปริมาณน้ำทุก 10 นาที `water/NorthFlowExplain.jsx`, คำเตือน, AI ผลกระทบรายเขต กทม. `water/NorthImpactCard.jsx`, แผนที่ลูกศรทิศทางน้ำ `water/NorthFlowMap.jsx` เส้นหนาตามปริมาณน้ำ สีตามสถานะตอนนี้/คาดสูงสุด, เส้นทางน้ำ นครสวรรค์ → อยุธยา, กราฟปริมาณน้ำวัดได้ 72 ชม. + คาดการณ์ 4 วัน) |
| `components/AiPage.jsx` | แชทถาม AI เรื่องเส้นทาง พร้อมกล้อง AI ประกอบ |
| `lib/api.js` | ฟังก์ชันเรียก REST API ทั้งหมด |
| `lib/store.js` | localStorage: กล้องโปรด, กล้องที่เปิด, ชื่อผู้ใช้, ธีม |
| `index.css` | โทเค็นสี/ฟอนต์ Prompt, ธีมมืด (remap ตัวแปรสีภายใต้ `.dark`) |

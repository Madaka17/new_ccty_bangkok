# กล้องจราจร กรุงเทพฯ และ ปริมณฑล + ระบบ AI ตรวจจับรถยนต์ (YOLO11x)

เว็บแอปพลิเคชันระบบกล้องวงจรปิด (CCTV) ตรวจสอบสภาพจราจรแบบเรียลไทม์ ครอบคลุม **กรุงเทพมหานคร และ ปริมณฑล** (66 กล้อง) พร้อมติดตั้งระบบปัญญาประดิษฐ์ **YOLO11x (Ultralytics)** สำหรับตรวจจับ นับจำนวน และจำแนกประเภทยานพาหนะแบบสด โดยปรับความเร็วในการประมวลผลไว้ที่ **~5 FPS** เพื่อความเสถียรและแม่นยำสูงสุด

---

## 🤖 ฟังก์ชันระบบ AI ตรวจจับยานพาหนะ (YOLO11x)
- **โมเดลที่ใช้**: `YOLO11x` (โมเดลขนาดใหญ่สุด Extra-Large ที่มีความแม่นยำสูงสุดในตระกูล YOLOv11)
- **อัตราการประมวลผล (Target Frame Rate)**: **~5 FPS** (ประมาณ 1 เฟรม ทุกๆ 0.2 วินาที) ช่วยให้โมเดลขนาดใหญ่ประมวลผลได้ไหลลื่น ภาพไม่หน่วง และไม่กินพลังงาน GPU สูงเกินไป
- **การจำแนกประเภทยานพาหนะ**:
  1. 🚗 **รถยนต์ (Cars)**: สีฟ้า/น้ำเงินนีออน พร้อมกรอบและข้อความเปอร์เซ็นต์ความมั่นใจ
  2. 🏍️ **มอไซ (Motorcycles)**: สีส้ม/เหลืองทอง พร้อมกรอบและข้อความเปอร์เซ็นต์ความมั่นใจ
  3. 🚚 **รถบรรทุก (Trucks / Buses)**: สีแดงส้ม พร้อมกรอบและข้อความเปอร์เซ็นต์ความมั่นใจ
- **การนับและประเมินสภาพจราจรแบบเรียลไทม์**:
  - แสดงตัวเลขดิจิทัลนับแยกตามประเภทแบบสดๆ
  - ประเมินสถานะการจราจร: `🟢 คล่องตัว` / `🟡 ปานกลาง` / `🔴 หนาแน่น`
  - รองรับการเปิดดูกล้อง CCTV ใดก็ได้จากทั้ง 66 ตัวในกรุงเทพฯ และปริมณฑล
- **เปลี่ยนโมเดลได้ผ่าน `.env`**: `AI_MODEL=yolo26x.pt` (YOLO26x: mAP 57.5 vs YOLO11x 54.7, NMS-free, เร็วกว่าเล็กน้อย — ทดสอบบน RTX 3080 FP16 ได้ ~36 ms/เฟรม) ไฟล์ `.pt` ดาวน์โหลดอัตโนมัติถ้ายังไม่มี
- **ติดตั้ง PyTorch แบบ CUDA** (ถ้า `torch.cuda.is_available()` เป็น False ระบบจะตกไปใช้ CPU ช้ากว่า ~30 เท่า):

```bash
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130 --force-reinstall --no-deps
```

- **รองรับ GPU Acceleration**: ใช้งาน PyTorch CUDA 12.4 บนการ์ดจอ **NVIDIA GeForce RTX 3050** ความเร็ว Latency เพียง ~65 ms ต่อเฟรม!

---

## 🌸 หน้าเว็บใหม่ (React + Tailwind + framer-motion)

โค้ดหน้าเว็บโฉมใหม่อยู่ในโฟลเดอร์ `web/` เมื่อ build แล้ว `server.py` จะเสิร์ฟหน้าใหม่จาก `web/dist` โดยอัตโนมัติ (ถ้ายังไม่ได้ build จะใช้หน้าเดิมจาก `local/legacy_ui/`)

```bash
cd web
npm install
npm run build      # สร้าง web/dist แล้วเปิด run_server.bat ตามปกติ
npm run dev        # โหมดพัฒนา ที่ http://localhost:5173 (proxy /api ไป :8000)
```

---

## 🗺️ แผนที่จราจร / 🤖 AI ผู้ช่วยการจราจร / 📊 แดชบอร์ด

หน้าเว็บมี 4 หน้า: **แดชบอร์ด**, **กล้อง**, **แผนที่จราจร**, **AI ผู้ช่วยการจราจร**

- **เส้นจราจร (เขียว/เหลือง/แดง)** ดึงจาก Longdo Traffic vector tiles (`msv.longdo.com/maps/traffic`) ผ่านเซิร์ฟเวอร์ของเราที่แคชไว้ในโฟลเดอร์ `cache/` ถ้าเน็ตหลุดจะแสดงข้อมูลล่าสุดที่บันทึกไว้
- **แผนที่ออฟไลน์**: แผนที่พื้นฐาน (OpenStreetMap) จะถูกเก็บลงเครื่องอัตโนมัติเมื่อเปิดดู หรือดาวน์โหลดล่วงหน้าทั้งกรุงเทพฯ ด้วย

```bash
.venv\Scripts\python local\pipeline\prefetch_tiles.py
```

- **AI ผู้ช่วยการจราจร** วิเคราะห์การระบายรถรายถนนจากเส้นจราจรทุกสาย (จับคู่ชื่อถนนจาก Longdo base map) ใช้ **Gemini Flash-Lite** เมื่อใส่ key ในไฟล์ `.env` (สร้าง key ฟรีที่ https://aistudio.google.com/apikey):

```
GEMINI_API_KEY=AIza...
# ไม่บังคับ: เปลี่ยนรุ่น (ค่าเริ่มต้น gemini-2.5-flash-lite)
GEMINI_MODEL=gemini-2.5-flash-lite
# โมเดล vision สำหรับตรวจภาพ (อุบัติเหตุ/หมวก) ใช้รุ่น lite ที่ไม่ใช่ thinking จะเร็วกว่ามาก (2-6 วิ/ภาพ)
GEMINI_VISION_MODEL=gemini-3.5-flash-lite
# ตรวจหมวก: จำกัดการเรียก API ต่อชั่วโมง, โมเดลแยก, AI ในเครื่อง (LOCAL_VLM=0 ปิด)
HELMET_PATROL_MAX_PER_HOUR=240
HELMET_AGENT_MODEL=gemini-3.1-flash-lite
LOCAL_VLM=Qwen/Qwen2-VL-2B-Instruct
# ป้องกันสาธารณะ: ตั้งแล้วส่ง header X-Admin-Token เพื่อกดปุ่มควบคุมจากนอก LAN
ADMIN_TOKEN=
# โฟลเดอร์เก็บ CSV รอบนับกล้อง กทม. + ภาพหลักฐานฝ่าฝืน (ค่าเริ่มต้น D:\Data)
BMA_DATA_DIR=E:\data smartstreet
```

ลำดับผู้ให้บริการ: Gemini (`GEMINI_API_KEY`) → Claude (`ANTHROPIC_API_KEY`) → โหมดออฟไลน์ (สรุปจากข้อมูลสด ไม่ต้องใช้ key)

### 🌐 เปิดให้คนอื่นดูผ่าน Tailscale

รันครั้งเดียวในเครื่องนี้ (Funnel เดิมชี้ไปพอร์ต 3000 ต้องรีเซ็ตก่อน):

```bash
tailscale funnel reset
tailscale funnel --bg 8000        # เปิดสู่อินเทอร์เน็ต ทุกคนที่มีลิงก์เข้าดูได้
# หรือเฉพาะคนใน tailnet เดียวกัน:
tailscale serve --bg 8000
```

ลิงก์: https://cctv-bangkok.tail95e28b.ts.net

ทางลัด (ดับเบิลคลิก):
- `run_public.bat` เปิด Funnel + รันเซิร์ฟเวอร์
- `restart_public.bat` ปิดเซิร์ฟเวอร์เดิมที่พอร์ต 8000 แล้วเปิดใหม่พร้อม Funnel (ใช้หลังแก้ `.env` หรือโค้ด)
- `stop_public.bat` ปิด Funnel (เซิร์ฟเวอร์ยังรันอยู่)

- API: `GET /api/traffic/summary`, `GET /api/traffic/roads?q=`, `POST /api/chat`, tiles ที่ `/api/traffic/tile/{z}/{x}/{y}.pbf` และ `/api/tiles/base/{z}/{x}/{y}.png`

#### 🔒 การป้องกันเมื่อเปิดสาธารณะ (`access_guard.py`)

เปิดใช้อัตโนมัติ ไม่ต้องตั้งค่าเพิ่ม:

- **endpoint ควบคุม** (POST/PUT/DELETE เช่น เปลี่ยนกล้อง, ตั้ง FPS, สแกน BMA, ลบผลตรวจ) ใช้ได้เฉพาะ localhost / LAN / tailnet หรือส่ง header `X-Admin-Token` ให้ตรงกับ `ADMIN_TOKEN` ใน `.env` — คนนอกได้ `403`
- **`/api/chat`** (ใช้ key Gemini/Claude) จำกัดต่อ IP ค่าเริ่มต้น 6 ครั้ง/นาที, 60 ครั้ง/วัน, body ไม่เกิน 8000 bytes — เกินได้ `429` / `413`
- request ทั่วไปจากคนนอกจำกัด 600 ครั้ง/นาที ต่อ IP

ปรับได้ใน `.env`:

```
ADMIN_TOKEN=รหัสลับสำหรับสั่งงานจากข้างนอก
CHAT_RATE_PER_MIN=6
CHAT_RATE_PER_DAY=60
CHAT_MAX_BODY=8000
GENERAL_RATE_PER_MIN=600
```

หมายเหตุ: endpoint เส้นจราจรของ Longdo เป็นการใช้งานแบบไม่เป็นทางการ อาจเปลี่ยนหรือต้องใช้ key ในอนาคต

---

## 📍 ขอบเขตพื้นที่กล้อง (กรุงเทพฯ และ ปริมณฑล 66 กล้อง)
1. **กรุงเทพมหานคร (Bangkok)** - 32 กล้อง
2. **นนทบุรี (Nonthaburi)** - 24 กล้อง
3. **นครปฐม (Nakhon Pathom)** - 6 กล้อง
4. **สมุทรปราการ (Samut Prakan)** - 3 กล้อง
5. **ปทุมธานี (Pathum Thani)** - 1 กล้อง

---

## 🚀 วิธีเปิดใช้งาน
1. ดับเบิลคลิกที่ไฟล์ [**`run_server.bat`**](file:///C:/Users/Mrsun/OneDrive/Desktop/New_CCTV/run_server.bat)
2. ระบบจะเปิดเซิร์ฟเวอร์ FastAPI พร้อมโหลดโมเดล YOLO11x บน GPU
3. หน้าเว็บจะเปิดขึ้นมาที่ `http://localhost:8000` โดยอัตโนมัติ
4. กดที่ปุ่ม **"🤖 AI ตรวจจับรถ (YOLO11x)"** ที่แถบเมนูด้านบน หรือกดไอคอนหุ่นยนต์บนหน้าต่างกล้องใดๆ เพื่อเปิดหน้าต่างวิเคราะห์การจราจรสด

## 📁 โครงสร้างโฟลเดอร์ (อะไรขึ้น Tailscale / อะไรใช้แค่ในเครื่อง)

`tailscale funnel 8000` เปิดเฉพาะ `server.py` ดังนั้น **ทุกอย่างที่ root คือชุดที่เซิร์ฟเวอร์ต้องใช้** ส่วน `local/` คือของที่ใช้แค่ในเครื่องนี้ (เทรนโมเดล, เก็บ dataset, ของเก่า) ไม่ต้องคัดลอกไปเครื่องอื่น

```
D:\New_CCTV\
├── server.py, *_service.py, yolo_detector.py,      ← 🌐 เซิร์ฟเวอร์ (Tailscale) — โค้ด backend
│   vehicle_log.py, count_workers.py, survey.py,
│   bma_*.py, telemetry_service.py
├── cameras_bkk.json, cameras_bma.json               ← 🌐 ข้อมูลกล้อง
├── yolo26x.pt (+ yolo26l/m), *_bkk.pt, helmet_cls.pt ← 🌐 โมเดล (gitignore, ต้องคัดลอกเอง)
├── web/  (src/ = ซอร์ส React, dist/ = ที่เซิร์ฟจริง)  ← 🌐 หน้าเว็บ (build ด้วย npm run build)
├── run_server.bat, requirements.txt, .env           ← 🌐 ตัวรัน + config (.env ห้าม commit)
├── cache/, vehicle_counts.db, count_cameras.json    ← 🌐 ข้อมูล runtime (สร้างเองอัตโนมัติ)
│
└── local/                                            ← 💻 ใช้ในเครื่องเท่านั้น
    ├── pipeline/   สคริปต์เก็บภาพ/label/เทรน + .bat/.sh ทั้งหมด (pipeline.bat, collect.bat, status.bat ...)
    ├── dataset/, dataset_helmet/, runs/, pipeline.log   ข้อมูลเทรนและผลลัพธ์ (gitignore)
    ├── legacy_ui/  หน้าเว็บเก่า (index.html, app.js, style.css, cameras_data.js) ใช้เป็น fallback เมื่อไม่มี web/dist
    ├── scratch/    ไฟล์ทดลอง
    └── archive/    ของเก่า/สำรอง (new_ccty_bangkok, cameras_bkk_backup_itic.json, yolo11x_bkk.pt.bad, test_*.jpg)
```

- ไฟล์ `.bat` ใน `local/pipeline/` ดับเบิลคลิกได้เหมือนเดิม (สคริปต์ `cd` กลับไป root เอง) ผลลัพธ์โมเดล `*_bkk.pt` / `helmet_cls.pt` ยังถูกเขียนลง root ให้เซิร์ฟเวอร์หยิบใช้
- เซิร์ฟเวอร์เสิร์ฟไฟล์ static จาก `web/dist` เท่านั้น (ไม่เสิร์ฟ root ทั้งโฟลเดอร์แล้ว) `.env`, `*.db`, `*.py` จึงไม่หลุดออก Tailscale

---

## แผนผังโค้ด (Code map)

### Backend (Python, FastAPI)
| ไฟล์ | หน้าที่ |
|---|---|
| `server.py` | จุดเริ่มต้น: โหลดกล้อง, สร้าง detector/scanner/services, ประกาศ REST API ทั้งหมด, เสิร์ฟ `web/dist` |
| `yolo_detector.py` | YOLO11x + ByteTrack บนสตรีมกล้องเดียว (หน้า AI ตรวจจับรถสด), นับรถผ่าน, ประเมินระดับจราจร, ตรวจรถจอดนิ่ง/ชน |
| `count_workers.py` | นับรถต่อเนื่องหลายกล้องในพื้นหลัง (แดชบอร์ด "จำนวนรถที่ผ่านกล้อง AI") |
| `survey.py` | วนสำรวจทุกกล้องสั้น ๆ เพื่อให้ป้ายระดับ โล่ง/ปานกลาง/ติดขัด ในหน้ากล้อง |
| `vehicle_log.py` | SQLite `vehicle_counts.db`: ยอดรายชั่วโมง, sample จาก survey, เหตุการณ์จากกล้อง |
| `incident_service.py` | รวมเหตุการณ์: กล้อง AI (ยืนยันด้วย Claude vision) + รายงาน Longdo |
| `traffic_service.py` | ดึง tile จราจร Longdo, สรุปการระบายรถรายถนน, proxy tile แผนที่ |
| `chat_service.py` | หน้า "ถาม AI เรื่องเส้นทาง": ส่งสรุปจราจร + กล้องให้ Claude ตอบ |
| `bma_service.py` | สแกนกล้อง กทม. 574 ตัว (snapshot ทุก ~4 นาที) นับรถด้วย YOLO, เก็บ `bma_latest`/`bma_history`, สตรีม MJPEG |
| `bma_archive.py` | รอบนับอัตโนมัติ: สะสมยอดต่อกล้อง, รีเซ็ตทุกชั่วโมง, เขียน CSV รายวัน/สัปดาห์/เดือน/รายถนน ที่ `BMA_DATA_DIR` (ตั้งใน `.env` ตอนนี้ `E:\data smartstreet`), ข้อมูลเปรียบเทียบ |
| `bma_events.py` | ดึงรายงานสด (น้ำท่วม/อุบัติเหตุ) จาก cpudapp.bangkok.go.th ทุก 60 วินาที |
| `water_service.py` | ระดับน้ำ/คลอง/น้ำทะเลหนุน/ฝน จาก thaiwater.net + คาดการณ์ (ทางการ 7 วัน หรือโมเดลในเครื่อง 48 ชม.) + หาคีย์ API ใหม่อัตโนมัติ |
| `guidance_service.py` | คำแนะนำระบายรถรายเส้นทางหลัก 12 สาย ทุก 1 นาที จากเส้นสี Longdo (hotspots) + กล้อง กทม. + เหตุการณ์; Gemini เรียบเรียงข้อความทุก 5 นาที (`/api/traffic/guidance`) |
| `air_service.py` | PM2.5 / AQI รายสถานีจาก Air4Thai ทุก 10 นาที (`/api/air/stations`) |
| `helmet_service.py` | ตรวจหมวกกันน็อกทุกกล้อง กทม.: crop มอไซจากรอบสแกน → AI agent (Gemini/Claude หรือ `helmet_det.pt` ในเครื่อง) → ผู้ไม่สวมหมวกเก็บภาพ+CSV ที่ `BMA_DATA_DIR\helmet\` (`/api/helmet/*`) |
| `local_vision.py` | AI agent ตัวที่ 2 ในเครื่อง (Qwen2-VL-2B บน GPU, ไม่ใช้ key) ใช้แทนเมื่อ Gemini หมดเครดิต/โควตา และให้ความเห็นซ้ำจากหน้าเว็บ |
| `access_guard.py` | ป้องกันเมื่อเปิด Funnel สาธารณะ: POST ควบคุมทำได้จาก LAN/tailnet หรือ `X-Admin-Token`; `/api/chat` จำกัดต่อ IP |
| `local/pipeline/backup_db.py` (`backup_db.bat`) | งานกลางคืน: ลบ `bma_history`/`samples` เกิน 90 วัน, VACUUM, สำเนา DB + CSV + .env ไป `BMA_DATA_DIRackup\` (ลงทะเบียน Task Scheduler 03:30 แล้ว) |
| `local/pipeline/watchdog.bat` | ping `/api/health` ทุก 1 นาที ล้ม 3 ครั้งติดจึงรัน `restart_public.bat` |
| `local/pipeline/prep_helmet_det.py`, `train_helmet_det.py`, `watch_train.*` | dataset Kaggle helmet-detection → YOLO format → fine-tune `yolo26x.pt` เป็น `helmet_det.pt` (helmet / no_helmet) + หน้าต่าง % ความคืบหน้า |
| `local/pipeline/` (`collect_dataset.py`, `relabel_dataset.py`, `clean_dataset.py`, `train_model.py`, `pipeline_status.py`, `*.bat`) | pipeline เก็บภาพ-ทำ label (tiled 2×2 + เกณฑ์ conf รายคลาส)-เทรน YOLO (oversample เฟรมที่มีมอเตอร์ไซค์ `--moto-boost`) ให้เข้ากับกล้องไทย |
| `rsc_service.py` | สถิติอุบัติเหตุ Thai RSC รายเขต + จุดเสี่ยงรอบกล้อง BMA (`/api/rsc/*`) |
| `violation_service.py` | จับผิดกฎจราจรจากกล้อง AI สด: ย้อนศร (เรียนรู้ทิศทางจราจรต่อกล้องเอง) และไม่สวมหมวกกันน็อก (โมเดล `helmet_cls.pt` ถ้ามี ไม่งั้นใช้ vision API) → `/api/ai/violations` สำเนาภาพลง `D:\Dataiolations` |
| `local/pipeline/collect_helmet_dataset.py`, `local/pipeline/train_helmet.py` | สร้างชุดข้อมูล crop ผู้ขี่ (label โดย vision API) แล้วเทรน YOLO11 classifier หมวก/ไม่หมวก → `helmet_cls.pt` |
| `local/pipeline/prefetch_tiles.py` | ดาวน์โหลด tile แผนที่ไว้ใช้ออฟไลน์ (รันครั้งเดียว) |

### Frontend (`web/src`, React + Tailwind v4)
| ไฟล์ | หน้าที่ |
|---|---|
| `App.jsx` | เลย์เอาต์หลัก (Sidebar ซ้าย + เนื้อหา), routing ด้วย hash, state กล้องที่เปิด, toast, poll เหตุการณ์ |
| `components/Sidebar.jsx` | เมนูซ้าย (กลุ่มหน้า), ชื่อผู้ใช้, สถานะกล้อง, สลับธีม สว่าง/มืด/ตามเครื่อง |
| `components/dashboard/ui.jsx` | ชิ้นส่วนพื้นฐาน: Card, Badge, Button, Segmented, Skeleton, EmptyState, ErrorState |
| `components/dashboard/primitives.jsx` | ชิ้นส่วนระดับหน้า: PageHeader, StatTile, StatusBanner, Tabs, Modal, ShareBar |
| `components/dashboard/format.js` | ฟอร์แมตเวลา/ตัวเลข/สีสถานะ |
| `components/DashboardPage.jsx` + `dashboard/*` | แดชบอร์ดจราจร: ประโยคสรุป, KPI, ดัชนีระบายรถ, เหตุการณ์, ถนนติด/โล่ง, กราฟแนวโน้ม, จำนวนรถผ่านกล้อง |
| `components/SidePanel.jsx`, `CameraCard.jsx`, `CityWindow.jsx`, `VideoSlot.jsx` | หน้า "กล้องของฉัน": เลือกกล้อง + ดูภาพสด HLS สูงสุด 9 ช่อง |
| `components/BmaCountPage.jsx` + `bma/*` | นับรถจากกล้อง กทม.: ภาพรวมตอนนี้, เทียบวัน/สัปดาห์/เดือน, กล้องทุกตัว + สตรีม YOLO |
| `components/YoloPage.jsx` | AI ตรวจจับรถสดจากกล้องเดียว ปรับ FPS/ความมั่นใจ |
| `components/MapPage.jsx` | แผนที่ MapLibre: เส้นจราจร, หมุดกล้อง, เหตุการณ์ |
| `components/WaterPage.jsx` + `water/*` | คาดการณ์น้ำ: กราฟรายสถานี, ตารางสถานี, น้ำทะเลหนุน, คลอง/ถนน, ฝน, รายงานสด กทม. |
| `components/AiPage.jsx` | แชทถาม AI เรื่องเส้นทาง พร้อมกล้อง AI ประกอบ |
| `lib/api.js` | ฟังก์ชันเรียก REST API ทั้งหมด |
| `lib/store.js` | localStorage: กล้องโปรด, กล้องที่เปิด, ชื่อผู้ใช้, ธีม |
| `index.css` | โทเค็นสี/ฟอนต์ Prompt, ธีมมืด (remap ตัวแปรสีภายใต้ `.dark`) |

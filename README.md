# BKK StreetSmart: กล้องจราจร กรุงเทพฯ และปริมณฑล + AI วิเคราะห์เมือง

เว็บแอปติดตามเมืองแบบเรียลไทม์ ครอบคลุม **กรุงเทพมหานคร และปริมณฑล**: กล้อง CCTV (กล้องสตรีมสด 34 ตัว + กล้อง กทม. 574 ตัวที่สแกนนับรถทุก ~4 นาที) ตรวจจับและนับรถด้วย **YOLO26x (Ultralytics)** จราจรรายถนน น้ำท่วม/ฝน/ระดับคลอง PM2.5 อุบัติเหตุ ตรวจหมวกกันน็อกและรถย้อนศร และ AI ผู้ช่วยตอบคำถาม

---

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

โค้ดหน้าเว็บโฉมใหม่อยู่ในโฟลเดอร์ `web/` เมื่อ build แล้ว `server.py` จะเสิร์ฟหน้าใหม่จาก `web/dist` โดยอัตโนมัติ (ถ้ายังไม่ได้ build จะใช้หน้าเดิมจาก `local/legacy_ui/`)

```bash
cd web
npm install
npm run build      # สร้าง web/dist แล้วเปิด launch\localhost_8000\start.bat ตามปกติ
npm run dev        # โหมดพัฒนา ที่ http://localhost:5173 (proxy /api ไป :8000)
npm run dev:8001   # เหมือนกัน แต่ proxy /api ไปเซิร์ฟเวอร์ทดสอบ :8001
```

`web/dist` ไม่อยู่ใน git แล้ว: สคริปต์ `start.bat` ใน `launch/` เรียก `launch\build_web.bat` ให้ build อัตโนมัติเมื่อยังไม่มี `web\dist` (ต้องมี Node.js) หลังแก้โค้ดหน้าเว็บให้รัน `launch\build_web.bat force` หรือ `npm run build`

---

## 🗺️ แผนที่จราจร / 🤖 AI ผู้ช่วยการจราจร / 📊 แดชบอร์ด

หน้าเว็บมี 8 หน้า (เมนูซ้าย): **Traffic Dashboard**, **City Analytics**, **Camera AI & Analysis**, **Traffic Map**, **Helmet Check**, **Wrong-Way Check**, **Water Forecast**, **Ask AI (Routes)**

- **เส้นจราจร (เขียว/เหลือง/แดง)** ดึงจาก Longdo Traffic vector tiles (`msv.longdo.com/maps/traffic`) ผ่านเซิร์ฟเวอร์ของเราที่แคชไว้ในโฟลเดอร์ `cache/` ถ้าเน็ตหลุดจะแสดงข้อมูลล่าสุดที่บันทึกไว้
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
# ตรวจหมวก: จำกัดการเรียก API ต่อชั่วโมง, โมเดลแยก
HELMET_PATROL_MAX_PER_HOUR=240
HELMET_AGENT_MODEL=gemini-3.1-flash-lite
# ตรวจย้อนศร: โมเดลทิศทางรถ (เทรนด้วย local\pipeline\wrongway_pipeline.bat), งบ AI ต่อชั่วโมง, จำนวนรถขั้นต่ำต่อช่องก่อนตัดสิน
WRONGWAY_DET=wrongway_det.pt
WRONGWAY_MAX_PER_HOUR=120
WRONGWAY_MIN_VOTES=40
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

ทางลัด: ดูหัวข้อ **🚀 วิธีเปิดใช้งาน** ด้านล่าง (สคริปต์ทั้งหมดอยู่ใน `launch/` แยกตาม Main web / localhost:8000 / localhost:8001)

- API: `GET /api/traffic/summary`, `GET /api/traffic/roads?q=`, `POST /api/chat`, tiles ที่ `/api/traffic/tile/{z}/{x}/{y}.pbf` และ `/api/tiles/base/{z}/{x}/{y}.png`

#### 🔒 การป้องกันเมื่อเปิดสาธารณะ (`backend/core/access_guard.py`)

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

## 📍 ขอบเขตพื้นที่กล้อง
- **กล้องสตรีมสด (`config/cameras_bkk.json`, 34 ตัว)**: กรุงเทพมหานคร 22, นครปฐม 5, นนทบุรี 3, สมุทรปราการ 3, ปทุมธานี 1
- **กล้อง กทม. (`config/cameras_bma.json`, 574 ตัว)**: snapshot ทุก ~4 นาที นับรถด้วย YOLO และใช้ตรวจหมวกกันน็อก/ย้อนศร

---

## 🚀 วิธีเปิดใช้งาน

สคริปต์เปิด/ปิดเซิร์ฟเวอร์อยู่ใน `launch/` แยกเป็น 3 โหมด ดับเบิลคลิกได้เลย (สคริปต์ `cd` กลับไป root เอง และ build `web\dist` ให้อัตโนมัติถ้ายังไม่มี)

| โหมด | URL | ใช้เมื่อ | สคริปต์ (`launch\...`) | ข้อมูล |
|---|---|---|---|---|
| 🌐 **Main web** (สาธารณะ) | https://cctv-bangkok.tail95e28b.ts.net (+ http://localhost:8000) | เปิดให้คนอื่นดูผ่าน Tailscale Funnel | `main_web\start.bat` · `main_web\restart.bat` (หลังแก้ `.env`/โค้ด) · `main_web\stop.bat` (ปิด Funnel, เซิร์ฟเวอร์ยังรัน) | root (`cache/`, `vehicle_counts.db`) |
| 💻 **localhost:8000** (ในเครื่อง) | http://localhost:8000 | ใช้งานจริงในเครื่อง/LAN ไม่เปิดออกอินเทอร์เน็ต | `localhost_8000\start.bat` · `localhost_8000\stop.bat` | root (ชุดเดียวกับ Main web) |
| 🧪 **localhost:8001** (ทดสอบ) | http://localhost:8001 | ลองโค้ดใหม่ก่อน `main_web\restart.bat` | `localhost_8001\start.bat` · `localhost_8001\stop.bat` | `local\stage\` ของตัวเอง (ไม่แตะของจริง) |

- Main web กับ localhost:8000 ใช้พอร์ต 8000 เดียวกัน จึงเปิดได้ทีละตัว ส่วน localhost:8001 เปิดพร้อมกับตัวใดตัวหนึ่งได้
- localhost:8001 ครั้งแรกจะคัดลอก cache เล็ก ๆ และ DB มาไว้ใน `local\stage\`; ลบโฟลเดอร์นี้เพื่อเริ่มใหม่สะอาด ๆ (ตัวแปร: `PORT`, `INSTANCE_DIR`, `BMA_DATA_DIR` ดู `backend/core/instance.py`)
- `launch\build_web.bat force` build หน้าเว็บใหม่หลังแก้โค้ดใน `web/`
- พัฒนาหน้าเว็บแบบ hot-reload: `npm run dev` (proxy `/api` ไป :8000) หรือ `npm run dev:8001` (proxy ไปเซิร์ฟเวอร์ทดสอบ :8001)

ขั้นตอน:
1. ดับเบิลคลิก **`launch\localhost_8000\start.bat`** (หรือ `launch\main_web\start.bat` ถ้าจะเปิดสาธารณะ)
2. ระบบจะเปิดเซิร์ฟเวอร์ FastAPI พร้อมโหลดโมเดล YOLO26x บน GPU
3. หน้าเว็บจะเปิดขึ้นมาที่ `http://localhost:8000` โดยอัตโนมัติ
4. เลือกหน้า **Camera AI & Analysis** จากเมนูซ้าย หรือกดไอคอนหุ่นยนต์บนหน้าต่างกล้องใดๆ เพื่อเปิดหน้าต่างวิเคราะห์การจราจรสด

## 📁 โครงสร้างโฟลเดอร์ (อะไรขึ้น Tailscale / อะไรใช้แค่ในเครื่อง)

`tailscale funnel 8000` เปิดเฉพาะ `server.py` ดังนั้น **ทุกอย่างนอก `local/` คือชุดที่เซิร์ฟเวอร์ต้องใช้** ส่วน `local/` คือของที่ใช้แค่ในเครื่องนี้ (เทรนโมเดล, เก็บ dataset, ของเก่า) ไม่ต้องคัดลอกไปเครื่องอื่น

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
├── launch/                       ← ▶️ ตัวรัน แยกตามโหมด
│   ├── main_web/        start / restart / stop   (Tailscale Funnel → :8000)
│   ├── localhost_8000/  start / stop             (ในเครื่อง :8000)
│   ├── localhost_8001/  start / stop             (ทดสอบ :8001, ข้อมูลใน local\stage)
│   └── build_web.bat
├── web/  (src/ = ซอร์ส React, dist/ = ที่เซิร์ฟจริง)  ← 🌐 หน้าเว็บ (build ด้วย npm run build)
├── tests/                        ← pytest
├── requirements.txt, .env        ← config (.env ห้าม commit)
├── yolo26x.pt (+ yolo26l/m), *_bkk.pt, helmet_*.pt, wrongway_*.pt ← 🌐 โมเดล (gitignore, ต้องคัดลอกเอง)
├── cache/, vehicle_counts.db, count_cameras.json    ← 🌐 ข้อมูล runtime ของ :8000 (สร้างเองอัตโนมัติ)
│
└── local/                                            ← 💻 ใช้ในเครื่องเท่านั้น
    ├── pipeline/   สคริปต์เก็บภาพ/label/เทรน + .bat/.sh ทั้งหมด (pipeline.bat, collect.bat, status.bat, watch_training.bat ...)
    ├── stage/      ข้อมูลของเซิร์ฟเวอร์ทดสอบ :8001 (gitignore)
    ├── dataset/, dataset_helmet/, runs/, logs/         ข้อมูลเทรนและผลลัพธ์ (gitignore)
    ├── legacy_ui/  หน้าเว็บเก่า (index.html, app.js, style.css, cameras_data.js) ใช้เป็น fallback เมื่อไม่มี web/dist
    ├── scratch/    ไฟล์ทดลอง
    └── archive/    ของเก่า/สำรอง
```

- ไฟล์ `.bat` ใน `local/pipeline/` ดับเบิลคลิกได้เหมือนเดิม (สคริปต์ `cd` กลับไป root เอง) ผลลัพธ์โมเดล `*_bkk.pt` / `helmet_cls.pt` ยังถูกเขียนลง root ให้เซิร์ฟเวอร์หยิบใช้
- เซิร์ฟเวอร์เสิร์ฟไฟล์ static จาก `web/dist` เท่านั้น (ไม่เสิร์ฟ root ทั้งโฟลเดอร์แล้ว) `.env`, `*.db`, `*.py` จึงไม่หลุดออก Tailscale

---

## 🧪 Tests

```bash
.venv\Scripts\python -m pytest tests
```

ครอบคลุมเกณฑ์ระดับน้ำบนถนน/ฝน/ตลิ่งใน `backend/traffic/road_service.py`, การป้องกันใน `backend/core/access_guard.py` และ context ของ chatbot

---

## แผนผังโค้ด (Code map)

### Backend (Python, FastAPI)
| ไฟล์ | หน้าที่ |
|---|---|
| `backend/core/instance.py` | พอร์ตและโฟลเดอร์ข้อมูลของ instance นี้ (`PORT`, `INSTANCE_DIR`): ทุก service ดึง path ของ `cache/` และ `vehicle_counts.db` จากที่นี่ ให้เซิร์ฟเวอร์จริง (:8000) กับเซิร์ฟเวอร์ทดสอบ (:8001, `launch/localhost_8001`) รันพร้อมกันได้โดยไม่เขียนทับกัน |
| `server.py` | จุดเริ่มต้น: โหลดกล้อง, สร้าง detector/scanner/services, ประกาศ REST API ทั้งหมด, เสิร์ฟ `web/dist` |
| `backend/vision/yolo_detector.py` | YOLO26x + ByteTrack บนสตรีมกล้องเดียว (หน้า AI ตรวจจับรถสด), นับรถผ่าน, ประเมินระดับจราจร, ตรวจรถจอดนิ่ง/ชน |
| `backend/vision/count_workers.py` | นับรถต่อเนื่องหลายกล้องในพื้นหลัง (แดชบอร์ด "จำนวนรถที่ผ่านกล้อง AI") |
| `backend/vision/survey.py` | วนสำรวจทุกกล้องสั้น ๆ เพื่อให้ป้ายระดับ โล่ง/ปานกลาง/ติดขัด ในหน้ากล้อง |
| `backend/vision/vehicle_log.py` | SQLite `vehicle_counts.db`: ยอดรายชั่วโมง, sample จาก survey, เหตุการณ์จากกล้อง |
| `backend/vision/incident_service.py` | รวมเหตุการณ์: กล้อง AI (ยืนยันด้วย Claude vision) + รายงาน Longdo |
| `backend/traffic/traffic_service.py` | ดึง tile จราจร Longdo, สรุปการระบายรถรายถนน, proxy tile แผนที่ |
| `backend/agents/chat_service.py` | หน้า "Ask AI": รวมข้อมูลสดทุกหมวด (จราจร น้ำ/ฝน PM2.5 อุบัติเหตุ เส้นเลี่ยง น้ำท่วมรายถนน การฝ่าฝืน analytics) เป็น context ดึงถนน/เขตที่ผู้ใช้ถามขึ้นก่อน แล้วให้ Gemini → Claude → rule-based ตอบตามลำดับ |
| `backend/bma/bma_service.py` | สแกนกล้อง กทม. 574 ตัว (snapshot ทุก ~4 นาที) นับรถด้วย YOLO, เก็บ `bma_latest`/`bma_history`, สตรีม MJPEG |
| `backend/bma/bma_archive.py` | รอบนับอัตโนมัติ: สะสมยอดต่อกล้อง, รีเซ็ตทุกชั่วโมง, เขียน CSV รายวัน/สัปดาห์/เดือน/รายถนน ที่ `BMA_DATA_DIR` (ตั้งใน `.env` ตอนนี้ `E:\data smartstreet`), ข้อมูลเปรียบเทียบ |
| `backend/bma/bma_events.py` | ดึงรายงานสด (น้ำท่วม/อุบัติเหตุ) จาก cpudapp.bangkok.go.th ทุก 60 วินาที |
| `backend/water/water_service.py` | ระดับน้ำ/คลอง/น้ำทะเลหนุน/ฝน จาก thaiwater.net + คาดการณ์ (ทางการ 7 วัน หรือโมเดลในเครื่อง 48 ชม.) + หาคีย์ API ใหม่อัตโนมัติ |
| `backend/traffic/guidance_service.py` | คำแนะนำระบายรถรายเส้นทางหลัก 12 สาย ทุก 1 นาที จากเส้นสี Longdo (hotspots) + กล้อง กทม. + เหตุการณ์; Gemini เรียบเรียงข้อความทุก 5 นาที (`/api/traffic/guidance`) |
| `backend/water/flood_service.py` | จุดน้ำท่วมขังถนน กทม. ~250 จุด จากเซ็นเซอร์สำนักการระบายน้ำ (`weather.bangkok.go.th/flood`) ดึงทุก 5 นาที: ระดับน้ำเหนือผิวถนนหน่วย ซม. ต่อจุด + ถนน/เขต/พิกัด/เวลาเริ่มท่วม/สูงสุด เกณฑ์ตามเว็บต้นทาง (≤5 ปกติ, 5-10 เล็กน้อย, >10 ท่วม) เก็บประวัติในหน่วยความจำเพื่อบอกแนวโน้มขึ้น/ลงเทียบ 25 นาทีก่อน และให้ Gemini เขียนบทวิเคราะห์ (ระดับความรุนแรง จุดที่ต้องจับตา คำแนะนำ แนวโน้ม) ทุก 5 นาทีเมื่อสถานการณ์เปลี่ยน มี template ภาษาไทยสำรองเมื่อไม่มี key (`/api/flood/status|stations|roads|analysis`) — เฉพาะ กทม. 50 เขต ปริมณฑลไม่มีเซ็นเซอร์สาธารณะ |
| `backend/traffic/road_service.py` | ประเมินความเสี่ยงน้ำท่วมขัง **รายถนน** ทั้ง กทม. และปริมณฑล ทุก 2 นาที: รวมถนนทุกสายจาก `traffic_service` (ชื่อ+จุดกึ่งกลาง+% รถติด) เข้ากับเซ็นเซอร์น้ำบนถนน (`flood_service`, เฉพาะ กทม.), สถานีวัดฝน 24 ชม. ~180 จุด และสถานีระดับน้ำคลอง/แม่น้ำ ~70 จุด (`water_service`) ด้วยระยะทางจริง แล้วจัดระดับตาม **เกณฑ์ทางการ** (น้ำบนถนน: สนน. กทม. 5/10 ซม. + ปภ. 20/60/80 ซม. · ฝน 24 ชม.: กรมอุตุนิยมวิทยา 10/35/90 มม. · ระดับตลิ่ง: คลังข้อมูลน้ำแห่งชาติ 80%/100%) + Gemini เขียนบทวิเคราะห์สายที่เสี่ยงสุด · สายที่ไม่มีเซ็นเซอร์บนถนนจะทำเครื่องหมาย `measured: false` (`/api/roads/risk`) |
| `backend/water/air_service.py` | PM2.5 / AQI รายสถานีจาก Air4Thai ทุก 10 นาที (`/api/air/stations`) |
| `backend/vision/helmet_service.py` | ตรวจหมวกกันน็อกทุกกล้อง กทม.: crop มอไซจากรอบสแกน → โมเดลในเครื่อง (`HELMET_DET`, ค่าปัจจุบัน `helmet_det_blur.pt`) คัดกรอง → AI agent (Gemini/Claude) ยืนยัน → ผู้ไม่สวมหมวกเก็บภาพ+CSV ที่ `BMA_DATA_DIR\helmet\` (`/api/helmet/*`) |
| `backend/vision/wrongway_service.py` | ตรวจรถย้อนศรทุกกล้อง กทม. จากภาพนิ่ง: กรอบรถจาก yolo26x ตัวเดียวกับที่นับรถ → โมเดลจำแนกทิศ `wrongway_cls.pt` (YOLO26s-cls, `toward` เห็นหน้ารถ / `away` เห็นท้ายรถ) อ่านรถทีละคัน (ไม่มีไฟล์นี้จะใช้ `wrongway_det.pt` ตัวเก่าที่หารถไม่ค่อยเจอ) → กล้องแต่ละตัวเรียนรู้ทิศปกติต่อช่องกริด 12×9 (`cache/heading/`) → รถที่หันสวนช่องที่รู้ทิศแล้วส่ง AI agent ยืนยัน → หลักฐาน+CSV ที่ `BMA_DATA_DIR\wrongway\` (`/api/wrongway/*`) |
| `local/pipeline/collect_wrongway_dataset.py`, `train_wrongway_det.py`, `wrongway_pipeline.bat`, `wrongway_status.bat` | dataset ทิศทางรถแบบไม่ต้อง label มือ: เก็บ burst จากทุกกล้อง (BMA ~1 เฟรม/วิ + HLS) ติดตามรถ ทิศจากการเคลื่อนที่ (รถจอดใช้แผนที่ทิศของกล้อง) → fine-tune `yolo26x.pt` เป็น `wrongway_det.pt`; `wrongway_pipeline.bat [รอบ] [นาทีห่าง] [epochs] [batch]` ทำครบทั้งสองขั้น + หน้าต่างสถานะ |
| `local/pipeline/prep_wrongway_cls.py`, `train_wrongway_cls.py` | ตัดกรอบ `toward/away` จาก `dataset_wrongway` เป็นภาพครอป (`local/dataset_wrongway_cls/`) → เทรน `yolo26s-cls` 128 px (`--clean` ย้ายภาพที่ label น่าจะผิดไป `rejected/` แล้วเทรนซ้ำ) → `wrongway_cls.pt`; รันข้างเซิร์ฟเวอร์ได้ ใช้ GPU ~1-2 GB |
| `backend/core/access_guard.py` | ป้องกันเมื่อเปิด Funnel สาธารณะ: POST ควบคุมทำได้จาก LAN/tailnet หรือ `X-Admin-Token`; `/api/chat` จำกัดต่อ IP |
| `local/pipeline/backup_db.py` (`backup_db.bat`) | งานกลางคืน: ลบ `bma_history`/`samples` เกิน 90 วัน, VACUUM, สำเนา DB + CSV + .env ไป `BMA_DATA_DIR\backup\` (ลงทะเบียน Task Scheduler 03:30 แล้ว) |
| `local/pipeline/watchdog.bat` | ping `/api/health` ทุก 1 นาที ล้ม 3 ครั้งติดจึงรัน `launch\main_web\restart.bat` |
| `local/pipeline/prep_helmet_det.py`, `train_helmet_det.py`, `watch_train.*` | dataset Kaggle helmet-detection → YOLO format → fine-tune `yolo26x.pt` เป็น `helmet_det.pt` (helmet / no_helmet) + หน้าต่าง % ความคืบหน้า |
| `local/pipeline/` (`collect_dataset.py`, `relabel_dataset.py`, `clean_dataset.py`, `train_model.py`, `pipeline_status.py`, `*.bat`) | pipeline เก็บภาพ-ทำ label (tiled 2×2 + เกณฑ์ conf รายคลาส)-เทรน YOLO (oversample เฟรมที่มีมอเตอร์ไซค์ `--moto-boost`) ให้เข้ากับกล้องไทย |
| `backend/traffic/rsc_service.py` | สถิติอุบัติเหตุ Thai RSC รายเขต + จุดเสี่ยงรอบกล้อง BMA (`/api/rsc/*`) |
| `backend/vision/violation_service.py` | จับผิดกฎจราจรจากกล้อง AI สด: ย้อนศร (เรียนรู้ทิศทางจราจรต่อกล้องเอง) และไม่สวมหมวกกันน็อก (โมเดล `helmet_cls.pt` ถ้ามี ไม่งั้นใช้ vision API) → `/api/ai/violations` สำเนาภาพลง `BMA_DATA_DIR\violations` |
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
| `components/DashboardPage.jsx` + `dashboard/*` | แดชบอร์ดจราจร 4 แท็บ: ภาพรวมจราจร, **วิเคราะห์รายถนน** (`dashboard/RoadRiskPanel.jsx`), เหตุการณ์สด, รายงานสดจากศูนย์ |
| `components/SidePanel.jsx`, `CameraCard.jsx`, `CityWindow.jsx`, `VideoSlot.jsx` | หน้า "กล้องของฉัน": เลือกกล้อง + ดูภาพสด HLS สูงสุด 9 ช่อง |
| `components/BmaCountPage.jsx` + `bma/*` | นับรถจากกล้อง กทม.: ภาพรวมตอนนี้, เทียบวัน/สัปดาห์/เดือน, กล้องทุกตัว + สตรีม YOLO |
| `components/HelmetPage.jsx`, `components/WrongWayPage.jsx` | ตรวจหมวกกันน็อก / ตรวจรถย้อนศร จากกล้อง กทม. ทุกตัว: หลักฐาน, รถที่สงสัย (สั่งตรวจซ้ำด้วยโมเดลในเครื่องหรือ AI), กล้องทุกตัว + ตรวจตอนนี้ |
| `components/AnalyticsPage.jsx` | City Analytics: ดัชนีความแออัด ความหนาแน่นถนน คาดการณ์น้ำท่วม 1-6 ชม. จุดเสี่ยงอุบัติเหตุ ผู้เข้าชม + export CSV/JSON |
| `components/CameraAiPage.jsx` | Camera AI & Analysis: รวมแท็บกล้องสด / AI ตรวจจับ / นับรถกล้อง กทม. |
| `components/YoloPage.jsx` | AI ตรวจจับรถสดจากกล้องเดียว ปรับ FPS/ความมั่นใจ |
| `components/MapPage.jsx` | แผนที่ MapLibre: เส้นจราจร, หมุดกล้อง, เหตุการณ์, เรดาร์ฝน, PM2.5, ลม, อาคาร 3D/ผังอาคาร+ชื่อสถานที่, **น้ำท่วมขังถนน กทม.** (ป้ายความลึก ซม. จากเซ็นเซอร์ สนน.) และ **ระดับน้ำแม่น้ำ/คลองปริมณฑล** (% ความจุตลิ่ง จากคลังข้อมูลน้ำแห่งชาติ ครอบคลุม กทม. นนทบุรี ปทุมธานี สมุทรปราการ นครปฐม สมุทรสาคร) |
| `components/WaterPage.jsx` + `water/*` | คาดการณ์น้ำ: กราฟรายสถานี, ตารางสถานี, น้ำทะเลหนุน, คลอง/ถนน, ฝน, รายงานสด กทม. |
| `components/AiPage.jsx` | แชทถาม AI เรื่องเส้นทาง พร้อมกล้อง AI ประกอบ |
| `lib/api.js` | ฟังก์ชันเรียก REST API ทั้งหมด |
| `lib/store.js` | localStorage: กล้องโปรด, กล้องที่เปิด, ชื่อผู้ใช้, ธีม |
| `index.css` | โทเค็นสี/ฟอนต์ Prompt, ธีมมืด (remap ตัวแปรสีภายใต้ `.dark`) |

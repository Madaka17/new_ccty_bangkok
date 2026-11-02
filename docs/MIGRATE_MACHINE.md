# ย้ายเซิร์ฟเวอร์ไปเครื่องใหม่

คู่มือนี้ใช้ตอนย้าย BKK StreetSmart (production :8000, test :8001), ENVIRO (:5050) และ Cloudflare Tunnel
จากเครื่องเดิมไปเครื่องใหม่ ทำตามลำดับ ข้อ 1-5 ทำได้ตอนเครื่องเดิมยังเปิดเว็บอยู่ เว็บจะปิดเฉพาะช่วงข้อ 6
(ประมาณ 15-30 นาที ขึ้นกับขนาดข้อมูลที่ต้องคัดลอกรอบสุดท้าย)

เครื่องเดิม ณ 2026-10-24: Windows 11, Ryzen 5 3600, RTX 3080, Python 3.14.7, Node 24.19.0,
PyTorch 2.14.0+cu130, โปรเจกต์อยู่ที่ `E:\new_ccty_bangkok`, ข้อมูลสถิติอยู่ที่ `E:\data smartstreet`

---

## 1. เช็คเครื่องใหม่ก่อน

| เช็คอะไร | ทำไม |
|---|---|
| GPU NVIDIA และ VRAM | `yolo26x.pt` ใช้ประมาณ 36 ms/เฟรม บน RTX 3080 ถ้า GPU เล็กกว่านี้หรือไม่มี GPU ดูข้อ 4 |
| ที่ว่างในดิสก์ | ต้องพอสำหรับ `instances\`, ไฟล์ `*.pt` และโฟลเดอร์ `BMA_DATA_DIR` (ดูขนาดจริงบนเครื่องเดิมก่อน) |
| มีไดรฟ์ `E:` หรือไม่ | ถ้าใช้ path เดิมได้ `E:\new_ccty_bangkok` จะต้องแก้ค่าน้อยที่สุด (scheduled task, `.env`, memory ของ Claude ผูกกับ path นี้) |
| ชื่อผู้ใช้ Windows | `launch\cloudflare\config.yml` ชี้ไฟล์ credentials ที่ `C:\Users\user\.cloudflared\` ถ้าชื่อผู้ใช้ไม่ใช่ `user` ต้องแก้ไฟล์นี้ |

---

## 2. ติดตั้งโปรแกรมบนเครื่องใหม่

1. **ปิด Smart App Control** ก่อนติดตั้งอย่างอื่น: Settings > Privacy & security > Windows Security >
   App & browser control > Smart App Control > Off
   ถ้าไม่ปิด `import torch` จะเจอ `WinError 4551` เพราะ Windows บล็อก DLL ที่ไม่มีลายเซ็น
   ปิดแล้วเปิดกลับไม่ได้ ถ้าไม่ลง Windows ใหม่
2. ติดตั้งไดรเวอร์ NVIDIA ตัวล่าสุด (ต้องรองรับ CUDA 13 เพราะใช้ PyTorch build `cu130`)
3. ติดตั้ง Git, Python 3.14, Node.js 24
4. ติดตั้ง cloudflared ที่ `C:\Program Files (x86)\cloudflared\cloudflared.exe`
   (`launch\cloudflare\install_service.ps1` ใช้ path นี้ ถ้าติดตั้งที่อื่นต้องแก้ตัวแปร `$exe` ในไฟล์นั้น)
5. ติดตั้ง Tailscale ถ้าจะดูหน้า BKK Monitor จากมือถือ

---

## 3. ดึงโค้ดและติดตั้งแพ็กเกจ

```powershell
git clone https://github.com/Madaka17/new_ccty_bangkok.git E:\new_ccty_bangkok
cd E:\new_ccty_bangkok

python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130

cd web
npm ci
cd ..
```

ตรวจว่า PyTorch เห็น GPU (รันนอกเซิร์ฟเวอร์เท่านั้น ห้ามใส่คำสั่งนี้ในโค้ดเซิร์ฟเวอร์):

```powershell
.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

ต้องได้ `True` ตามด้วยชื่อการ์ดจอ ถ้าได้ `False` ให้เช็คไดรเวอร์และ build ของ PyTorch

ENVIRO ใช้ `.venv` ตัวเดียวกับโปรเจกต์หลัก (`launch\enviro\start.bat` เรียก `.venv\Scripts\pythonw.exe`)
ถ้า ENVIRO ขาดแพ็กเกจให้ติดตั้งเพิ่มจาก `ENVIRO\requirements.txt` ลงใน `.venv` เดียวกัน

---

## 4. คัดลอกไฟล์ที่ไม่อยู่ใน git (รอบแรก)

รอบแรกทำตอนเครื่องเดิมยังรันอยู่ เพื่อย้ายของใหญ่ไปก่อน รอบสุดท้ายในข้อ 6 จะคัดลอกเฉพาะส่วนที่เปลี่ยน

ตัวอย่างใช้ `robocopy` จากเครื่องเดิม โดย `$DST` คือปลายทาง เช่น share ของเครื่องใหม่ `\\NEWPC\E$`
หรือฮาร์ดดิสก์ภายนอก

```powershell
$SRC = 'E:\new_ccty_bangkok'
$DST = '\\NEWPC\E$\new_ccty_bangkok'

# ค่าตั้งและคีย์ลับ
robocopy $SRC $DST .env

# โมเดล (ไม่อยู่ใน git เพราะใหญ่)
robocopy $SRC $DST yolo26x.pt helmet_det.pt helmet_det_blur.pt wrongway_det.pt wrongway_cls.pt
robocopy "$SRC\weights" "$DST\weights" /E

# ข้อมูลของแต่ละเซิร์ฟเวอร์: DB, cache, ค่าของ agent, web build
robocopy "$SRC\instances\production" "$DST\instances\production" /E /XD dist_old dist_prev* dist_river_* dist_next
robocopy "$SRC\instances\test" "$DST\instances\test" /E

# ข้อมูล ENVIRO
robocopy "$SRC\ENVIRO\data" "$DST\ENVIRO\data" enviro.db accounts.txt

# สถิติและรูปหลักฐาน (BMA_DATA_DIR ใน .env)
robocopy 'E:\data smartstreet' '\\NEWPC\E$\data smartstreet' /E
```

ไฟล์ใน `instances\production\cache\` ที่ห้ามหาย:

| ไฟล์ | ถ้าหายจะเกิดอะไร |
|---|---|
| `session_secret` | session ของผู้ใช้ทุกคนใช้ไม่ได้ ต้องเปิดหน้าเว็บใหม่ |
| `vapid_private.pem`, `push_subs.json` | การแจ้งเตือนแบบ push ที่ผู้ใช้สมัครไว้ส่งไม่ได้อีก ผู้ใช้ต้องสมัครใหม่ |
| `yolo_switch.json` | สถานะเปิด/ปิด YOLO ถ้าหายจะเริ่มแบบเปิด |
| `telemetry.db` | สถิติผู้ใช้เว็บ |

ของที่คัดลอกหรือไม่ก็ได้:

- `local\labels\`, `local\logs\`, `local\dataset*\`, `local\runs\`, `local\buildings\`: ข้อมูลเทรนโมเดลและรายงานเก่า
- `launch\watchdog\state\`, `launch\monitor\state\`: log และประวัติของ watchdog กับ BKK Monitor
- `yolo11x.pt`: โมเดลเก่า ไม่ได้ใช้แล้ว

ไฟล์ลับที่ต้องคัดลอกแยก (อยู่นอกโปรเจกต์ ห้ามใส่ git):

- `C:\Users\user\.cloudflared\<tunnel-id>.json`: credentials ของ tunnel `bkk-streetsmart`
- `C:\Users\user\.cloudflared\cert.pem`: ใช้ตอนสั่ง `cloudflared tunnel ...` ที่ต้องล็อกอิน

memory ของ Claude Code (ให้ Claude จำเรื่องเดิมของโปรเจกต์ได้):

- `C:\Users\user\.claude\projects\E--new-ccty-bangkok\memory\` คัดลอกไปที่เดียวกันบนเครื่องใหม่
  ชื่อโฟลเดอร์มาจาก path ของโปรเจกต์ ถ้าโปรเจกต์ไม่ได้อยู่ที่ `E:\new_ccty_bangkok` ชื่อโฟลเดอร์จะเปลี่ยนตาม

ไฟล์ SQLite ที่คัดลอกตอนเซิร์ฟเวอร์รันอยู่อาจไม่สมบูรณ์ ไม่เป็นไรในรอบแรก เพราะรอบสุดท้ายจะคัดลอกทับหลังหยุดเซิร์ฟเวอร์

---

## 5. ปรับค่าให้เข้ากับเครื่องใหม่ แล้วทดสอบบน test :8001

### 5.1 แก้ `.env` ถ้าจำเป็น

- `BMA_DATA_DIR`: ถ้าโฟลเดอร์ข้อมูลไม่ได้อยู่ที่ `E:\data smartstreet`
- GPU แรงไม่พอสำหรับ `yolo26x.pt` เลือกอย่างใดอย่างหนึ่ง:

| ทางเลือก | ทำอย่างไร | ผล |
|---|---|---|
| ใช้โมเดลเล็กลง | `AI_MODEL=yolo26m.pt` (หรือ `yolo26s.pt`, `yolo26n.pt`) | นับรถได้ แม่นน้อยลง ระบบโหลดไฟล์เองถ้ายังไม่มี |
| ลดโมเดลหมวกและย้อนศร | ลบหรือคอมเมนต์ `HELMET_DET`, `WRONGWAY_DET` | `helmet_det*.pt` และ `wrongway_det.pt` เทรนจาก yolo26x จึงหนักเท่ากัน `AI_MODEL` ไม่ได้เปลี่ยนสองตัวนี้ |
| ปิด YOLO ทั้งหมด | `launch\yolo_switch.bat 8000 --off` | เว็บ แผนที่ น้ำท่วม ฝน ยังทำงาน การจราจรใช้ Longdo แทน นับรถ หมวก ย้อนศร หยุด |

ถ้าใส่ชื่อไฟล์ใน `AI_MODEL` ผิด `backend\services.py` จะกลับไปใช้ `yolo26x.pt` เอง
ให้ดู log ว่ามีบรรทัด `[AI] ... not found, falling back to yolo26x.pt` หรือไม่

ไม่มี GPU NVIDIA: โค้ดใช้ CPU ให้เอง แต่ช้ามาก ใช้ได้แค่ `yolo26n.pt` หรือ `yolo26s.pt` หรือปิด YOLO

### 5.2 ทดสอบบน test server

```powershell
launch\test\start.bat
```

1. เปิด http://localhost:8001 ในเบราว์เซอร์ (ถ้าหน้าแรกได้ `503` ให้รัน `launch\build_web.bat` ก่อน)
2. เช็คทุกเมนู: ภาพรวมจราจร แผนที่ กล้อง AI น้ำท่วม แจ้งเตือน ถาม AI
3. `launch\yolo_status.bat` ดูว่า YOLO โหลดบน GPU และใช้ VRAM เท่าไร
4. `launch\camera_status.bat` ดูว่ากล้องดึงภาพได้
5. `.venv\Scripts\python -m pytest tests` ต้องผ่านทั้งหมด
6. หยุด test: `launch\test\stop.bat`

`API_SESSION=1` เปิดอยู่ ถ้าใช้ `curl` ยิง `/api` จะได้ `403` ให้เช็คผ่านเบราว์เซอร์แทน

อย่า restart ซ้ำหลายรอบติดกัน เว็บ BMA จะบล็อก IP ชั่วคราว (`429`) เมื่อดึงภาพถี่เกินไป

---

## 6. สลับเครื่องจริง (เว็บปิดช่วงนี้)

ทำตามลำดับนี้เท่านั้น ห้ามให้ cloudflared รันพร้อมกันสองเครื่อง: tunnel เดียวกันที่มีสองเครื่องต่ออยู่
Cloudflare จะแบ่งผู้ใช้ไปทั้งสองเครื่อง ข้อมูลจะแยกกันสองชุด

### บนเครื่องเดิม

```powershell
# 1. ปิด watchdog ก่อน ไม่อย่างนั้นมันจะเปิดเซิร์ฟเวอร์ขึ้นมาใหม่ภายใน 2 นาที
Disable-ScheduledTask -TaskName 'BKK StreetSmart watchdog'
Disable-ScheduledTask -TaskName 'BKK StreetSmart backup'

# 2. หยุดเซิร์ฟเวอร์ทุกตัว
launch\production\stop.bat
launch\test\stop.bat
launch\enviro\stop.bat

# 3. หยุด tunnel และไม่ให้เปิดเองตอนบูต (ต้องเปิด PowerShell แบบ administrator)
Stop-Service cloudflared
Set-Service cloudflared -StartupType Disabled
```

จากนั้นคัดลอกรอบสุดท้าย (ใช้ `$SRC`, `$DST` ชุดเดิมจากข้อ 4):

```powershell
robocopy "$SRC\instances\production" "$DST\instances\production" /E /XD dist_old dist_prev* dist_river_* dist_next
robocopy "$SRC\instances\test" "$DST\instances\test" /E
robocopy "$SRC\ENVIRO\data" "$DST\ENVIRO\data" enviro.db accounts.txt
robocopy 'E:\data smartstreet' '\\NEWPC\E$\data smartstreet' /E
```

ใช้ `/E` ไม่ใช้ `/MIR` เพราะ `/MIR` ลบไฟล์ที่ปลายทางที่ไม่มีที่ต้นทาง ถ้าพิมพ์ path ผิดอาจลบข้อมูลบนเครื่องใหม่ได้

### บนเครื่องใหม่

```powershell
# 4. เปิดเซิร์ฟเวอร์
launch\production\start.bat
launch\enviro\start.bat
```

5. เช็คในเบราว์เซอร์: http://localhost:8000 และ http://127.0.0.2:8000 ต้องเปิดได้ทั้งคู่
   (tunnel ส่งผู้ใช้เข้า `127.0.0.2:8000` เพราะ `backend\core\access_guard.py` อ่าน IP ผู้ใช้จาก
   `CF-Connecting-IP` เฉพาะบนที่อยู่นี้)
6. ถ้าชื่อผู้ใช้ Windows ไม่ใช่ `user` แก้ `credentials-file` ใน `launch\cloudflare\config.yml`
7. ติดตั้ง tunnel เป็น service (PowerShell แบบ administrator):

```powershell
powershell -ExecutionPolicy Bypass -File launch\cloudflare\install_service.ps1
```

8. เปิด https://bkksmartstreet.com และ https://bkksmartstreet.com/enviro/ จากมือถือที่ใช้เน็ตมือถือ
   (ไม่ใช่ WiFi บ้าน) ต้องเปิดได้และข้อมูลเป็นปัจจุบัน

---

## 7. ติดตั้งงานเบื้องหลังบนเครื่องใหม่

```powershell
# watchdog: เปิดเซิร์ฟเวอร์ใหม่เมื่อ :8000 หรือ :5050 ไม่ตอบ (ทุก 2 นาที)
powershell -ExecutionPolicy Bypass -File launch\watchdog\install.ps1

# BKK Monitor: collector ทุก 30 วินาที + หน้าเว็บสำหรับมือถือที่ 127.0.0.1:8090 + ไอคอนบน Desktop
powershell -ExecutionPolicy Bypass -File launch\monitor\install.ps1

# สำรอง DB ทุกคืน 03:30
schtasks /create /tn "BKK StreetSmart backup" /tr "\"E:\new_ccty_bangkok\local\pipeline\backup_db.bat\"" /sc daily /st 03:30

# ให้มือถือดู BKK Monitor ผ่าน Tailscale
tailscale serve --bg 8090
```

ไอคอน `BKK YOLO On-Off` บน Desktop: สร้าง shortcut ไปที่ `launch\yolo_switch.bat` เอง ถ้าต้องการ

---

## 8. หลังย้ายเสร็จ

1. เก็บเครื่องเดิมไว้อย่างน้อย 1 สัปดาห์ ห้ามลบข้อมูลจนกว่าเครื่องใหม่จะรันได้ปกติ
2. เช็ค `launch\logs\production.log` และ BKK Monitor วันละครั้งในสัปดาห์แรก
3. เช็คว่าสำรอง DB คืนแรกสำเร็จ: ดู `local\logs\backup.log` และโฟลเดอร์ `<BMA_DATA_DIR>\backup\`
4. วัดความรับโหลดใหม่ด้วยสคริปต์ใน `local\loadtest\` (เครื่องเดิมรับได้ประมาณ 500 req/s)
5. ถ้าจะรันโมเดล LLM ในเครื่อง (Bionic, LM Studio) ข้าง YOLO ให้ดู VRAM ที่เหลือก่อนเลือกขนาดโมเดล
6. บอก Claude ให้อัปเดต memory ที่ผูกกับเครื่องเดิม: path ของเซิร์ฟเวอร์, GPU, Smart App Control,
   ความรับโหลด, โมเดล local

---

## ตรวจทานก่อนปิดงาน

- [ ] Smart App Control ปิดแล้ว, `torch.cuda.is_available()` ได้ `True`
- [ ] `.env`, ไฟล์ `*.pt`, `instances\`, `ENVIRO\data\`, `BMA_DATA_DIR` อยู่บนเครื่องใหม่
- [ ] `session_secret`, `vapid_private.pem`, `push_subs.json` คัดลอกแล้ว
- [ ] test :8001 ผ่าน และ `pytest` ผ่าน
- [ ] watchdog และ backup บนเครื่องเดิมปิดแล้ว, cloudflared บนเครื่องเดิมหยุดและตั้งเป็น Disabled
- [ ] production :8000 และ ENVIRO :5050 บนเครื่องใหม่เปิดได้ทั้ง `localhost` และ `127.0.0.2`
- [ ] https://bkksmartstreet.com และ `/enviro/` เปิดได้จากเน็ตภายนอก
- [ ] watchdog, BKK Monitor, backup ติดตั้งบนเครื่องใหม่แล้ว
- [ ] memory ของ Claude อัปเดตแล้ว

---

## 9. ย้ายไป Raspberry Pi (เว็บอยู่ Pi, YOLO อยู่คอม)

ส่วนนี้ต่างจากข้อ 1-8: ไม่ได้ย้ายทุกอย่าง แต่แบ่งงานกันสองเครื่อง

| เครื่อง | รันอะไร |
|---|---|
| Pi 4 (`192.168.1.109`, user `test`, โค้ดที่ `/mnt/ssd/new_ccty_bangkok`) | production :8000, ENVIRO :5050, cloudflared, ดึงภาพ BMA, DB, สำรอง DB |
| คอม (RTX 3080) | AI worker :8100 (YOLO ทุกโมเดลให้ Pi), Bionic :1235, test :8001, build เว็บ |

ถ้าคอมปิด Pi ยังเปิดเว็บได้ แต่ไม่มี AI ตรวจภาพ

### 9.1 ติดตั้งบน Pi (ทำแล้ว 2026-11-02)

```bash
cd /mnt/ssd/new_ccty_bangkok && bash launch/pi/setup.sh
```

สคริปต์ติดตั้งแพ็กเกจระบบ, uv, `.venv` (Python 3.14) และ `ENVIRO/.venv`
torch ใช้แบบ CPU (`--torch-backend cpu`) เพราะ Pi ไม่มี GPU ถ้าใช้แบบปกติจะดึงแพ็กเกจ CUDA มาอีกประมาณ 20 ตัว
บรรทัดสุดท้ายต้องขึ้น `cuda False` และ `CUDA packages (want 0): 0`

รัน test บน Pi ต้องข้าม test ของ BKK Monitor 4 ไฟล์ (`tests/test_monitor_*.py`) เพราะเป็นโปรแกรมของ Windows

### 9.2 ค่าที่ต้องตั้งบน Pi

- `YOLO_ALLOWED=0`: ปิด YOLO ตลอด ถึงจะมีคนกดเปิดก็ไม่โหลด เพราะถ้าโหลดบน Pi
  ultralytics จะดาวน์โหลดโมเดลแล้วใช้ CPU เต็ม
- `BMA_FETCH=0`: ไม่ดึงภาพและข่าวจาก BMA ใช้ตอนทดสอบเท่านั้น เพราะ Pi กับคอมออกเน็ตด้วย IP เดียวกัน
  ถ้าดึงพร้อมกันสองเครื่อง BMA จะตอบ 429 ตอนสลับเครื่องจริง ห้ามใส่ใน production ของ Pi

ปิดได้ด้วย `0`, `false`, `no` หรือ `off` ทั้งสองค่าอยู่ใน unit แล้ว ส่วน `.env` ให้ `server.py` อ่านเอง ค่าใน unit จะมาก่อนค่าใน `.env`
`.env` บน Pi ต้องเป็นสิทธิ์ `600` (มีคีย์ API) และห้าม commit

### 9.3 systemd unit (`launch/pi/`)

| unit | ใช้ตอนไหน |
|---|---|
| `bkk-test.service` | ทดสอบใน LAN ที่ `http://192.168.1.109:8001` (ไม่ผ่าน tunnel) |
| `bkk-production.service` | ตอนสลับเครื่องเท่านั้น |
| `bkk-enviro.service` | ตอนสลับเครื่องเท่านั้น |

```bash
bash launch/pi/install_units.sh bkk-test.service   # คัดลอกและ reload เท่านั้น ไม่เปิดเอง
sudo systemctl start bkk-test
journalctl -u bkk-test -f
```

ทุก unit รอให้ `/mnt/ssd` mount ก่อน (`RequiresMountsFor`) และเปิดใหม่เองเมื่อหลุด
unit ของ test และ production จะช้าลงเมื่อใช้ RAM ถึง 2 GB และเปิดใหม่เองเมื่อถึง 3 GB เพื่อไม่ให้ Pi ค้างทั้งเครื่อง

`BMA_FETCH=0` ปิดการดึงจาก BMA ทุกทาง ทั้งการสแกนอัตโนมัติ, ข่าว, ปุ่มสแกน, ภาพสดในหน้ากล้อง และ `check_now`

ผลทดสอบ 2026-11-02 (เปิดทิ้งไว้ 1 ชั่วโมง):
- เปิดได้ใน 75 วินาที, log ไม่มี `Traceback`, ไม่ restart เลย
- RAM ประมาณ 1.05 GB และหยุดขึ้นหลัง 10 นาทีแรก (สูงสุด 1.2 GB ตอนงานน้ำท่วมรัน) จาก 8 GB
- CPU เฉลี่ย 21% ของหนึ่ง core (Pi มี 4 core) อุณหภูมิ 39 °C
- กดเปิด YOLO แล้วโดนปฏิเสธ และไม่มีการต่อไปที่ BMA

### 9.4 AI worker บนคอม (B2, ทำแล้ว 2026-11-02)

Pi ไม่มี GPU จึงส่งภาพไปให้คอมตรวจด้วย YOLO ทุกโมเดล (นับรถ, หมวกกันน็อก, ย้อนศร, ตัวจับผิด)

- บนคอม: ไอคอน **BKK AI Worker** บน Desktop (`launch\ai_worker\start.bat`) ปิดด้วย `stop.bat`
  log อยู่ที่ `launch\logs\ai_worker.log` ดูสถานะที่ `http://127.0.0.1:8100/`
- ตั้งครั้งแรก: `powershell -File launch\ai_worker\install.ps1` สร้าง `AI_WORKER_TOKEN` ใน `.env` และไอคอน
- บน Pi ใส่ใน `.env` 2 บรรทัด: `AI_WORKER_URL=http://192.168.1.101:8100` และ `AI_WORKER_TOKEN=` ค่าเดียวกับคอม
- worker ตอบเฉพาะ IP ใน `AI_WORKER_ALLOW` (ค่าเริ่มต้น Pi กับคอมเอง) ที่ส่ง token ถูก
- โหลดโมเดลตอนมีคนเรียก คืน VRAM เมื่อไม่ได้ใช้ 10 นาที
- ส่งภาพเป็น PNG ไม่ใช่ JPEG: ภาพกล้อง BMA เล็ก (352x288) แค่บีบ JPEG ผล YOLO ก็เปลี่ยน
  ทดสอบ 20 ภาพ ผลตรงกับรันบนคอมเองทุกกล่อง

ถ้าคอมปิดหรือ worker ล่ม: Pi ทำงานต่อแบบ YOLO ปิด (หน้าเว็บขึ้นว่า AI ปิด) และกลับมาเองภายในประมาณ 30-60 วินาที
หลัง worker เปิด ไม่ต้อง restart Pi

ผลทดสอบ 2026-11-02 บน Pi test :8001: กล้องสดได้ประมาณ 4 ภาพ/วินาที (ตั้งไว้ 10) ใช้เวลาไปกลับ 220 ms ต่อภาพ
ว่าง 10 นาทีแล้ว worker คืน VRAM ประมาณ 1.1 GB (3144 เหลือ 1985 MiB) production :8000 ไม่ได้รับผลกระทบ

watchdog เช็ค :8100 เฉพาะเมื่อมีไฟล์ `launch\watchdog\state\enabled_8100` ให้สร้างไฟล์นี้ตอนสลับเครื่อง

IP คอม `192.168.1.101` ได้จาก router เอง ควรจองไว้ใน router เหมือน Pi

### 9.5 เรื่องที่ยังต้องทำก่อนสลับเครื่อง

- **กล้องอุดร** ดึงไม่ได้บน Pi: `CERTIFICATE_VERIFY_FAILED` เพราะเว็บส่ง certificate มาไม่ครบ
  Windows หาตัวที่ขาดเองได้ แต่ Linux หาไม่ได้
- **`.env` ของ Pi**: `LOCAL_LLM_URL` ต้องชี้ไปที่ IP ของคอมใน LAN
  (`BMA_DATA_DIR` ตั้งไว้ใน unit แล้วเป็น `/mnt/ssd/data_smartstreet`)
- **BKK Monitor และสำรอง DB** ยังเป็นของ Windows ต้องทำตัวของ Linux

### 9.6 คัดลอกข้อมูล (C) และสลับเครื่อง (D): ยังไม่ทำ

- C: คัดลอก `instances/production`, `ENVIRO/data`, `BMA_DATA_DIR` และไฟล์ `.pt` ไป `/mnt/ssd` ด้วย `scp` หรือ `rsync`
  ตอนเว็บบนคอมยังเปิดอยู่ ส่วน DB ให้ใช้ sqlite backup ห้ามคัดลอกไฟล์ตรงๆ ขณะที่เซิร์ฟเวอร์เขียนอยู่
- D: ทำตามข้อ 6 แต่ฝั่งเครื่องใหม่ใช้ `systemctl enable --now bkk-production bkk-enviro`
  แล้วติดตั้ง cloudflared service บน Pi
  **ห้ามเปิด cloudflared บน Pi ขณะที่ tunnel บนคอมยังรันอยู่** เพราะผู้ใช้จะถูกแบ่งไปสองเครื่อง
  ทำเมื่อคุณสั่งเท่านั้น

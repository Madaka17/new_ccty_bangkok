r"""
YOLO on/off from the Desktop ("BKK YOLO On-Off" -> launch\yolo_switch.bat).

Shows whether YOLO is on and how much GPU memory is in use, asks, then switches every YOLO model on or
off through the server's /api/ai/yolo (operator only: it answers this machine). The server keeps the
state across restarts.
Usage: yolo_switch.py [port] [--on | --off]   (no flag: ask)
"""
import json
import sys
import urllib.error
import urllib.request


def call(port, method="GET", body=None, timeout=120):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/ai/yolo", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def describe(st):
    state = "เปิด" if st.get("enabled") else "ปิด"
    vram = st.get("vram")
    mem = f" · GPU ใช้ {vram['used_mb'] / 1024:.1f} จาก {vram['total_mb'] / 1024:.1f} GB" if vram else ""
    loaded = [n for n, on in (st.get("holders") or {}).items() if on]
    return f"YOLO ตอนนี้: {state}{mem}" + (f"\nโมเดลที่อยู่บน GPU: {', '.join(loaded)}" if loaded else "")


def main(argv, ask=input):
    port = next((a for a in argv if a.isdigit()), "8000")
    try:
        st = call(port, timeout=10)
    except (urllib.error.URLError, OSError) as e:
        print(f"ต่อเซิร์ฟเวอร์ที่พอร์ต {port} ไม่ได้: {e}")
        return 1
    print(describe(st))
    if "--on" in argv or "--off" in argv:
        want = "--on" in argv
    else:
        want = not st.get("enabled")
        answer = ask(f"{'เปิด' if want else 'ปิด'} YOLO ไหม? (Y/N) ").strip().lower()
        if answer not in ("y", "yes", "ใช่"):
            print("ไม่เปลี่ยน")
            return 0
    print("กำลังเปิด YOLO (โหลดโมเดลราว 10-30 วินาที)..." if want else "กำลังปิด YOLO และคืน GPU...")
    try:
        out = call(port, "POST", {"enabled": want})
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(e, TimeoutError) or isinstance(reason, TimeoutError):   # socket.timeout is TimeoutError
            print("ยังโหลดอยู่ ลองเปิดไอคอนนี้อีกครั้งเพื่อดูสถานะ")
        else:
            print(f"สั่งเปลี่ยนไม่สำเร็จ: {e}")
        return 1
    print(describe(out))
    for name, err in (out.get("errors") or {}).items():
        print(f"  {name}: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

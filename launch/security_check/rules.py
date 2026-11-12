"""Pure rules: facts in, Thai findings out. No I/O. Secrets never reach here, only lengths and booleans.

Finding = {"area": "attack"|"web"|"config"|"host", "level": "ok"|"info"|"warn"|"fail",
           "title": str, "detail": str, "fix": str}
"""
import re

KIND_TH = {
    "probe": "สแกนหาช่องโหว่",
    "bad_path": "path อันตราย",
    "docs_probe": "แอบดูหน้าเอกสาร API",
    "control_denied": "สั่งปุ่มควบคุมจากนอกบ้าน",
    "not_browser": "สคริปต์ดึง API",
    "no_session": "เรียก API ไม่ผ่านหน้าเว็บ",
    "rate_limited": "ยิงถี่เกิน",
    "chat_limited": "ใช้แชท AI ถี่เกิน",
    "report_limited": "แจ้งเหตุถี่เกิน",
    "too_large": "ส่งข้อมูลใหญ่เกิน",
    "dropped": "นับไม่ทัน (ทิ้ง)",
}

KNOWN_PORTS = {22: "SSH", 8000: "เว็บ", 5050: "ENVIRO", 9101: "pistats", 8090: "monitor"}
WAF = "Cloudflare → Security → WAF"


def _f(area, level, title, detail="", fix=""):
    if level in ("ok", "info"):
        fix = ""
    return {"area": area, "level": level, "title": title, "detail": detail, "fix": fix}


def evaluate_attacks(summary):
    a = "attack"
    if summary is None:
        return [_f(a, "info", "ต่อ Pi ไม่ได้ ดูยอดโจมตีไม่ได้")]
    total = summary.get("total") or 0
    if total == 0:
        return [_f(a, "ok", "ยังไม่มีข้อมูล / ไม่พบการโจมตี")]
    by_kind = summary.get("by_kind") or {}
    days = summary.get("days")
    out = []
    top = sorted(((k, n) for k, n in by_kind.items() if n), key=lambda kv: -kv[1])[:3]
    top_txt = ", ".join(f"{KIND_TH.get(k, k)} {n}" for k, n in top)
    span = f" ใน {days} วัน" if days else ""
    out.append(_f(a, "info", f"ถูกบล็อก {total} ครั้ง{span}", top_txt))

    probe = by_kind.get("probe", 0)
    if probe >= 100:
        paths = ", ".join(p["path"] for p in (summary.get("top_paths") or [])[:3])
        out.append(_f(a, "warn", "มีการสแกนหาช่องโหว่บ่อย", f"{probe} ครั้ง" + (f" เช่น {paths}" if paths else ""),
                      f"เพิ่มกฎใน {WAF} → Custom rules ให้บล็อก path ที่โดนบ่อย หรือบล็อก IP ที่ยิงมากสุด"))

    ips = summary.get("top_ips") or []
    if ips and ips[0]["n"] >= 50 and ips[0]["n"] * 2 >= total:
        ip = ips[0]
        out.append(_f(a, "warn", f"IP {ip['ip']} ยิงมากผิดปกติ", f"{ip['n']} จาก {total} ครั้ง",
                      f"บล็อก IP นี้ใน {WAF} → Tools → IP Access Rules"))

    lim = by_kind.get("rate_limited", 0) + by_kind.get("chat_limited", 0)
    if lim >= 500:
        out.append(_f(a, "warn", "มีคนยิงถี่เกินกำหนดมาก", f"{lim} ครั้ง",
                      "เปิด Rate Limiting ที่ Cloudflare → Security → WAF → Rate limiting rules"))

    if by_kind.get("dropped", 0) > 0:
        out.append(_f(a, "info", "มีบางครั้งนับไม่ทัน", f"ทิ้ง {by_kind['dropped']} ครั้ง ตัวเลขจริงอาจมากกว่านี้"))
    return out


_SEC_HEADERS = ("content-security-policy", "strict-transport-security", "x-frame-options",
                "x-content-type-options", "referrer-policy")
_HEADER_FIX = {
    "content-security-policy": "ตั้ง Content-Security-Policy ที่ middleware ของเซิร์ฟเวอร์",
    "strict-transport-security": "ตั้ง Strict-Transport-Security (HSTS) ที่ Cloudflare → SSL/TLS → Edge Certificates",
    "x-frame-options": "ตั้ง X-Frame-Options: DENY ที่ middleware ของเซิร์ฟเวอร์",
    "x-content-type-options": "ตั้ง X-Content-Type-Options: nosniff ที่ middleware ของเซิร์ฟเวอร์",
    "referrer-policy": "ตั้ง Referrer-Policy: strict-origin-when-cross-origin ที่ middleware ของเซิร์ฟเวอร์",
}


def _is_html(ctype):
    return "text/html" in (ctype or "").lower()


def evaluate_web(checks):
    a = "web"
    out = []
    headers = checks.get("headers")
    if headers is not None:
        for h in _SEC_HEADERS:
            if h not in headers:
                out.append(_f(a, "fail", f"ขาด header {h}", "หน้าเว็บไม่ส่ง header ป้องกันนี้", _HEADER_FIX[h]))
        server = headers.get("server", "")
        if re.search(r"\d+\.\d+", server):
            out.append(_f(a, "info", "header server บอกเลขเวอร์ชัน", server))
    status = checks.get("status") or {}
    for path in ("/docs", "/openapi.json"):
        if path in status:
            code, ctype, _body = status[path]
            if code == 200 and not _is_html(ctype):
                out.append(_f(a, "fail", f"หน้าเอกสาร API เปิดให้คนนอกดู ({path})", f"ตอบ 200 ชนิด {ctype}",
                              "ปิด docs ของเซิร์ฟเวอร์ (docs_url=None, openapi_url=None) หรือบล็อก path นี้ที่ Cloudflare"))
    for path in ("/.env", "/.git/HEAD"):
        if path in status:
            code, ctype, _body = status[path]
            if code == 200 and not _is_html(ctype):
                out.append(_f(a, "fail", f"ไฟล์ลับเปิดให้โหลดได้ ({path})", f"ตอบ 200 ชนิด {ctype}",
                              "บล็อก path นี้ทันทีที่เซิร์ฟเวอร์และ Cloudflare แล้วเปลี่ยนรหัสลับทุกตัว"))
    api = "/api/traffic/summary"
    if api in status and status[api][0] == 200:
        out.append(_f(a, "warn", "เรียก API ได้โดยไม่ต้องมี cookie", f"{api} ตอบ 200",
                      "เปิด API_SESSION=1 ใน .env ของ production แล้วรีสตาร์ตเซิร์ฟเวอร์"))
    days = checks.get("cert_days_left")
    if days is not None:
        fix = "ตรวจ Cloudflare → SSL/TLS → Edge Certificates ว่าต่ออายุอัตโนมัติหรือไม่"
        if days < 3:
            out.append(_f(a, "fail", f"ใบรับรอง HTTPS ใกล้หมดมาก (เหลือ {days} วัน)", "", fix))
        elif days < 14:
            out.append(_f(a, "warn", f"ใบรับรอง HTTPS เหลือ {days} วัน", "", fix))
    return out


def evaluate_config(flags):
    a = "config"
    if flags is None:
        return [_f(a, "info", "อ่านค่าตั้งไม่ได้")]
    out = []
    n = flags.get("admin_token_len")
    if n is not None:
        if n == 0:
            out.append(_f(a, "warn", "ยังไม่ตั้งรหัสปุ่มควบคุม", "ตอนนี้สั่งได้เฉพาะในวง LAN",
                          "ตั้ง ADMIN_TOKEN ใน .env เป็นตัวอักษรสุ่ม 32 ตัวขึ้นไป ถ้าจะสั่งจากนอกบ้าน"))
        elif n < 24:
            out.append(_f(a, "fail", "รหัสปุ่มควบคุมสั้นเกินไป", f"ยาว {n} ตัว",
                          "เปลี่ยน ADMIN_TOKEN ใน .env เป็นตัวอักษรสุ่ม 32 ตัวขึ้นไป"))
        else:
            out.append(_f(a, "ok", "รหัสปุ่มควบคุมยาวพอ", f"ยาว {n} ตัว"))
    if flags.get("api_session") is False:
        out.append(_f(a, "warn", "API_SESSION ปิดอยู่", "คนนอกเรียก API ตรงๆ ได้โดยไม่ผ่านหน้าเว็บ",
                      "ตั้ง API_SESSION=1 ใน .env แล้วรีสตาร์ตเซิร์ฟเวอร์"))
    if flags.get("api_browser_only") is False:
        out.append(_f(a, "warn", "API_BROWSER_ONLY ปิดอยู่", "สคริปต์ที่ไม่ใช่เบราว์เซอร์เรียก API ได้",
                      "ตั้ง API_BROWSER_ONLY=1 ใน .env แล้วรีสตาร์ตเซิร์ฟเวอร์"))
    if flags.get("general_rate_per_min") == 0:
        out.append(_f(a, "warn", "ไม่จำกัดจำนวนครั้งต่อนาที", "ใครก็ยิงถี่ได้",
                      "ตั้งค่าจำกัดต่อนาที (general rate) ใน .env ให้มากกว่า 0"))
    if flags.get("chat_rate_per_day") == 0:
        out.append(_f(a, "warn", "ไม่จำกัดแชท AI ต่อวัน", "เสี่ยงค่า AI พุ่ง",
                      "ตั้งค่าจำกัดแชทต่อวัน (chat rate) ใน .env ให้มากกว่า 0"))
    return out


def _split_addr(addr):
    host, _, port = addr.rpartition(":")
    try:
        return host, int(port)
    except ValueError:
        return host, None


def evaluate_host(raw):
    a = "host"
    if raw is None:
        return [_f(a, "info", "ต่อ Pi ไม่ได้")]
    out = []
    sshd = raw.get("sshd")
    if sshd:
        if sshd.get("passwordauthentication") == "yes":
            out.append(_f(a, "fail", "SSH ยังเข้าด้วยรหัสผ่านได้", "คนเดารหัสผ่านได้",
                          "แก้ /etc/ssh/sshd_config เป็น PasswordAuthentication no (กุญแจใช้ได้อยู่แล้ว) แล้ว sudo systemctl restart ssh"))
        root = sshd.get("permitrootlogin")
        if root is not None and root not in ("no", "prohibit-password"):
            out.append(_f(a, "fail", "SSH ให้ root เข้าด้วยรหัสผ่านได้", f"PermitRootLogin = {root}",
                          "แก้ /etc/ssh/sshd_config เป็น PermitRootLogin no แล้ว sudo systemctl restart ssh"))
    fw = raw.get("firewall")
    if fw is not None and fw != "active":
        out.append(_f(a, "warn", "ไฟร์วอลล์ยังไม่เปิด", f"สถานะ: {fw}",
                      "รัน sudo ufw allow from 192.168.1.0/24 แล้ว sudo ufw enable"))
    seen = set()
    for addr in raw.get("listen") or []:
        host, port = _split_addr(addr)
        if port is None or host not in ("0.0.0.0", "*", "[::]", "::") or port in seen:
            continue
        seen.add(port)
        if port == 5900:
            out.append(_f(a, "warn", "VNC เปิดให้ทั้งวง LAN", "พอร์ต 5900",
                          "ปิด VNC (sudo raspi-config → Interface Options → VNC) หรือจำกัดด้วย ufw"))
        elif port not in KNOWN_PORTS:
            out.append(_f(a, "warn", f"พอร์ต {port} เปิดให้ทั้งวง LAN", f"ฟังที่ {addr}",
                          f"ถ้าไม่ได้ใช้ ให้ปิดโปรแกรมนั้น หรือ sudo ufw deny {port}"))
    up = raw.get("upgradable")
    if up is not None and up >= 20:
        out.append(_f(a, "warn", f"มีอัปเดตค้าง {up} รายการ", "",
                      "รัน sudo apt update && sudo apt upgrade"))
    if raw.get("unattended") is False:
        out.append(_f(a, "info", "ยังไม่ได้เปิดอัปเดตความปลอดภัยอัตโนมัติ", "แนะนำ: sudo apt install unattended-upgrades"))
    if raw.get("reboot_required"):
        out.append(_f(a, "warn", "ต้องรีบูต Pi เพื่อใช้อัปเดต", "", "รัน sudo reboot ตอนไม่มีคนใช้"))
    if raw.get("fail2ban") is False:
        out.append(_f(a, "info", "ยังไม่ได้ลง fail2ban", "แนะนำ: sudo apt install fail2ban"))
    return out


def overall(findings):
    levels = {f["level"] for f in findings}
    if "fail" in levels:
        return "fail"
    if "warn" in levels:
        return "warn"
    return "ok"

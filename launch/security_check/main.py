"""Security check entry point: python -m launch.security_check.main --target production|test [--days N] [--no-open]"""
import argparse
import os
import sys
import webbrowser
from datetime import datetime

from . import collect, geo, report, rules

ROOT = collect.ROOT
REPORTS_DIR = os.path.join(ROOT, "local", "reports", "security")
PROD_URL = "https://bkksmartstreet.com"
TEST_URL = "http://localhost:8001"


def _f(area, level, title, detail="", fix="", cmd=""):
    return {"area": area, "level": level, "title": title, "detail": detail, "fix": fix, "cmd": cmd}


def _attack_findings(summary, owner_ips=()):
    if isinstance(summary, dict) and summary.get("_error") == "not_deployed":
        return [_f("attack", "info", "เซิร์ฟเวอร์บน Pi ยังไม่ได้อัปเดตตัวบันทึก",
                   "ยอดการโจมตีจะเริ่มนับหลังอัปเดตเซิร์ฟเวอร์")]
    return rules.evaluate_attacks(summary, owner_ips=owner_ips)


def _web_findings(checks, trusted_origin=False):
    fs = rules.evaluate_web(checks, trusted_origin=trusted_origin)
    if not checks or (checks.get("headers") is None and not checks.get("status")):
        fs.append(_f("web", "info", "ต่อหน้าเว็บไม่ได้", "ตรวจหน้าเว็บไม่ได้ในรอบนี้"))
    elif not fs:
        fs.append(_f("web", "ok", "หน้าเว็บผ่านทุกข้อที่ตรวจ"))
    if trusted_origin:
        fs.append(_f("web", "info", "ตรวจจากเครื่องนี้ (ในบ้าน) เลยตรวจรั้วกันคนนอกไม่ได้",
                     "ดูผลจริงได้ที่ --target production"))
    return fs


def _extra(summary, ssh, owner_ips):
    owners = list(owner_ips)
    counts = {}
    for src in ((summary or {}).get("top_ips") or [], (ssh or {}).get("failed_ips") or []):
        for x in src:
            try:
                ip = x.get("ip")
                if not ip:
                    continue
                counts[ip] = counts.get(ip, 0) + int(x.get("n", 0))
            except (AttributeError, TypeError, ValueError):
                continue
    rows = []
    for ip, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        cc = geo.lookup(ip)
        rows.append({"ip": ip, "cc": cc, "country": geo.country_name(cc) if cc else "",
                     "n": n, "owner": rules._same_home(ip, owners)})
    return {"ssh": ssh, "owner_ips": list(owner_ips), "geo": rows}


def _public_ips():
    return [ip for ip in (collect.public_ip(), collect.public_ip_v4()) if ip]


def _owner_list(pubs, ssh_log):
    """Owner IPs: our public IPs (v6 and v4) plus LAN/home IPs seen in accepted SSH logins, deduped."""
    owners = []
    for ip in pubs:
        if ip not in owners:
            owners.append(ip)
    for x in (ssh_log or {}).get("accepted") or []:
        ip = str(x.get("ip", "")) if isinstance(x, dict) else ""
        if not ip:
            continue
        if (ip.startswith("192.168.1.") or rules._same_home(ip, pubs)) and ip not in owners:
            owners.append(ip)
    return owners


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=("production", "test"), default="production")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if a.target == "production":
        summary = collect.pi_attack_summary(a.days)
        config = collect.pi_config_flags()
        host_raw = collect.pi_host_raw()
        host = rules.evaluate_host(host_raw)
        token = collect.pi_self_check_token()
        web = collect.web_checks(PROD_URL, self_check_token=token)
        ssh_log = collect.pi_ssh_log(a.days)
        pubs = _public_ips()
        owner_ips = _owner_list(pubs, ssh_log)
        pw_auth = ((host_raw or {}).get("sshd") or {}).get("passwordauthentication")
        host = host + rules.evaluate_ssh_log(ssh_log, owner_ips=owner_ips, password_auth=pw_auth)
    else:
        summary = collect.local_attack_summary(os.path.join(ROOT, "instances", "test"), a.days)
        config = collect.local_config_flags(os.path.join(ROOT, "instances", "test", ".env"))
        host = [_f("host", "info", "ตรวจเครื่อง Pi เฉพาะ production")]
        token = collect.local_self_check_token(os.path.join(ROOT, "instances", "test"))
        web = collect.web_checks(TEST_URL, self_check_token=token)
        ssh_log = None
        owner_ips = _owner_list(_public_ips(), None)

    sections = {
        "attack": _attack_findings(summary, owner_ips) + ([] if token else [
            _f("attack", "info", "ส่งรหัสตรวจตัวเองไม่ได้ รอบนี้จะถูกนับเป็นการโจมตี")]),
        "web": _web_findings(web, trusted_origin=(a.target == "test")),
        "config": rules.evaluate_config(config),
        "host": host,
    }
    real = summary if isinstance(summary, dict) and not summary.get("_error") else None
    extra = _extra(real, ssh_log, owner_ips)
    now = datetime.now()
    html = report.render(a.target, sections, real, now.strftime("%Y-%m-%d %H:%M"), extra)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"security-{a.target}-{now.strftime('%Y%m%d-%H%M')}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    verdict = report.VERDICT[rules.overall([f for fs in sections.values() for f in fs])][1]
    print(path)
    print("ผลรวม:", verdict)
    if not a.no_open:
        webbrowser.open("file:///" + path.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # crash -> exit 1
        print("crash:", type(e).__name__, e)
        sys.exit(1)

"""Security check entry point: python -m launch.security_check.main --target production|test [--days N] [--no-open]"""
import argparse
import os
import sys
import webbrowser
from datetime import datetime

from . import collect, report, rules

ROOT = collect.ROOT
REPORTS_DIR = os.path.join(ROOT, "local", "reports", "security")
PROD_URL = "https://bkksmartstreet.com"
TEST_URL = "http://localhost:8001"


def _f(area, level, title, detail="", fix=""):
    return {"area": area, "level": level, "title": title, "detail": detail, "fix": fix}


def _attack_findings(summary):
    if isinstance(summary, dict) and summary.get("_error") == "not_deployed":
        return [_f("attack", "info", "เซิร์ฟเวอร์บน Pi ยังไม่ได้อัปเดตตัวบันทึก",
                   "ยอดการโจมตีจะเริ่มนับหลังอัปเดตเซิร์ฟเวอร์")]
    return rules.evaluate_attacks(summary)


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
        host = rules.evaluate_host(collect.pi_host_raw())
        web = collect.web_checks(PROD_URL)
    else:
        summary = collect.local_attack_summary(os.path.join(ROOT, "instances", "test"), a.days)
        config = collect.local_config_flags(os.path.join(ROOT, "instances", "test", ".env"))
        host = [_f("host", "info", "ตรวจเครื่อง Pi เฉพาะ production")]
        web = collect.web_checks(TEST_URL)

    sections = {
        "attack": _attack_findings(summary),
        "web": _web_findings(web, trusted_origin=(a.target == "test")),
        "config": rules.evaluate_config(config),
        "host": host,
    }
    real = summary if isinstance(summary, dict) and not summary.get("_error") else None
    now = datetime.now()
    html = report.render(a.target, sections, real, now.strftime("%Y-%m-%d %H:%M"))
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

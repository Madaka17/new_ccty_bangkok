"""Thai HTML report. Self-contained, offline, all dynamic text escaped."""
from html import escape as _e

from .rules import KIND_TH, overall

VERDICT = {"ok": ("✓", "ปลอดภัยดี", "ไม่พบเรื่องที่ต้องแก้"),
           "warn": ("!", "ควรดู", "มีเรื่องที่ควรตรวจและแก้"),
           "fail": ("✗", "ต้องแก้", "มีเรื่องที่ต้องแก้ก่อน")}
MARK = {"ok": "✓ ผ่าน", "info": "i ข้อมูล", "warn": "! ควรดู", "fail": "✗ ต้องแก้"}
AREA_TH = {"attack": "การโจมตีที่ถูกบล็อก", "web": "หน้าเว็บสาธารณะ", "config": "ค่าตั้งเซิร์ฟเวอร์", "host": "เครื่อง Pi"}
TARGET_TH = {"production": "เว็บจริง (production)", "test": "เว็บทดสอบ (test)"}

CSS = """
:root{color-scheme:dark;--bg:#0d0d0f;--card:#17171b;--line:#2a2a31;--fg:#ececf0;--mut:#9a9aa6;--acc:#ff8a1f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 "Noto Sans Thai Looped",system-ui,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:1.3rem;margin:0 0 4px}h2{font-size:1.1rem;margin:24px 0 8px;color:var(--acc)}
.mut{color:var(--mut);font-size:.9rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:10px 0}
.verdict{font-size:1.6rem;font-weight:700;border-left:6px solid var(--acc);padding-left:12px}
.big{font-size:2.6rem;font-weight:700;color:var(--acc);line-height:1.1}
table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
th{color:var(--mut);font-weight:600}td.n,th.n{text-align:right;white-space:nowrap}
.bars{display:flex;align-items:flex-end;gap:2px;height:70px}
.bars span{flex:1;background:var(--acc);min-height:2px;border-radius:2px 2px 0 0}
.tag{display:inline-block;font-weight:700;padding:0 8px;border:1px solid var(--line);border-radius:6px;margin-right:6px;white-space:nowrap}
.fail .tag{border-color:#ff5a5a;color:#ff7a7a}.warn .tag{border-color:var(--acc);color:var(--acc)}
.ok .tag{border-color:#4cc38a;color:#4cc38a}
.item{padding:8px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}.item:last-child{border:0}
.fix{margin-top:4px}.fix b{color:var(--acc)}
"""


def _item(f, with_fix=True):
    lv = f.get("level", "info")
    s = f'<div class="item {_e(lv)}"><span class="tag">{_e(MARK.get(lv, lv))}</span><b>{_e(f.get("title", ""))}</b>'
    if f.get("detail"):
        s += f'<div class="mut">{_e(f["detail"])}</div>'
    if with_fix and f.get("fix"):
        s += f'<div class="fix"><b>วิธีแก้:</b> {_e(f["fix"])}</div>'
    return s + "</div>"


def _attacks(summary):
    if summary is None:
        return '<div class="card">ต่อ Pi ไม่ได้ ยังไม่มีข้อมูลยอดโจมตี</div>'
    if summary.get("_error") or (not summary.get("by_day") and not summary.get("total")):
        return '<div class="card">ยังไม่มีข้อมูล ยอดการโจมตีจะเริ่มนับหลังอัปเดตเซิร์ฟเวอร์</div>'
    days = summary.get("days", "")
    total = summary.get("total", 0)
    by_day = summary.get("by_day") or []
    mx = max([d.get("n", 0) for d in by_day] or [0]) or 1
    bars = "".join(f'<span style="height:{max(3, round(100 * d.get("n", 0) / mx))}%" '
                   f'title="{_e(str(d.get("day", "")))}: {int(d.get("n", 0))}"></span>' for d in by_day)
    s = (f'<div class="card"><div class="mut">ถูกบล็อกใน {_e(str(days))} วัน</div>'
         f'<div class="big">{int(total):,} ครั้ง</div>')
    if bars:
        s += f'<div class="bars" role="img" aria-label="ยอดบล็อกรายวัน">{bars}</div>'
        s += (f'<div class="mut">{_e(str(by_day[0].get("day", "")))} ถึง '
              f'{_e(str(by_day[-1].get("day", "")))} (สูงสุด {mx} ครั้ง/วัน)</div>')
    s += "</div>"
    kinds = sorted((summary.get("by_kind") or {}).items(), key=lambda kv: -kv[1])
    if kinds:
        rows = "".join(f'<tr><td>{_e(KIND_TH.get(k, k))}</td><td class="n">{int(n):,}</td></tr>' for k, n in kinds if n)
        s += f'<div class="card"><table><tr><th>ชนิด</th><th class="n">ครั้ง</th></tr>{rows}</table></div>'
    for key, head, col in (("top_ips", "IP ที่ยิงมากสุด", "ip"), ("top_paths", "path ที่โดนมากสุด", "path")):
        items = summary.get(key) or []
        if items:
            rows = "".join(f'<tr><td>{_e(str(i.get(col, "")))}</td><td class="n">{int(i.get("n", 0)):,}</td></tr>' for i in items)
            s += f'<div class="card"><table><tr><th>{head}</th><th class="n">ครั้ง</th></tr>{rows}</table></div>'
    return s


def render(target, sections, summary, generated):
    allf = [f for fs in sections.values() for f in fs]
    ov = overall(allf)
    icon, word, sub = VERDICT[ov]
    todo = sorted((f for f in allf if f["level"] in ("warn", "fail")), key=lambda f: f["level"] != "fail")
    p = [f'<!doctype html><html lang="th"><head><meta charset="utf-8">'
         f'<meta name="viewport" content="width=device-width,initial-scale=1">'
         f'<title>ตรวจความปลอดภัย {_e(target)}</title><style>{CSS}</style></head><body><div class="wrap">',
         f'<h1>ตรวจความปลอดภัย BKK StreetSmart</h1>'
         f'<div class="mut">{_e(TARGET_TH.get(target, target))} · {_e(generated)}</div>',
         f'<div class="card"><div class="verdict">{icon} {_e(word)}</div><div class="mut">{_e(sub)}</div></div>',
         '<h2>ยอดโจมตีที่ถูกบล็อก</h2>', _attacks(summary), '<h2>ควรแก้อะไร</h2>']
    if todo:
        p.append('<div class="card">' + "".join(_item(f) for f in todo) + "</div>")
    else:
        p.append('<div class="card">✓ ไม่มีเรื่องที่ต้องแก้</div>')
    p.append("<h2>ผลตรวจทั้งหมด</h2>")
    for area, fs in sections.items():
        p.append(f'<div class="card"><b>{_e(AREA_TH.get(area, area))}</b>'
                 + ("".join(_item(f, False) for f in fs) or '<div class="mut">ไม่มีรายการ</div>') + "</div>")
    p.append("</div></body></html>")
    return "".join(p)

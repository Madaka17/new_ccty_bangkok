"""Thai HTML security report, neon SIEM look. Self-contained (inline CSS/JS/SVG), offline, all dynamic text escaped."""
import math
from html import escape as _e

from . import geo
from .rules import KIND_TH, overall, owner_total

VERDICT = {"ok": ("✓", "ปลอดภัยดี", "ไม่พบเรื่องที่ต้องแก้"),
           "warn": ("!", "ควรดู", "มีเรื่องที่ควรตรวจและแก้"),
           "fail": ("✗", "ต้องแก้", "มีเรื่องที่ต้องแก้ก่อน")}
MARK = {"ok": "✓ ผ่าน", "info": "i ข้อมูล", "warn": "! ควรดู", "fail": "✗ ต้องแก้"}
AREA_TH = {"attack": "การโจมตีที่ถูกบล็อก", "web": "หน้าเว็บสาธารณะ", "config": "ค่าตั้งเซิร์ฟเวอร์", "host": "เครื่อง Pi"}
TARGET_TH = {"production": "เว็บจริง (production)", "test": "เว็บทดสอบ (test)"}
CREDIT = "IP→ประเทศ: DB-IP.com (CC BY 4.0) · แผนที่: Natural Earth · พิกัดประเทศ: mledoze/countries (ODbL)"
MAP_W, MAP_H = 1000, 500
BKK = (13.75, 100.5)

CSS = """
:root{color-scheme:dark;--bg:#0b0618;--card:#140a2a;--line:rgba(170,90,255,.35);--glow:#c44dff;--glow2:#ff4fd8;
--fg:#f1eaff;--mut:#a99cc4;--ok:#39e6a0;--warn:#ffb547;--fail:#ff4f7b;--chip:rgba(57,230,160,.12);
--mono:ui-monospace,Consolas,"Cascadia Mono",monospace}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:radial-gradient(1200px 600px at 80% -10%,#2a0f55 0,transparent 60%),var(--bg);color:var(--fg);
font:16px/1.6 "Noto Sans Thai Looped","Segoe UI",system-ui,sans-serif;overflow-x:hidden}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:1.35rem;margin:0;line-height:1.3}
h2{font-size:1.05rem;margin:0 0 10px;color:var(--fg);letter-spacing:.2px}
h2::before{content:"";display:inline-block;width:4px;height:1em;margin-right:8px;vertical-align:-2px;border-radius:2px;
background:linear-gradient(var(--glow2),var(--glow))}
.mut{color:var(--mut);font-size:.9rem}
.num,.big,code,pre,td.n{font-family:var(--mono)}
header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
header svg{flex:none;filter:drop-shadow(0 0 6px var(--glow))}
.hd{flex:1 1 240px;min-width:0}
.chip{display:inline-block;font-size:.8rem;font-weight:600;padding:1px 10px;border-radius:99px;color:var(--ok);
background:var(--chip);border:1px solid rgba(57,230,160,.45);margin:2px 4px 2px 0;white-space:normal;overflow-wrap:anywhere;max-width:100%;font-family:var(--mono)}
.chip.sans{font-family:inherit}
.chip.nw{white-space:nowrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:0;min-width:0;
box-shadow:0 0 14px rgba(196,77,255,.18),inset 0 0 18px rgba(196,77,255,.05)}
.stat{animation:glow 4s ease-in-out infinite alternate}
@keyframes glow{from{box-shadow:0 0 8px rgba(196,77,255,.15),inset 0 0 14px rgba(196,77,255,.04);border-color:rgba(170,90,255,.3)}
to{box-shadow:0 0 22px rgba(255,79,216,.32),inset 0 0 22px rgba(255,79,216,.08);border-color:rgba(255,79,216,.6)}}
.sec{margin:16px 0}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:14px 0}
.stat .lbl{color:var(--mut);font-size:.88rem}
.big{font-size:2.4rem;font-weight:700;line-height:1.15;margin:4px 0;color:var(--fg);text-shadow:0 0 14px rgba(196,77,255,.7);overflow-wrap:anywhere}
.risk .big{font-family:inherit;font-size:2rem}
.risk.ok{border-color:rgba(57,230,160,.6)}.risk.ok .big{color:var(--ok);text-shadow:0 0 14px rgba(57,230,160,.5)}
.risk.warn{border-color:rgba(255,181,71,.7)}.risk.warn .big{color:var(--warn);text-shadow:0 0 14px rgba(255,181,71,.5)}
.risk.fail{border-color:rgba(255,79,123,.8);background:linear-gradient(135deg,#3a0b2c,#140a2a 75%)}
.risk.fail .big{color:var(--fail);text-shadow:0 0 16px rgba(255,79,123,.7)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
table{border-collapse:collapse;width:100%}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid rgba(170,90,255,.18);overflow-wrap:anywhere;vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:.85rem}td.n,th.n{text-align:right;white-space:nowrap}
.pct{height:6px;border-radius:3px;background:rgba(170,90,255,.18);margin-top:4px;overflow:hidden}
.pct i{display:block;height:100%;background:linear-gradient(90deg,var(--glow),var(--glow2))}
.bars{display:flex;align-items:flex-end;gap:2px;height:110px;border-bottom:1px solid var(--line)}
.bars span{flex:1;min-width:2px;background:linear-gradient(var(--glow2),var(--glow));min-height:2px;border-radius:2px 2px 0 0;
box-shadow:0 0 6px rgba(255,79,216,.5)}
.tag{display:inline-block;font-weight:700;font-size:.82rem;padding:0 8px;border:1px solid var(--line);border-radius:6px;margin-right:6px;white-space:nowrap}
.fail .tag{border-color:var(--fail);color:var(--fail)}.warn .tag{border-color:var(--warn);color:var(--warn)}
.ok .tag{border-color:var(--ok);color:var(--ok)}.info .tag{color:var(--mut)}
.item{padding:10px 0;border-bottom:1px solid rgba(170,90,255,.18);overflow-wrap:anywhere}.item:last-child{border:0}
.fixtxt{margin-top:6px}.fixtxt .h{font-size:.85rem;color:var(--mut)}
.fixbox{margin-top:8px;border:1px dashed rgba(196,77,255,.55);border-radius:10px;padding:8px 10px;background:rgba(196,77,255,.07)}
.fixbox .h{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:.85rem;color:var(--mut)}
pre{margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:.88rem;color:var(--fg)}
button.copy{font:inherit;font-size:.82rem;color:var(--fg);background:rgba(196,77,255,.2);border:1px solid var(--glow);
border-radius:8px;padding:2px 12px;cursor:pointer;min-height:32px}
button.copy:hover{background:rgba(255,79,216,.3)}
button.copy:focus-visible{outline:2px solid var(--glow2);outline-offset:2px}
svg.map{width:100%;height:auto;display:block;background:#0e0720;border-radius:10px}
.land{fill:#2a1650;stroke:#4b2a8a;stroke-width:.6}
.dot{fill:var(--glow2);fill-opacity:.85;stroke:#fff;stroke-opacity:.6;stroke-width:.8;filter:drop-shadow(0 0 4px var(--glow2))}
.arc{fill:none;stroke:var(--glow2);stroke-width:1.4;stroke-linecap:round;opacity:.85;stroke-dasharray:1;stroke-dashoffset:0;
animation:draw 1.6s ease-out both;animation-delay:var(--d,0s)}
@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
.tgt{fill:var(--ok);filter:drop-shadow(0 0 5px var(--ok))}
.pulse{fill:none;stroke:var(--ok);stroke-width:1.5;transform-box:fill-box;transform-origin:center;animation:pulse 2s ease-out infinite}
@keyframes pulse{from{transform:scale(1);opacity:.9}to{transform:scale(4);opacity:0}}
.trav{fill:#fff}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px;font-size:.9rem}
.legend span{white-space:nowrap}.legend b{font-family:var(--mono);color:var(--glow2)}
.nomap{margin-top:10px;color:var(--warn);font-size:.92rem}
footer{margin:22px 0 8px;color:var(--mut);font-size:.82rem;overflow-wrap:anywhere}
.area{margin-bottom:6px;font-weight:700}
@media (max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}}
@media (max-width:720px){.stats,.grid2{grid-template-columns:1fr}.big{font-size:2.1rem}.wrap{padding:12px}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.trav{display:none}.arc{stroke-dashoffset:0}}
"""

JS = """
(function(){try{
var rm=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
var bs=document.querySelectorAll('button.copy');
for(var i=0;i<bs.length;i++)bs[i].addEventListener('click',function(){var b=this,t=b.parentNode.parentNode.querySelector('pre');
if(!t)return;var s=t.textContent,ok=function(){var o=b.textContent;b.textContent='คัดลอกแล้ว ✓';setTimeout(function(){b.textContent=o},1500)};
try{if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(s).then(ok,function(){})}
else{var a=document.createElement('textarea');a.value=s;document.body.appendChild(a);a.select();document.execCommand('copy');document.body.removeChild(a);ok()}}catch(e){}});
if(rm)return;
var ns=document.querySelectorAll('[data-n]');
for(var j=0;j<ns.length;j++)(function(el){var n=parseInt(el.getAttribute('data-n'),10);if(!(n>0))return;var t0=null;
function f(t){if(t0===null)t0=t;var p=Math.min(1,(t-t0)/900);el.textContent=Math.round(n*(1-Math.pow(1-p,3))).toLocaleString('en-US');
if(p<1)requestAnimationFrame(f)}el.textContent='0';requestAnimationFrame(f)})(ns[j]);
}catch(e){}})();
"""

SHIELD = ('<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#c44dff" stroke-width="1.6" '
          'stroke-linejoin="round" aria-hidden="true"><path d="M12 2.5 4.5 5.5v6c0 4.7 3.1 8.2 7.5 10 4.4-1.8 7.5-5.3 7.5-10v-6z" '
          'fill="rgba(196,77,255,.15)"/><path d="m8.6 12.2 2.4 2.4 4.4-4.8" stroke="#39e6a0" stroke-width="2" '
          'stroke-linecap="round"/></svg>')


def _n(v):
    try:
        return int(v)
    except Exception:
        return 0


def _num(v, key=""):
    if v is None:
        return '<span class="big num">—</span>'
    return f'<span class="big num" data-n="{_n(v)}">{_n(v):,}</span>'


def _fix_block(fix, cmd, title):
    s = ""
    if fix:
        s += f'<div class="fixtxt"><div class="h">วิธีแก้</div><div>{_e(fix)}</div></div>'
    if cmd:
        s += ('<div class="fixbox"><div class="h"><span>คำสั่ง</span>'
              f'<button type="button" class="copy" data-copy="1" aria-label="{_e("คัดลอกคำสั่ง: " + str(title), quote=True)}">คัดลอก</button></div>'
              f'<pre>{_e(cmd)}</pre></div>')
    return s


def _item(f, with_fix=True):
    lv = f.get("level", "info")
    s = f'<div class="item {_e(lv)}"><span class="tag">{_e(MARK.get(lv, lv))}</span><b>{_e(f.get("title", ""))}</b>'
    if f.get("detail"):
        s += f'<div class="mut">{_e(f["detail"])}</div>'
    if with_fix and (f.get("fix") or f.get("cmd")):
        s += _fix_block(f.get("fix", ""), f.get("cmd", ""), f.get("title", ""))
    return s + "</div>"


def _chips(ips):
    return "".join(f'<span class="chip">{_e(str(i))}</span>' for i in ips)


def _stats(allf, ov, summary, ssh, owners):
    icon, word, _ = VERDICT[ov]
    nfail = sum(f["level"] == "fail" for f in allf)
    nwarn = sum(f["level"] == "warn" for f in allf)
    real = isinstance(summary, dict) and not summary.get("_error")
    total = summary.get("total", 0) if real else None
    own_web = 0
    if real:
        own_web = min(owner_total(summary.get("top_ips"), owners), _n(total))
        total = _n(total) - own_web
    top = ""
    if real and summary.get("by_kind"):
        k, n = max(summary["by_kind"].items(), key=lambda kv: kv[1])
        top = f"มากสุด: {KIND_TH.get(k, k)} {_n(n):,}"
    if real and total == 0:
        top = ""
    days = f"{_n(summary.get('days'))} วัน" if real and summary.get("days") else "30 วัน"
    own_ssh = 0
    sshn = None
    if ssh:
        own_ssh = owner_total(ssh.get("failed_ips"), owners)
        sshn = max(0, _n(ssh.get("failed")) + _n(ssh.get("invalid_user")) - own_ssh)
    web_note = f" (+{own_web:,} ครั้งจากเจ้าของเครื่อง ไม่นับ)" if own_web > 0 else ""
    ssh_note = f" (+{own_ssh:,} ครั้งจากเจ้าของเครื่อง ไม่นับ)" if own_ssh > 0 else ""
    return (
        '<div class="stats">'
        f'<div class="card stat"><div class="lbl">การโจมตีเว็บที่ถูกบล็อก</div>{_num(total)}'
        f'<div class="mut">ใน {_e(days)}{" · " + _e(top) if top else ""}{_e(web_note)}</div></div>'
        f'<div class="card stat"><div class="lbl">คนพยายามเดารหัส SSH</div>{_num(sshn)}'
        f'<div class="mut">{("ครั้ง ใน 30 วัน" + _e(ssh_note)) if ssh else "อ่าน log SSH ไม่ได้"}</div></div>'
        f'<div class="card stat risk {ov}"><div class="lbl">ระดับความเสี่ยง</div>'
        f'<div class="big">{icon} {_e(word)}</div>'
        f'<div class="mut">{nfail} เรื่องต้องแก้ · {nwarn} เรื่องควรดู</div></div>'
        f'<div class="card stat"><div class="lbl">IP เจ้าของเครื่อง</div>'
        f'<div style="margin:8px 0">{_chips(owners) or "<span class=mut>ไม่ทราบ</span>"}</div>'
        '<div class="mut">ไม่นับเป็นผู้โจมตี</div></div></div>')


def _todo(allf):
    todo = sorted((f for f in allf if f["level"] in ("warn", "fail")), key=lambda f: f["level"] != "fail")
    body = "".join(_item(f) for f in todo) or '<div class="item ok"><span class="tag">✓ ผ่าน</span>ไม่มีเรื่องที่ต้องแก้</div>'
    return f'<section class="card sec"><h2>ควรแก้อะไร</h2>{body}</section>'


def _arc(x1, y1, x2, y2):
    dist = math.hypot(x2 - x1, y2 - y1)
    cx, cy = (x1 + x2) / 2, min(y1, y2) - dist * 0.28
    return f"M{x1:.1f} {y1:.1f}Q{cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}"


def _map(rows):
    try:
        land = geo.land_path(MAP_W, MAP_H)
    except Exception:
        land = ""
    by_cc = {}
    for r in rows or []:
        if r.get("owner") or not r.get("cc"):
            continue
        d = by_cc.setdefault(r["cc"], {"n": 0, "name": r.get("country") or r["cc"]})
        d["n"] += _n(r.get("n"))
    items = sorted(by_cc.items(), key=lambda kv: -kv[1]["n"])
    bx, by = geo.project(BKK[0], BKK[1], MAP_W, MAP_H)
    arcs, dots, legend = [], [], []
    mx = max([v["n"] for _, v in items] or [1]) or 1
    for i, (cc, v) in enumerate(items):
        c = geo.centroid(cc)
        if not c:
            continue
        x, y = geo.project(c[0], c[1], MAP_W, MAP_H)
        d = _arc(x, y, bx, by)
        delay = f"{i * 0.25:.2f}s"
        r = 4 + 9 * math.sqrt(v["n"] / mx)
        arcs.append(f'<path class="arc" pathLength="1" d="{d}" style="--d:{delay}"/>'
                    f'<circle class="trav" r="2.2"><animateMotion dur="2.4s" begin="{i * 0.25 + 1.6:.2f}s" repeatCount="indefinite" path="{d}"/></circle>')
        dots.append(f'<circle class="dot" data-cc="{_e(cc)}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}">'
                    f'<title>{_e(v["name"])}: {v["n"]:,}</title></circle>')
    for cc, v in items[:5]:
        legend.append(f'<span>{_e(v["name"])} <b>{v["n"]:,}</b></span>')
    svg = ""
    if land:
        svg = (f'<svg class="map" viewBox="0 0 {MAP_W} {MAP_H}" role="img" aria-label="แผนที่โลกแสดงที่มาของการโจมตีไปยังกรุงเทพ">'
               f'<path class="land" d="{land}"/>{"".join(arcs)}{"".join(dots)}'
               f'<circle class="pulse" cx="{bx:.1f}" cy="{by:.1f}" r="5"/><circle class="tgt" cx="{bx:.1f}" cy="{by:.1f}" r="5">'
               '<title>กรุงเทพ</title></circle></svg>')
    note = ""
    if not dots and geo.available():
        note = '<div class="nomap">ยังไม่มีผู้โจมตีนอกบ้านให้แสดง</div>'
    elif not dots:
        note = ('<div class="nomap">! ยังไม่มีข้อมูลประเทศ (ยังไม่มีฐานข้อมูล IP) '
                'ดาวน์โหลดฐานข้อมูลด้วย update_geo.bat</div>')
    leg = f'<div class="legend">{"".join(legend)}</div>' if legend else ""
    return f'<section class="card sec"><h2>แผนที่ที่มาของการโจมตี</h2>{svg}{leg}{note}</section>'


def _charts(summary, owners=()):
    if not (isinstance(summary, dict) and not summary.get("_error")):
        return ('<section class="card sec"><h2>ยอดโจมตีรายวัน</h2><div class="mut">'
                'ต่อ Pi ไม่ได้ หรือยังไม่มีข้อมูล ยอดการโจมตีจะเริ่มนับหลังอัปเดตเซิร์ฟเวอร์</div></section>')
    by_day = summary.get("by_day") or []
    mx = max([_n(d.get("n")) for d in by_day] or [0]) or 1
    bars = "".join(f'<span style="height:{max(3, round(100 * _n(d.get("n")) / mx))}%" '
                   f'title="{_e(str(d.get("day", "")))}: {_n(d.get("n"))}"></span>' for d in by_day)
    left = '<h2>ยอดโจมตีรายวัน</h2>'
    if bars:
        d0, d1 = str(by_day[0].get("day", "")), str(by_day[-1].get("day", ""))
        own = min(owner_total(summary.get("top_ips"), owners), _n(summary.get("total")))
        note = f" (รวม {own:,} ครั้งจากเจ้าของเครื่อง นับในกราฟนี้)" if own > 0 else ""
        left += (f'<div class="bars" role="img" aria-label="{_e(f"ยอดบล็อกรายวัน {d0} ถึง {d1} สูงสุด {mx:,} ครั้งต่อวัน", quote=True)}">{bars}</div>'
                 f'<div class="mut">{_e(d0)} ถึง {_e(d1)} '
                 f'(สูงสุด {mx:,} ครั้ง/วัน){_e(note)}</div>')
    else:
        left += '<div class="mut">ยังไม่มีข้อมูลรายวัน</div>'
    sc = _n(summary.get("self_checks"))
    kinds = sorted(((k, _n(n)) for k, n in (summary.get("by_kind") or {}).items() if _n(n)), key=lambda kv: -kv[1])
    tot = sum(n for _, n in kinds) or 1
    rows = "".join(f'<tr><td>{_e(KIND_TH.get(k, k))}<div class="pct"><i style="width:{100 * n / tot:.0f}%"></i></div></td>'
                   f'<td class="n">{n:,}</td><td class="n">{100 * n / tot:.0f}%</td></tr>' for k, n in kinds)
    right = ('<h2>ชนิดการโจมตี</h2>' + (f'<table><tr><th>ชนิด</th><th class="n">ครั้ง</th><th class="n">%</th></tr>{rows}</table>'
                                         if rows else '<div class="mut">ยังไม่มีข้อมูล</div>'))
    return f'<div class="grid2 sec"><section class="card">{left}</section><section class="card">{right}</section></div>'


def _table(head, cols, rows):
    if not rows:
        return ""
    th = "".join(f'<th{" class=n" if i else ""}>{h}</th>' for i, h in enumerate(cols))
    return f'<section class="card"><h2>{head}</h2><table><tr>{th}</tr>{"".join(rows)}</table></section>'


def _tables(summary, ssh, rows, owners):
    real = isinstance(summary, dict) and not summary.get("_error")
    cc_of = {r["ip"]: r for r in rows or []}
    ipr = []
    for i in (summary.get("top_ips") or []) if real else []:
        ip = str(i.get("ip", ""))
        g = cc_of.get(ip) or {}
        own = bool(g.get("owner")) or ip in owners
        chip = ' <span class="chip sans nw">เจ้าของ</span>' if own else ""
        ipr.append(f'<tr><td class="num">{_e(ip)}{chip}</td><td>{_e(g.get("country") or "—")}</td>'
                   f'<td class="n">{_n(i.get("n")):,}</td></tr>')
    pr = [f'<tr><td class="num">{_e(str(i.get("path", "")))}</td><td class="n">{_n(i.get("n")):,}</td></tr>'
          for i in ((summary.get("top_paths") or []) if real else [])]
    ur = [f'<tr><td class="num">{_e(str(i.get("user", "")))}</td><td class="n">{_n(i.get("n")):,}</td></tr>'
          for i in ((ssh or {}).get("users_tried") or [])]
    parts = [_table("IP ที่ยิงมากสุด", ["IP", "ประเทศ", "ครั้ง"], ipr),
             _table("path ที่โดนมากสุด", ["path", "ครั้ง"], pr),
             _table("ชื่อผู้ใช้ SSH ที่ถูกลองเดา", ["ชื่อผู้ใช้", "ครั้ง"], ur)]
    parts = [p for p in parts if p]
    return f'<div class="grid2 sec">{"".join(parts)}</div>' if parts else ""


def render(target, sections, summary, generated, extra=None):
    extra = extra or {}
    ssh = extra.get("ssh")
    owners = [str(x) for x in (extra.get("owner_ips") or [])]
    rows = extra.get("geo") or []
    allf = [f for fs in sections.values() for f in fs]
    ov = overall(allf)
    real = isinstance(summary, dict) and not summary.get("_error")
    sc = _n(summary.get("self_checks")) if real else 0
    foot = ""
    if sc > 0:
        foot += f"ไม่นับการตรวจของโปรแกรมนี้เอง {sc:,} ครั้ง<br>"
    foot += f"{_e(CREDIT)}<br>สร้างเมื่อ {_e(generated)}"
    allsec = "".join(
        f'<div class="area">{_e(AREA_TH.get(a, a))}</div>' + ("".join(_item(f, False) for f in fs) or '<div class="mut">ไม่มีรายการ</div>')
        for a, fs in sections.items())
    p = [f'<!doctype html><html lang="th"><head><meta charset="utf-8">'
         f'<meta name="viewport" content="width=device-width,initial-scale=1">'
         "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:\">"
         f'<title>ตรวจความปลอดภัย {_e(target)}</title><style>{CSS}</style></head><body><div class="wrap">',
         f'<header>{SHIELD}<div class="hd"><h1>ศูนย์เฝ้าระวังภัย BKK StreetSmart</h1>'
         f'<div class="mut">{_e(TARGET_TH.get(target, target))} · {_e(generated)}</div></div>'
         '<span class="chip sans">ไม่ส่งข้อมูลออกนอกเครื่อง</span></header>',
         _stats(allf, ov, summary, ssh, owners), _todo(allf), _map(rows), _charts(summary, owners),
         _tables(summary, ssh, rows, owners),
         f'<section class="card sec"><h2>ตรวจทุกข้อ</h2>{allsec}</section>',
         f'<footer>{foot}</footer>',
         f'</div><script type="text/javascript">{JS}</script></body></html>']
    return "".join(p)

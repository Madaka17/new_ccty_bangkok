"""The live attack wall page: one self-contained HTML string (inline CSS/JS/SVG, no external URLs).

All event text is put into the DOM with textContent, never innerHTML.
"""
from html import escape as _e

from . import geo
from .report import BKK, CREDIT, CSS as REPORT_CSS, MAP_H, MAP_W

CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'self'"

CSS = REPORT_CSS + """
.top{display:flex;gap:10px 14px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.top h1{flex:1 1 220px;font-family:var(--mono);letter-spacing:.5px;text-shadow:0 0 12px rgba(196,77,255,.7)}
.pill{display:inline-flex;gap:6px;align-items:center;font-size:.9rem;font-weight:600;padding:2px 12px;border-radius:99px;
border:1px solid var(--line);background:rgba(196,77,255,.1);white-space:nowrap}
.pill.ok{color:var(--ok);border-color:rgba(57,230,160,.55);background:var(--chip)}
.pill.warn{color:var(--warn);border-color:rgba(255,181,71,.6)}
.pill.fail{color:var(--fail);border-color:rgba(255,79,123,.7)}
.pill.off{color:var(--mut)}
.wrap{max-width:1600px;min-height:100vh;display:flex;flex-direction:column}
.wall{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:14px;align-items:stretch;flex:none;
grid-template-rows:minmax(0,1fr);height:calc(100vh - 270px);min-height:420px}
.wall .card{margin:0;display:flex;flex-direction:column;min-height:0;overflow:hidden}
.mapbox{flex:1 1 auto;position:relative;min-height:0;overflow:hidden}
.mapbox svg.map{position:absolute;inset:0;width:100%;height:100%}
.edgelbl{position:absolute;left:10px;bottom:8px;font-family:var(--mono);font-size:13px;color:var(--mut);
background:rgba(11,6,24,.75);padding:1px 8px;border-radius:6px;pointer-events:none}
.stats{margin:10px 0 14px}
.stat .big{font-size:2.2rem}
.stat{animation:none}
.arc{stroke-dasharray:1;stroke-dashoffset:1;opacity:1;animation:fire 1.1s ease-out forwards,fade 3.5s ease-in 1.1s forwards}
@keyframes fire{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes fade{from{opacity:.9}to{opacity:0}}
.burst{fill:none;stroke:var(--glow2);stroke-width:1.6;transform-box:fill-box;transform-origin:center;animation:burst 1.4s ease-out forwards}
.burst.end{stroke:var(--ok)}
@keyframes burst{from{transform:scale(.6);opacity:.95}to{transform:scale(4.5);opacity:0}}
.dot{transition:r .6s ease,fill-opacity 2s linear}
.feedhd{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.feedhd label{display:inline-flex;gap:8px;align-items:center;min-height:32px;cursor:pointer;font-size:.9rem;color:var(--mut)}
.feedhd input{width:18px;height:18px;accent-color:#c44dff}
#feed{list-style:none;margin:0;padding:0;flex:1;min-height:0;overflow-y:auto}
#feed li{display:grid;grid-template-columns:auto 1fr;gap:0 10px;padding:7px 4px;border-bottom:1px solid rgba(170,90,255,.18);overflow-wrap:anywhere;
animation:slidein .45s ease-out both}
@keyframes slidein{from{transform:translateX(-14px);opacity:0}to{transform:none;opacity:1}}
#feed .t{font-family:var(--mono);color:var(--mut);font-size:.85rem}
#feed .lb{font-weight:700}
#feed .sub{grid-column:2;font-family:var(--mono);font-size:.85rem;color:var(--mut)}
#feed li.owner{opacity:.7}
#feed.hide-owner li.owner{display:none}
#feed li.ssh .lb::before{content:"SSH \\00b7  ";color:var(--warn)}
#feed li.empty{display:block;color:var(--mut);padding:10px 0;animation:none}
#alerts{display:grid;gap:8px;margin:0 0 12px}
#alerts:empty{margin:0}
.banner{display:flex;gap:10px;align-items:flex-start;justify-content:space-between;padding:10px 14px;border-radius:12px;
border:1px solid var(--warn);background:rgba(255,181,71,.1);color:var(--fg);overflow-wrap:anywhere}
.banner.crit{border-color:var(--fail);background:rgba(255,79,123,.14)}
.banner b{font-family:var(--mono);margin-right:6px}
.banner.crit b{color:var(--fail)}.banner:not(.crit) b{color:var(--warn)}
.banner button{flex:none;font:inherit;color:var(--fg);background:rgba(196,77,255,.2);border:1px solid var(--glow);border-radius:8px;
min-height:32px;padding:0 12px;cursor:pointer}
.banner button:focus-visible{outline:2px solid var(--glow2);outline-offset:2px}
@media (max-width:900px){.wall{grid-template-columns:minmax(0,1fr);grid-template-rows:none;height:auto;min-height:0}.mapbox{flex:none;aspect-ratio:2/1}#feed{flex:none;max-height:60vh}}
@media (max-width:720px){.stat .big{font-size:1.8rem}}
@media (prefers-reduced-motion:reduce){#feed li{animation:none}.arc,.burst{display:none}.dot{transition:none}}
"""

JS = r"""
(function(){'use strict';
var W=__W__,H=__H__,BKK=[__BLAT__,__BLON__],MAXARC=30,MAXROW=100;
var UNK='\u0e44\u0e21\u0e48\u0e17\u0e23\u0e32\u0e1a\u0e1b\u0e23\u0e30\u0e40\u0e17\u0e28';
var rm=false;try{rm=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)}catch(e){}
var NS='http://www.w3.org/2000/svg';
function $(i){return document.getElementById(i)}
function proj(lat,lon){return [(lon+180)/360*W,(90-lat)/180*H]}
var B=proj(BKK[0],BKK[1]);
var layer=$('layer'),dots=$('dots'),feed=$('feed'),alertsEl=$('alerts');
var st={since:0,last60:0,ssh60:0,base:null},shown={},arcs=[],dotMap={},cn={};
function el(n,a){var e=document.createElementNS(NS,n);for(var k in a)e.setAttribute(k,a[k]);return e}
function setNum(id,v){var e=$(id);if(!e)return;
if(v===null||v===undefined){e.textContent='\u2014';shown[id]=null;return}
var from=shown[id]||0;shown[id]=v;
if(rm||from===v){e.textContent=v.toLocaleString('en-US');return}
var t0=null;
function f(t){if(t0===null)t0=t;var p=Math.min(1,(t-t0)/600);
e.textContent=Math.round(from+(v-from)*(1-Math.pow(1-p,3))).toLocaleString('en-US');
if(p<1&&shown[id]===v)requestAnimationFrame(f)}
requestAnimationFrame(f)}
function paint(){setNum('n-since',st.since);setNum('n-60',st.last60);setNum('n-base',st.base);setNum('n-ssh',st.ssh60)}
function pill(id,cls,s){var e=$(id);e.className='pill '+cls;e.textContent=s}
var conn='reconnecting',fails=0;
function paintConn(){
if(conn==='connected')pill('p-conn','ok','\u25CF \u0e2a\u0e14');
else if(fails>=3)pill('p-conn','fail','\u2717 \u0e15\u0e48\u0e2d Pi \u0e44\u0e21\u0e48\u0e44\u0e14\u0e49');
else pill('p-conn','warn','\u25CB \u0e01\u0e33\u0e25\u0e31\u0e07\u0e15\u0e48\u0e2d\u0e43\u0e2b\u0e21\u0e48')}
function paintLine(v){
if(v==='on')pill('p-line','ok','LINE \u0e40\u0e1b\u0e34\u0e14');
else if(v==='failed')pill('p-line','fail','LINE \u0e2a\u0e48\u0e07\u0e44\u0e21\u0e48\u0e2a\u0e33\u0e40\u0e23\u0e47\u0e08');
else pill('p-line','off','LINE \u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e44\u0e14\u0e49\u0e15\u0e31\u0e49\u0e07')}
function z(n){return (n<10?'0':'')+n}
function hhmmss(ts){var m=/(\d\d:\d\d:\d\d)/.exec(String(ts||''));if(m)return m[1];
var d=new Date();return z(d.getHours())+':'+z(d.getMinutes())+':'+z(d.getSeconds())}
function txt(tag,cls,s){var e=document.createElement(tag);if(cls)e.className=cls;e.textContent=String(s==null?'':s);return e}
function addRow(ev,animate){
if(ev.kind==='self_check')return;
var emp=$('empty');if(emp)emp.remove();
var li=document.createElement('li');li.className=(ev.owner?'owner ':'')+(ev.type==='ssh'?'ssh':'web');
if(!animate||rm)li.style.animation='none';
li.appendChild(txt('span','t',hhmmss(ev.ts)));
var main=txt('span','lb',ev.label_th||ev.kind||'');
if(ev.owner){main.appendChild(document.createTextNode(' '));main.appendChild(txt('span','chip sans nw','\u0e40\u0e08\u0e49\u0e32\u0e02\u0e2d\u0e07'))}
li.appendChild(main);
var parts=[ev.ip,ev.country||UNK];
if(ev.type==='ssh'){if(ev.user)parts.push('user '+ev.user)}else{if(ev.method)parts.push(ev.method);if(ev.path)parts.push(ev.path)}
li.appendChild(txt('span','sub',parts.join(' \u00b7 ')));
feed.insertBefore(li,feed.firstChild);
while(feed.children.length>MAXROW)feed.removeChild(feed.lastChild)}
function arcD(x1,y1,x2,y2){var d=Math.hypot(x2-x1,y2-y1),cx=(x1+x2)/2,cy=Math.min(y1,y2)-d*0.28;
return 'M'+x1.toFixed(1)+' '+y1.toFixed(1)+'Q'+cx.toFixed(1)+' '+cy.toFixed(1)+' '+x2.toFixed(1)+' '+y2.toFixed(1)}
function later(node,ms){setTimeout(function(){if(node.parentNode)node.parentNode.removeChild(node)},ms)}
function fire(x,y){
if(rm)return;
var p=el('path',{'class':'arc',pathLength:'1',d:arcD(x,y,B[0],B[1])});
layer.appendChild(p);arcs.push(p);
while(arcs.length>MAXARC){var o=arcs.shift();if(o.parentNode)o.parentNode.removeChild(o)}
later(p,5000);
var b1=el('circle',{'class':'burst',cx:x.toFixed(1),cy:y.toFixed(1),r:5});layer.appendChild(b1);later(b1,1500);
var b2=el('circle',{'class':'burst end',cx:B[0].toFixed(1),cy:B[1].toFixed(1),r:5});layer.appendChild(b2);later(b2,1500)}
function dotFor(key,name,x,y,n,mx){
var d=dotMap[key];
if(!d){var c=el('circle',{'class':'dot',cx:x.toFixed(1),cy:y.toFixed(1),r:4}),t=el('title',{});
c.appendChild(t);dots.appendChild(c);d={c:c,t:t,n:0};dotMap[key]=d}
d.n=n;d.c.setAttribute('r',(4+9*Math.sqrt(n/Math.max(mx,1))).toFixed(1));
d.c.setAttribute('fill-opacity','0.9');d.t.textContent=name+': '+n;
if(!rm){clearTimeout(d.f);d.f=setTimeout(function(){d.c.setAttribute('fill-opacity','0.45')},20000)}}
function bump(ev){
var key=ev.cc||'??',known=(ev.lat!=null&&ev.lon!=null);
var xy=known?proj(ev.lat,ev.lon):[26,H-26];
cn[key]=(cn[key]||0)+1;var mx=0;for(var k in cn)if(cn[k]>mx)mx=cn[k];
dotFor(key,ev.country||UNK,xy[0],xy[1],cn[key],mx);
fire(xy[0],xy[1])}
function onEvent(ev){
if(ev.kind==='self_check')return;
addRow(ev,true);
if(ev.owner)return;
st.since++;st.last60++;if(ev.type==='ssh'&&(ev.event==='failed'||ev.event==='invalid'))st.ssh60++;
paint();bump(ev)}
function banner(a){
var crit=(a.level==='critical'||a.level==='crit'||a.level==='fail'||a.level==='error');
var d=document.createElement('div');d.className='banner'+(crit?' crit':'');d.setAttribute('role','alert');
var m=document.createElement('div');m.appendChild(txt('b','',crit?'\u2717':'!'));m.appendChild(document.createTextNode(String(a.text||'')));
var x=txt('button','','\u0e1b\u0e34\u0e14');x.type='button';x.setAttribute('aria-label','\u0e1b\u0e34\u0e14\u0e01\u0e32\u0e23\u0e41\u0e08\u0e49\u0e07\u0e40\u0e15\u0e37\u0e2d\u0e19');
x.addEventListener('click',function(){d.remove()});
d.appendChild(m);d.appendChild(x);alertsEl.insertBefore(d,alertsEl.firstChild);
while(alertsEl.children.length>5)alertsEl.removeChild(alertsEl.lastChild)}
function showEmpty(){if($('empty')||feed.querySelector('li'))return;
var li=txt('li','empty','\u0e22\u0e31\u0e07\u0e44\u0e21\u0e48\u0e21\u0e35\u0e40\u0e2b\u0e15\u0e38\u0e01\u0e32\u0e23\u0e13\u0e4c \u0e23\u0e2d\u0e14\u0e39\u0e2a\u0e14\u0e44\u0e14\u0e49\u0e40\u0e25\u0e22');li.id='empty';feed.appendChild(li)}
function load(){
fetch('/state',{cache:'no-store'}).then(function(r){return r.json()}).then(function(s){
st.since=s.since_start||0;st.last60=s.last60||0;st.ssh60=s.ssh60||0;st.base=(s.baseline30==null?null:s.baseline30);
conn=s.status==='connected'?'connected':'reconnecting';fails=s.failures||0;paintConn();paintLine(s.line);paint();
cn={};var mx=0;(s.countries||[]).forEach(function(c){if(c.n>mx)mx=c.n});
(s.countries||[]).forEach(function(c){var k=c.cc||'??';cn[k]=c.n;
var xy=(c.lat!=null&&c.lon!=null)?proj(c.lat,c.lon):[26,H-26];dotFor(k,c.country||k,xy[0],xy[1],c.n,mx)});
if(!feed.querySelector('li:not(.empty)')){(s.events||[]).slice(0,MAXROW).reverse().forEach(function(e){addRow(e,false)})}
if(!alertsEl.children.length)(s.alerts||[]).slice(0,3).reverse().forEach(banner);
showEmpty()}).catch(function(){})}
$('hide-owner').addEventListener('change',function(){feed.className=this.checked?'hide-owner':''});
feed.className='hide-owner';
function connect(){
var es;try{es=new EventSource('/events')}catch(e){return}
es.onopen=function(){load()};
es.onerror=function(){conn='reconnecting';paintConn()};
es.onmessage=function(m){var d;try{d=JSON.parse(m.data)}catch(e){return}
if(d.type==='status'){conn=d.status==='connected'?'connected':'reconnecting';if(conn==='connected')fails=0;else fails++;paintConn()}
else if(d.type==='alert'){banner(d)}
else if(d.type==='web'||d.type==='ssh'){onEvent(d)}}}
paintConn();paintLine('off');showEmpty();load();connect();
setInterval(load,30000);
})();
"""


def build_page(target="production"):
    try:
        land = geo.land_path(MAP_W, MAP_H)
    except Exception:
        land = ""
    bx, by = geo.project(BKK[0], BKK[1], MAP_W, MAP_H)
    js = (JS.replace("__W__", str(MAP_W)).replace("__H__", str(MAP_H))
          .replace("__BLAT__", str(BKK[0])).replace("__BLON__", str(BKK[1])))
    tgt = "เว็บทดสอบ (test)" if target == "test" else "เว็บจริง (production)"
    nomap = "" if land else '<div class="nomap">! ยังไม่มีข้อมูลแผนที่ (update_geo.bat) ยังเห็นตัวเลขและรายการได้</div>'
    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>BKK Security Live</title>
<style>{CSS}</style></head><body><div class="wrap">
<div class="top"><h1>BKK Security Live</h1>
<span id="p-conn" class="pill warn">○ กำลังต่อใหม่</span><span id="p-line" class="pill off">LINE ยังไม่ได้ตั้ง</span>
<span class="mut">{_e(tgt)}</span></div>
<div id="alerts" aria-live="polite"></div>
<div class="stats">
<div class="card stat"><div class="lbl">โจมตีตั้งแต่เปิดหน้านี้</div><span class="big num" id="n-since">0</span><div class="mut">ครั้ง (ไม่นับเจ้าของ)</div></div>
<div class="card stat"><div class="lbl">60 นาทีล่าสุด</div><span class="big num" id="n-60">0</span><div class="mut">ครั้ง</div></div>
<div class="card stat"><div class="lbl">30 วัน (นอกบ้าน)</div><span class="big num" id="n-base">—</span><div class="mut">ครั้งที่ถูกบล็อก</div></div>
<div class="card stat"><div class="lbl">เดารหัส SSH 60 นาที</div><span class="big num" id="n-ssh">0</span><div class="mut">ครั้ง</div></div>
</div>
<div class="wall">
<section class="card mapcard"><h2>ที่มาของการโจมตี</h2>
<div class="mapbox"><svg class="map" preserveAspectRatio="xMidYMid meet" viewBox="0 0 {MAP_W} {MAP_H}" role="img" aria-label="แผนที่โลกแสดงการโจมตีสดไปยังกรุงเทพ">
<path class="land" d="{land}"/><g id="dots"></g><g id="layer"></g>
<circle class="pulse" cx="{bx:.1f}" cy="{by:.1f}" r="5"/><circle class="tgt" cx="{bx:.1f}" cy="{by:.1f}" r="5"><title>กรุงเทพ</title></circle>
</svg><span class="edgelbl">ไม่ทราบประเทศ</span></div>{nomap}</section>
<section class="card"><div class="feedhd"><h2 style="margin:0">เหตุการณ์สด</h2>
<label><input type="checkbox" id="hide-owner" checked> ซ่อนของเจ้าของ</label></div>
<ul id="feed" aria-label="รายการเหตุการณ์ล่าสุด"></ul></section>
</div>
<footer>{_e(CREDIT)}</footer>
</div><script>{js}</script></body></html>"""

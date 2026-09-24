"""Slim the BMA risk-map (cpudapp.bangkok.go.th/riskbkk) traffic layers for the Traffic Map.

Reads the raw ArcGIS GeoJSON downloads in cache/riskbkk/ and writes one small GeoJSON per map
layer to web/public/riskbkk/, keeping only a title and a few "label: value" lines per point.

    python local/pipeline/build_riskbkk_layers.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, 'cache', 'riskbkk')
OUT = os.path.join(ROOT, 'web', 'public', 'riskbkk')


def clean(v):
    s = str(v).strip() if v is not None else ''
    return '' if s in ('', 'None', '-') else ' '.join(s.split())


def load(fname):
    return json.load(open(os.path.join(SRC, fname), encoding='utf-8'))['features']


def point(f, lat_key=None, lng_key=None):
    g = f.get('geometry')
    if g and g.get('type') == 'Point':
        return g['coordinates'][:2]
    p = f['properties']
    try:
        return [float(p[lng_key]), float(p[lat_key])]
    except (KeyError, TypeError, ValueError):
        return None


def _rings(g):
    return [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']


def _inside(x, y, ring):
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


# BMA district polygons (outer ring + holes), for a `district` on every point
DISTRICTS = []
for _f in load('Risk_Fire_Public__ขอบเขตของเขต.geojson'):
    for poly in _rings(_f['geometry']):
        xs, ys = [c[0] for c in poly[0]], [c[1] for c in poly[0]]
        DISTRICTS.append((_f['properties']['DISTRICT_N'], (min(xs), min(ys), max(xs), max(ys)), poly))


def district_of(x, y):
    for name, (x0, y0, x1, y1), poly in DISTRICTS:
        if x0 <= x <= x1 and y0 <= y <= y1 and _inside(x, y, poly[0]) and not any(_inside(x, y, h) for h in poly[1:]):
            return name
    return ''


def build(name, feats, title, info, lat_key=None, lng_key=None, extra=None):
    out = []
    for f in feats:
        c = point(f, lat_key, lng_key)
        if not c:
            continue
        p = f['properties']
        props = {'title': clean(title(p)), 'info': [f'{k}: {clean(v)}' for k, v in info(p) if clean(v)],
                 'district': district_of(c[0], c[1])}
        if extra:
            props.update(extra(p))
        out.append({'type': 'Feature', 'properties': props,
                    'geometry': {'type': 'Point', 'coordinates': [round(c[0], 5), round(c[1], 5)]}})
    path = os.path.join(OUT, f'{name}.geojson')
    json.dump({'type': 'FeatureCollection', 'features': out}, open(path, 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    print(f'{name}: {len(out)} points, {os.path.getsize(path) // 1024} KB')


os.makedirs(OUT, exist_ok=True)

# ITIC accident events 2020-01 .. 2022-05 (BkkAccidentNew = the TYPE 3 "accident" subset of BkkAccident)
build('accident', load('risk_all__Risk_All_-_RISK_ADMIN_BkkAccidentNew.geojson'),
      lambda p: clean(p['TITLE'])[:60], lambda p: [('เวลา', (p.get('START_') or '')[:16])])  # 35k points: keep it small

build('risk100', load('risk_all__Risk_All_-_RISK_ADMIN_RISK_ADMIN_Risk100Transport.geojson'),
      lambda p: p['PROPERTI_1'], lambda p: [('เขต', p['PROPERTI_2']), ('จำนวนอุบัติเหตุ', f"{p['NCASE']} ครั้ง")])

build('risk100_solve', load('risk_all__Risk_All_-_RISK_ADMIN_Transport_Solve_Result.geojson'),
      lambda p: p['DETAIL'], lambda p: [('เขต', p['DNAME']), ('สถานะ', p['SOLVE'])],
      extra=lambda p: {'done': p['SOLVE'] == 'ดำเนินการแล้วเสร็จ'})

acc = []
for year in ('2566', '2567', '2568'):
    for f in load(f'Risk_Transport_Public__จ_ดเส_ยงอ_บ_ต_เหต_ป_{year}.geojson'):
        f['properties']['_year'] = year
        acc.append(f)
build('accident_risk', acc, lambda p: p['POINT'],
      lambda p: [('ปี', p['_year']), ('เขต', p.get('DISTRICT')),
                 ('สาเหตุ', p.get('สาเหตุ_รายละเอียดของปัญหา') or p.get('สาเหตุการเกิดอุบัติเหตุ')),
                 ('แนวทางแก้ไข', p.get('แนวทางการแก้ไขเบื้องต้น') or p.get('เเนวทางการแก้ไขเบื้องต้น') or p.get('แนวทางการแก้ไข'))],
      'LATITUDE', 'LONGITUDE')

build('friction', load('Risk_Flood-Public-GI__จ_ดสน_บสน_นสถานท_-_จ_ดฝ_ด.geojson'),
      lambda p: p['DESCRIPTIONSURVEYAREA'],
      lambda p: [('เขต', p['DISTRIC_NAME']), ('ช่วงติด', p['DURINGTRAFFICCONGESTION']), ('สาเหตุ', p['CAUSE']), ('แนวทางแก้ไข', p['SOLUTION'])],
      'LAT', 'LONG_')

build('crosswalk', load('Risk_Flood-Public-GI__จ_ดสน_บสน_นสถานท_-_ทางข_ามม_าลาย.geojson'),
      lambda p: f"ทางม้าลาย {clean(p['LOCATION'])}",
      lambda p: [('ถนน', p['ROAD']), ('เขต', p['DISTRICT']), ('จำนวนช่องจราจร', p['NUM_LANE']), ('ไฟกดข้าม', p['PUSH_LIGHT'])],
      'LAT', 'LONG_')

build('rail_crossing', load('Risk_Transport_Public__จ_ดต_ดทางรถไฟ.geojson'),
      lambda p: f"จุดตัดทางรถไฟ {clean(p['RD_NAME'])}", lambda p: [('ประเภท', p['TYPE_DESC']), ('เขต', p['AMPHOE'])],
      'LATITUDE', 'LONGITUDE')

build('bus_stop', load('Risk_Flood-Public-GI__จ_ดสน_บสน_นสถานท_-_ป_ายรถเมล_.geojson'),
      lambda p: p['LOCATION'] or 'ป้ายรถเมล์', lambda p: [('ประเภท', p['NAME'])], 'LAT', 'LONG_')

build('motorcycle_taxi', load('Risk_Flood-Public-GI__จ_ดสน_บสน_นสถานท_-_ว_นมอเตอร_ไซต_.geojson'),
      lambda p: f"วินมอเตอร์ไซค์ {clean(p['MTC_ST_N'])}", lambda p: [('เขต', p['DNAME']), ('จำนวนรถ', p['QUANTITY'])], 'Y', 'X')

build('parking', load('Risk_Flood-Public-GI__จ_ดสน_บสน_นสถานท_-_สถานท_จอดรถ.geojson'),
      lambda p: p['NAMT'], lambda p: [('ที่ตั้ง', p['LOCATION_T']), ('เขต', p['AMP_NAMT'])])

build('construction', load('แผนท_จ_ดเส_ยงแผ_นด_นไหวและอาคารว_บ_ต_เช_งโครงสร_าง__สถานท_ก_อสร_างอาคารขนาดใหญ_อาคารขนาดใหญ_พ_เศษ_และอาคารส_ง.geojson'),
      lambda p: p['การใช้สอย_ครั้ง_'] or 'สถานที่ก่อสร้าง',
      lambda p: [('ถนน', p['ถนน']), ('เขต', p['เขต']), ('จำนวนชั้น', p['ชั้น']), ('สถานะ', p['สถานะปัจจุบัน'])],
      'ละติจูด', 'ลองจิจูด')

build('js100', load('Risk_Transport_Public__จ_ดเก_ดเหต_จราจรว_นน_จากจส100_และ_FM91.geojson'),
      lambda p: p['TITLE'], lambda p: [('รายละเอียด', p['DESCRIPTION'])], 'LATITUDE', 'LONGITUDE')

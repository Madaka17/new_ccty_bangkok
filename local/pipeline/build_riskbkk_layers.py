"""Slim the BMA risk-map (cpudapp.bangkok.go.th/riskbkk) traffic layers for the Traffic Map.

Reads the raw ArcGIS GeoJSON downloads in cache/riskbkk/ (and the Thai RSC accident cases 2566-2568
through rsc_service) and writes one small GeoJSON per map
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

def build_accidents():
    """Thai RSC accident cases 2566-2568 (CE 2023-2025) for all 50 districts, instead of the riskbkk ITIC
    layer (Jan 2563 - May 2565). ~200k cases is too many points for the map, so they are pooled into
    ~110 m cells (3-decimal lat/lon) with the case count `n`; accident_stats.json keeps the per-case
    numbers (district, month, weekday, injured, dead) for riskbkk_agent. Thai RSC has the date only.
    The cells carry short property names, unlike the other layers (see below)."""
    import collections
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date
    sys.path.insert(0, ROOT)
    import rsc_service

    jobs = [(y - 543, d) for y in ACCIDENT_YEARS_BE for d in range(1001, 1051)]
    with ThreadPoolExecutor(8) as ex:
        pages = list(ex.map(lambda a: rsc_service.fetch_district_points(*a)['points'], jobs))
    cells = {}
    stats = {'years_be': list(ACCIDENT_YEARS_BE), 'source': 'Thai RSC (thairsc.com)', 'cases': 0, 'injured': 0, 'dead': 0, 'outside': 0,
             'by_year': collections.Counter(), 'by_month': collections.Counter(), 'by_weekday': collections.Counter(),
             'by_district': collections.defaultdict(lambda: {'cases': 0, 'injured': 0, 'dead': 0})}
    for pts in pages:
        for p in pts:
            try:
                lat, lon = float(p['lat']), float(p['lon'])
                day = date.fromisoformat(p['date'][:10])
            except (KeyError, TypeError, ValueError):
                continue
            # the case's own district name is sometimes another province's: place it by the BMA polygons
            dist = district_of(lon, lat)
            if not dist:
                stats['outside'] += 1
                continue
            inj, dead = int(p.get('injured') or 0), int(p.get('dead') or 0)
            year_be = day.year + 543
            stats['cases'] += 1
            stats['injured'] += inj
            stats['dead'] += dead
            stats['by_year'][year_be] += 1
            stats['by_month'][day.month] += 1
            stats['by_weekday'][day.weekday()] += 1
            row = stats['by_district'][dist]
            row['cases'] += 1
            row['injured'] += inj
            row['dead'] += dead
            c = cells.setdefault((round(lon, 3), round(lat, 3)), {'n': 0, 'inj': 0, 'dead': 0, 'years': collections.Counter(),
                                                                   'district': collections.Counter(), 'place': collections.Counter()})
            c['n'] += 1
            c['inj'] += inj
            c['dead'] += dead
            c['years'][year_be] += 1
            c['district'][dist] += 1
            place = clean(p.get('place')).lstrip('- ').strip()
            if place:
                c['place'][place[:60]] += 1

    # short property names keep ~30k cells small; MapPage builds the popup text from them
    #   n cases, i injured, k killed, y cases per year (ACCIDENT_YEARS_BE order), d district, p commonest place
    out = []
    for (x, y), c in cells.items():
        place = next((pl for pl, _ in c['place'].most_common(3) if 'ไม่ระบุ' not in pl), '')
        props = {'n': c['n'], 'i': c['inj'], 'k': c['dead'], 'y': [c['years'][yr] for yr in ACCIDENT_YEARS_BE],
                 'd': c['district'].most_common(1)[0][0] if c['district'] else ''}
        if place:
            props['p'] = place
        out.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [x, y]}, 'properties': props})
    out.sort(key=lambda f: f['properties']['n'])   # busiest cells drawn last, on top
    path = os.path.join(OUT, 'accident.geojson')
    json.dump({'type': 'FeatureCollection', 'features': out}, open(path, 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))
    print(f'accident: {stats["cases"]} cases ({stats["outside"]} outside Bangkok dropped) in {len(out)} cells, {os.path.getsize(path) // 1024} KB')

    stats['by_year'] = {str(k): v for k, v in sorted(stats['by_year'].items())}
    stats['by_month'] = [stats['by_month'][m] for m in range(1, 13)]
    stats['by_weekday'] = [stats['by_weekday'][d] for d in range(7)]
    stats['by_district'] = dict(sorted(stats['by_district'].items(), key=lambda kv: -kv[1]['cases']))
    stats['top_cells'] = [{'place': f['properties'].get('p', ''), 'district': f['properties']['d'], 'cases': f['properties']['n'],
                           'injured': f['properties']['i'], 'dead': f['properties']['k']} for f in out[::-1][:12]]
    json.dump(stats, open(os.path.join(OUT, 'accident_stats.json'), 'w', encoding='utf-8'), ensure_ascii=False)


ACCIDENT_YEARS_BE = (2566, 2567, 2568)
build_accidents()

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


# BMA temporary shelters (สถานที่พักพิงชั่วคราว) for the "จุดพักพิงใกล้ฉัน" tab of the Water Forecast page.
# Not a map layer: the tab sorts them by distance from the user in the browser, so the capacity, phone
# numbers and facility flags stay as their own fields next to the usual title / info.
SHELTER_FACILITIES = (('ELECTRICITY', 'ไฟฟ้า'), ('PLUMBING', 'ประปา'), ('TOILET', 'ห้องน้ำ'), ('COMMUNICATION', 'สื่อสาร'),
                      ('TRANSPORTATION', 'การเดินทาง'), ('WASTE', 'จัดการขยะ'), ('GROUPS_FACILITIES', 'สิ่งอำนวยความสะดวกกลุ่มเปราะบาง'))


def shelter_address(p):
    vill = clean(p['VILL_NO'])
    parts = [clean(p['ADD_NO']), f"หมู่ {vill}" if vill.isdigit() else vill,
             f"ถ.{clean(p['ROAD'])}" if clean(p['ROAD']) else '', f"แขวง{clean(p['SUBDISTRICT'])}" if clean(p['SUBDISTRICT']) else '',
             f"เขต{clean(p['DISTRICT'])}" if clean(p['DISTRICT']) else '']
    return ' '.join(x for x in parts if x)


build('shelter', load('risk_all__Risk_All_-_RISK_ADMIN_shelter.geojson'),
      lambda p: p['NAME'], lambda p: [('พื้นที่', p['RISK_ADMIN.shelter.AREA']), ('ผู้ติดต่อ', p['CONTRACT_PERSON']), ('ตำแหน่ง', p['POSITION'])],
      'LAT', 'LNG',
      extra=lambda p: {'address': shelter_address(p), 'capacity': p['CAPACITY'] or None,
                       'tel': [t for t in (clean(x) for x in str(p['TEL'] or '').split(',')) if t],
                       'facilities': [label for key, label in SHELTER_FACILITIES if p.get(key) == 1]})

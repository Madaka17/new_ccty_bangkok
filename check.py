import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://traffic.longdo.com/camera.json'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))

items = data.get('item', [])
print(f"Total cameras in Longdo: {len(items)}")

bkk_items = []
for it in items:
    geo = str(it.get('geocode', '')).strip()
    title = it.get('title', '')
    camid = it.get('camid', '')
    # Bangkok check
    if geo.startswith('10') or 'กรุงเทพ' in title or 'กทม' in title:
        bkk_items.append(it)

print(f"Bangkok cameras count: {len(bkk_items)}")
for i, c in enumerate(bkk_items[:15]):
    print(f"{i+1}: [{c.get('camid')}] {c.get('title')} | Org: {c.get('organization')} | HLS: {c.get('hls_url')}")

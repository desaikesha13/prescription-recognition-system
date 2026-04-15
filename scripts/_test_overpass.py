"""Quick Overpass test with small area"""
import requests, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

query = """
[out:json][timeout:15];
node["amenity"="pharmacy"](28.60,77.20,28.65,77.25);
out tags 5;
"""

print("Testing Overpass API (small area near India Gate)...")
try:
    r = requests.post(
        'https://overpass-api.de/api/interpreter',
        data={'data': query},
        timeout=30,
        headers={'User-Agent': 'PrescriptionWebApp/1.0'}
    )
    print(f"HTTP Status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        elems = d.get('elements', [])
        print(f"Found {len(elems)} pharmacies!")
        for e in elems:
            name = e.get('tags', {}).get('name', '?')
            print(f"  - {name}: ({e.get('lat')}, {e.get('lon')})")
        print("\n[PASS] Overpass API is working!")
    else:
        print(f"[FAIL] HTTP {r.status_code}")
except Exception as e:
    print(f"[FAIL] {e}")

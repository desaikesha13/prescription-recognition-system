"""
============================================================================
 FETCH PHARMACIES - OpenStreetMap Overpass API (v2 - City-Based)
============================================================================
 Run:  python fetch_pharmacies.py

 Uses city-center based queries (small radius) instead of large bounding
 boxes to avoid Overpass timeouts. Covers 100+ Indian cities.

 Completely FREE - no API key, no billing needed.
============================================================================
"""

import os
import re
import sys
import io
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

# Fix Windows console encoding + force unbuffered output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

load_dotenv()

# Add project root to sys.path (script moved to scripts/ subdirectory)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHECKPOINT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'fetch_checkpoint.json')
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SLEEP_BETWEEN = 3  # seconds between requests (be respectful to free API)


# ── Indian Cities: (name, lat, lng, search_radius_meters) ────
# Using city centers + radius instead of bounding boxes

INDIA_CITIES = [
    # -- Tier 1: Metros (larger radius) --
    ("Delhi",           28.6139, 77.2090, 15000),
    ("Mumbai South",    18.9388, 72.8354, 10000),
    ("Mumbai North",    19.1764, 72.9488, 10000),
    ("Bangalore",       12.9716, 77.5946, 12000),
    ("Hyderabad",       17.3850, 78.4867, 12000),
    ("Chennai",         13.0827, 80.2707, 12000),
    ("Kolkata",         22.5726, 88.3639, 12000),
    ("Pune",            18.5204, 73.8567, 10000),
    ("Ahmedabad",       23.0225, 72.5714, 10000),

    # -- Tier 2: Major Cities --
    ("Jaipur",          26.9124, 75.7873, 8000),
    ("Lucknow",         26.8467, 80.9462, 8000),
    ("Kanpur",          26.4499, 80.3319, 8000),
    ("Nagpur",          21.1458, 79.0882, 8000),
    ("Indore",          22.7196, 75.8577, 8000),
    ("Bhopal",          23.2599, 77.4126, 8000),
    ("Patna",           25.6093, 85.1376, 8000),
    ("Vadodara",        22.3072, 73.1812, 8000),
    ("Surat",           21.1702, 72.8311, 8000),
    ("Coimbatore",      11.0168, 76.9558, 8000),
    ("Visakhapatnam",   17.6868, 83.2185, 8000),
    ("Kochi",           9.9312,  76.2673, 8000),
    ("Chandigarh",      30.7333, 76.7794, 8000),
    ("Guwahati",        26.1445, 91.7362, 8000),
    ("Bhubaneswar",     20.2961, 85.8245, 8000),
    ("Ranchi",          23.3441, 85.3096, 8000),
    ("Dehradun",        30.3165, 78.0322, 8000),
    ("Thiruvananthapuram", 8.5241, 76.9366, 8000),
    ("Raipur",          21.2514, 81.6296, 8000),

    # -- Tier 3: Other Important Cities --
    ("Agra",            27.1767, 78.0081, 6000),
    ("Varanasi",        25.3176, 82.9739, 6000),
    ("Noida",           28.5355, 77.3910, 6000),
    ("Gurgaon",         28.4595, 77.0266, 6000),
    ("Ghaziabad",       28.6692, 77.4538, 6000),
    ("Faridabad",       28.4089, 77.3178, 6000),
    ("Thane",           19.2183, 72.9781, 6000),
    ("Navi Mumbai",     19.0330, 73.0297, 6000),
    ("Nashik",          19.9975, 73.7898, 6000),
    ("Aurangabad",      19.8762, 75.3433, 6000),
    ("Rajkot",          22.3039, 70.8022, 6000),
    ("Amritsar",        31.6340, 74.8723, 6000),
    ("Jalandhar",       31.3260, 75.5762, 6000),
    ("Ludhiana",        30.9010, 75.8573, 6000),
    ("Allahabad",       25.4358, 81.8463, 6000),
    ("Meerut",          28.9845, 77.7064, 6000),
    ("Jodhpur",         26.2389, 73.0243, 6000),
    ("Udaipur",         24.5854, 73.7125, 6000),
    ("Kota",            25.2138, 75.8648, 6000),
    ("Gwalior",         26.2183, 78.1828, 6000),
    ("Jabalpur",        23.1815, 79.9864, 6000),
    ("Mysore",          12.2958, 76.6394, 6000),
    ("Mangalore",       12.9141, 74.8560, 6000),
    ("Hubli",           15.3647, 75.1240, 6000),
    ("Tiruchirappalli", 10.7905, 78.7047, 6000),
    ("Salem",           11.6643, 78.1460, 6000),
    ("Madurai",         9.9252,  78.1198, 6000),
    ("Vijayawada",      16.5062, 80.6480, 6000),
    ("Warangal",        17.9784, 79.5941, 6000),
    ("Guntur",          16.3067, 80.4365, 6000),
    ("Cuttack",         20.4625, 85.8830, 6000),
    ("Jamshedpur",      22.8046, 86.2029, 6000),
    ("Dhanbad",         23.7957, 86.4304, 6000),
    ("Siliguri",        26.7271, 88.3953, 6000),
    ("Durgapur",        23.5204, 87.3119, 6000),
    ("Asansol",         23.6739, 86.9524, 6000),
    ("Shimla",          31.1048, 77.1734, 5000),
    ("Jammu",           32.7266, 74.8570, 6000),
    ("Srinagar",        34.0837, 74.7973, 6000),
    ("Panaji",          15.4909, 73.8278, 5000),
    ("Imphal",          24.8170, 93.9368, 5000),
    ("Shillong",        25.5788, 91.8933, 5000),
    ("Agartala",        23.8315, 91.2868, 5000),
    ("Aizawl",          23.7271, 92.7176, 5000),
    ("Gangtok",         27.3389, 88.6065, 5000),
    ("Itanagar",        27.0844, 93.6053, 5000),
    ("Kohima",          25.6751, 94.1086, 5000),

    # -- Tier 4: Smaller cities for coverage --
    ("Nellore",         14.4426, 79.9865, 5000),
    ("Belgaum",         15.8497, 74.4977, 5000),
    ("Tirupati",        13.6288, 79.4192, 5000),
    ("Vellore",         12.9165, 79.1325, 5000),
    ("Pondicherry",     11.9416, 79.8083, 5000),
    ("Thrissur",        10.5276, 76.2144, 5000),
    ("Kozhikode",       11.2588, 75.7804, 5000),
    ("Kollam",          8.8932,  76.6141, 5000),
    ("Ujjain",          23.1765, 75.7885, 5000),
    ("Ajmer",           26.4499, 74.6399, 5000),
    ("Bikaner",         28.0229, 73.3119, 5000),
    ("Bareilly",        28.3670, 79.4304, 5000),
    ("Aligarh",         27.8974, 78.0880, 5000),
    ("Moradabad",       28.8386, 78.7733, 5000),
    ("Gorakhpur",       26.7606, 83.3732, 5000),
    ("Mathura",         27.4924, 77.6737, 5000),
    ("Firozabad",       27.1591, 78.3957, 4000),
    ("Roorkee",         29.8543, 77.8880, 4000),
    ("Haridwar",        29.9457, 78.1642, 4000),
    ("Rishikesh",       30.0869, 78.2676, 4000),
    ("Nainital",        29.3803, 79.4636, 4000),
    ("Jhansi",          25.4484, 78.5685, 5000),
    ("Bokaro",          23.6693, 86.1511, 4000),
    ("Muzaffarpur",     26.1209, 85.3647, 5000),
    ("Bhagalpur",       25.2425, 86.9842, 5000),
    ("Gaya",            24.7914, 84.9994, 5000),
]


def extract_pincode(tags):
    """Extract 6-digit Indian pincode from OSM tags."""
    postcode = tags.get('addr:postcode', '')
    if postcode and re.match(r'^[1-9]\d{5}$', postcode):
        return postcode
    full = tags.get('addr:full', '') + ' ' + tags.get('address', '')
    m = re.search(r'\b[1-9]\d{5}\b', full)
    return m.group() if m else ''


def build_address(tags):
    """Build readable address from OSM tags."""
    parts = []
    for k in ['addr:housenumber', 'addr:street', 'addr:suburb', 'addr:city', 'addr:state']:
        v = tags.get(k, '').strip()
        if v:
            parts.append(v)
    return ', '.join(parts) if parts else (tags.get('addr:full', '') or '')


def fetch_city(city_name, lat, lng, radius):
    """Fetch pharmacies around a city center using Overpass API."""
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="pharmacy"](around:{radius},{lat},{lng});
      way["amenity"="pharmacy"](around:{radius},{lat},{lng});
    );
    out center tags;
    """
    try:
        resp = requests.post(OVERPASS_URL, data={'data': query}, timeout=35,
                             headers={'User-Agent': 'PrescriptionWebApp/1.0'})

        if resp.status_code == 429:
            print("Rate limited, waiting 60s...", end=" ")
            time.sleep(60)
            return fetch_city(city_name, lat, lng, radius)

        if resp.status_code == 504:
            # Timeout: try with smaller radius
            if radius > 3000:
                print(f"timeout, retrying {radius//2}m...", end=" ")
                time.sleep(5)
                return fetch_city(city_name, lat, lng, radius // 2)
            return []

        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []

        for elem in data.get('elements', []):
            tags = elem.get('tags', {})
            name = tags.get('name', '') or tags.get('name:en', '')
            if not name:
                continue

            if elem['type'] == 'node':
                elat, elng = elem.get('lat'), elem.get('lon')
            else:
                c = elem.get('center', {})
                elat, elng = c.get('lat'), c.get('lon')

            if not elat or not elng:
                continue

            results.append({
                'place_id': f"osm_{elem['type']}_{elem['id']}",
                'name': name,
                'address': build_address(tags),
                'pincode': extract_pincode(tags),
                'lat': elat,
                'lng': elng,
                'phone': tags.get('phone', '') or tags.get('contact:phone', ''),
                'rating': None,
                'is_open': True,
                'city': tags.get('addr:city', '') or city_name,
                'state': tags.get('addr:state', ''),
                'types': json.dumps(["pharmacy"]),
                'source': 'osm',
            })

        return results

    except requests.exceptions.Timeout:
        if radius > 3000:
            time.sleep(5)
            return fetch_city(city_name, lat, lng, radius // 2)
        return []
    except Exception as e:
        print(f"[err: {e}]", end=" ")
        return []


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'completed': 0, 'total': 0}


def save_checkpoint(data):
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(data, f)


def fetch_all():
    from app import app, db
    from model import Pharmacy

    with app.app_context():
        checkpoint = load_checkpoint()
        start = checkpoint['completed']

        existing_ids = set(
            pid for (pid,) in db.session.query(Pharmacy.place_id).filter(
                Pharmacy.place_id.isnot(None)
            ).all()
        )

        total_cities = len(INDIA_CITIES)
        print(f"\n{'='*60}")
        print(f"  PHARMACY DATA COLLECTION - OpenStreetMap (FREE)")
        print(f"{'='*60}")
        print(f"  Cities: {total_cities} | Resume from: #{start} | Cost: $0")
        print(f"{'='*60}\n")

        new_total = 0
        dupes = 0

        for idx in range(start, total_cities):
            city_name, lat, lng, radius = INDIA_CITIES[idx]
            print(f"  [{idx+1:3d}/{total_cities}] {city_name:22s}", end=" ")

            results = fetch_city(city_name, lat, lng, radius)
            time.sleep(SLEEP_BETWEEN)

            city_new = 0
            for p in results:
                pid = p['place_id']
                if pid in existing_ids:
                    dupes += 1
                    continue
                existing_ids.add(pid)

                if not p['pincode']:
                    p['pincode'] = '000000'

                try:
                    pharmacy = Pharmacy(
                        name=p['name'], address=p['address'], pincode=p['pincode'],
                        phone=p['phone'], lat=p['lat'], lng=p['lng'],
                        rating=round(3.5 + (hash(p['name']) % 15) / 10, 1),
                        is_open=True, place_id=pid, city=p['city'],
                        state=p['state'], source='osm',
                        types=p['types'], fetched_at=datetime.utcnow(),
                    )
                    db.session.add(pharmacy)
                    city_new += 1
                    new_total += 1
                except:
                    db.session.rollback()

            # Commit per city
            try:
                db.session.commit()
            except:
                db.session.rollback()

            print(f"Found: {len(results):3d} | New: {city_new:3d} | Total new: {new_total}")

            save_checkpoint({'completed': idx + 1, 'total': new_total})

        # Summary
        final = Pharmacy.query.count()
        osm = Pharmacy.query.filter_by(source='osm').count()
        manual = Pharmacy.query.filter(
            (Pharmacy.source == 'manual') | (Pharmacy.source.is_(None))
        ).count()

        print(f"\n{'='*60}")
        print(f"  DONE! Total in DB: {final}")
        print(f"  - OpenStreetMap: {osm}")
        print(f"  - Manual/Seeded: {manual}")
        print(f"  - New this run:  {new_total}")
        print(f"  - Dupes skipped: {dupes}")
        print(f"{'='*60}\n")


if __name__ == '__main__':
    fetch_all()

"""
============================================================================
 PHARMACY FINDER MODULE — Geo-Search Upgrade
 Find nearby pharmacies using Haversine distance + medicine availability.
============================================================================

 Usage:
     from pharmacy_finder import find_pharmacies_with_medicines
     results = find_pharmacies_with_medicines(
         medicines=["Paracetamol", "Amoxicillin"],
         lat=21.17, lng=72.83,           # preferred
         pincode="395006",               # fallback
     )
============================================================================
"""

import hashlib
import time
import math
import os
import re
import requests
from collections import defaultdict

try:
    from rapidfuzz import fuzz as rf_fuzz, process as rf_process
    RAPIDFUZZ_OK = True
except ImportError:
    RAPIDFUZZ_OK = False


# ── In-Memory Cache ──────────────────────────────────────────
_cache = {}
_CACHE_TTL = 1800  # 30 minutes


def _cache_key(lat, lng, medicine_names):
    key = f"{round(lat,3)}:{round(lng,3)}|" + '|'.join(sorted(n.strip().lower() for n in medicine_names if n))
    return hashlib.md5(key.encode()).hexdigest()


def get_cached_result(lat, lng, medicine_names):
    h = _cache_key(lat, lng, medicine_names)
    if h in _cache:
        ts, result = _cache[h]
        if time.time() - ts < _CACHE_TTL:
            return result
        del _cache[h]
    return None


def cache_result(lat, lng, medicine_names, result):
    h = _cache_key(lat, lng, medicine_names)
    _cache[h] = (time.time(), result)


# ── Fuzzy Inventory Matching ─────────────────────────────────

def fuzzy_match_inventory(query, inventory_names, threshold=65):
    query_lower = query.strip().lower()
    for inv_name in inventory_names:
        if inv_name.lower() == query_lower:
            return inv_name, 100
    if RAPIDFUZZ_OK and inventory_names:
        result = rf_process.extractOne(
            query_lower,
            [n.lower() for n in inventory_names],
            scorer=rf_fuzz.ratio,
            score_cutoff=threshold,
        )
        if result:
            match_lower, score, idx = result
            return inventory_names[idx], round(score)
    return None, 0


# ── Haversine Distance ───────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Geo-Based Pharmacy Search (NEW) ──────────────────────────

def _find_pharmacies_nearby(lat, lng, radius_km=10, max_results=30):
    """
    Find pharmacies within radius_km of (lat, lng).
    Uses bounding-box SQL filter + Haversine refinement.
    Progressively expands radius if too few results found.
    """
    from model import Pharmacy

    RADIUS_STEPS = [5, 10, 25, 50]

    for r in RADIUS_STEPS:
        if r < radius_km and r != RADIUS_STEPS[0]:
            continue

        # Bounding box pre-filter (fast SQL)
        delta_lat = r / 111.0
        delta_lng = r / (111.0 * max(math.cos(math.radians(lat)), 0.01))

        pharmacies = (
            Pharmacy.query
            .filter(
                Pharmacy.lat.isnot(None),
                Pharmacy.lng.isnot(None),
                Pharmacy.lat.between(lat - delta_lat, lat + delta_lat),
                Pharmacy.lng.between(lng - delta_lng, lng + delta_lng),
            )
            .all()
        )

        # Haversine refinement (exact distance)
        results = []
        for p in pharmacies:
            dist = _haversine_km(lat, lng, p.lat, p.lng)
            if dist <= r:
                p._distance_km = round(dist, 1)
                results.append(p)

        if len(results) >= 5 or r == RADIUS_STEPS[-1]:
            results.sort(key=lambda p: p._distance_km)
            return results[:max_results]

    return []


# ── Pincode-Based Fallback Search ────────────────────────────
# (kept for backward compatibility when lat/lng not available)

def _find_pharmacies_by_pincode(pincode):
    """
    Fallback: Find pharmacies near a pincode using progressive prefix matching.
    Used only when lat/lng is not available.
    """
    from model import Pharmacy

    try:
        base = int(pincode)
        nearby = [str(base + d) for d in range(-5, 6)]
    except ValueError:
        nearby = [pincode]

    pharmacies = Pharmacy.query.filter(Pharmacy.pincode.in_(nearby)).all()
    if pharmacies:
        return pharmacies

    for prefix_len in [5, 4, 3, 2, 1]:
        prefix = pincode[:prefix_len]
        pharmacies = (
            Pharmacy.query
            .filter(Pharmacy.pincode.like(f'{prefix}%'))
            .limit(20)
            .all()
        )
        if pharmacies:
            return pharmacies

    return []


# ── Pincode to Approximate Coordinates (fallback) ───────────

_PINCODE_COORDS = {
    '11': (28.61, 77.21), '12': (28.46, 77.03), '13': (30.38, 76.78),
    '14': (31.33, 75.58), '15': (30.73, 76.78), '16': (30.73, 76.78),
    '17': (31.10, 77.17), '18': (32.73, 74.86), '19': (34.08, 74.80),
    '20': (28.54, 77.39), '21': (25.32, 82.97), '22': (26.85, 80.95),
    '23': (28.37, 79.43), '24': (30.32, 78.03), '25': (28.98, 77.71),
    '26': (27.18, 78.01), '27': (26.76, 83.37), '28': (27.49, 77.67),
    '30': (26.91, 75.79), '31': (24.59, 73.71), '32': (25.21, 75.86),
    '33': (28.02, 73.31), '34': (26.24, 73.02), '35': (25.58, 73.68),
    '36': (22.30, 70.80), '37': (23.08, 70.13), '38': (23.02, 72.57),
    '39': (21.17, 72.83), '40': (19.08, 72.88), '41': (18.52, 73.86),
    '42': (20.01, 73.79), '43': (19.88, 75.34), '44': (21.15, 79.09),
    '45': (22.72, 75.86), '46': (23.26, 77.41), '47': (26.22, 78.18),
    '48': (23.18, 79.99), '49': (21.25, 81.63), '50': (17.39, 78.49),
    '51': (15.83, 78.04), '52': (16.51, 80.65), '53': (17.69, 83.22),
    '56': (12.97, 77.59), '57': (12.30, 76.64), '58': (15.36, 75.12),
    '59': (15.85, 74.50), '60': (13.08, 80.27), '61': (12.92, 79.13),
    '62': (9.93, 78.12),  '63': (11.66, 78.15), '64': (11.02, 76.96),
    '67': (11.26, 75.78), '68': (9.93, 76.27),  '69': (8.52, 76.94),
    '70': (22.57, 88.36), '71': (22.60, 88.26), '73': (26.73, 88.40),
    '75': (20.30, 85.82), '76': (22.26, 84.85), '78': (26.14, 91.74),
    '79': (23.83, 91.29), '80': (25.61, 85.14), '81': (25.61, 85.14),
    '82': (23.80, 86.43), '83': (23.34, 85.31), '84': (26.12, 85.36),
}


def _estimate_coords_from_pincode(pincode):
    for prefix_len in [3, 2]:
        prefix = pincode[:prefix_len]
        if prefix in _PINCODE_COORDS:
            return _PINCODE_COORDS[prefix]
    zone = pincode[0] if pincode else '1'
    zone_coords = {
        '1': (28.61, 77.21), '2': (26.85, 80.95), '3': (23.02, 72.57),
        '4': (19.08, 72.88), '5': (17.39, 78.49), '6': (13.08, 80.27),
        '7': (22.57, 88.36), '8': (25.61, 85.14), '9': (26.85, 80.95),
    }
    return zone_coords.get(zone, (20.0, 78.0))


# ── Reverse Geocode — Nominatim (FREE, no API key) ───────────

_PINCODE_MAP = [
    (28.6139, 77.2090, '110001'), (28.5355, 77.3910, '201301'),
    (28.4595, 77.0266, '122001'), (30.7333, 76.7794, '160001'),
    (30.9010, 75.8573, '141001'), (31.1048, 77.1734, '171001'),
    (26.8467, 80.9462, '226001'), (26.4499, 80.3319, '208001'),
    (27.1767, 78.0081, '282001'), (25.3176, 82.9739, '221001'),
    (26.9124, 75.7873, '302001'), (23.0225, 72.5714, '380001'),
    (21.1702, 72.8311, '395001'), (22.3072, 73.1812, '390001'),
    (22.3039, 70.8022, '360001'), (19.0760, 72.8777, '400001'),
    (18.5204, 73.8567, '411001'), (21.1458, 79.0882, '440001'),
    (23.2599, 77.4126, '462001'), (22.7196, 75.8577, '452001'),
    (17.3850, 78.4867, '500001'), (12.9716, 77.5946, '560001'),
    (12.2958, 76.6394, '570001'), (17.6868, 83.2185, '530001'),
    (13.0827, 80.2707, '600001'), (11.0168, 76.9558, '641001'),
    (9.9252,  78.1198, '625001'), (9.9312,  76.2673, '682001'),
    (8.5241,  76.9366, '695001'), (22.5726, 88.3639, '700001'),
    (26.1445, 91.7362, '781001'), (20.2961, 85.8245, '751001'),
    (25.6093, 85.1376, '800001'), (23.3441, 85.3096, '834001'),
    (21.2514, 81.6296, '492001'),
]


def _fallback_reverse_geocode(lat, lng):
    """Mock reverse geocode using nearest known city."""
    if lat is None or lng is None:
        return None
    best_pincode = None
    best_dist = float('inf')
    for plat, plng, pcode in _PINCODE_MAP:
        d = ((lat - plat) ** 2 + (lng - plng) ** 2) ** 0.5
        if d < best_dist:
            best_dist = d
            best_pincode = pcode
    return best_pincode


def reverse_geocode_to_pincode(lat, lng):
    """
    Convert lat/lng to Indian pincode using Nominatim (FREE, no API key).
    Falls back to mock mapping if Nominatim fails.
    """
    if lat is None or lng is None:
        return None

    # Try Nominatim first (free, no key needed)
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        'lat': lat,
        'lon': lng,
        'format': 'json',
        'addressdetails': 1,
        'zoom': 18,
    }
    headers = {
        'User-Agent': 'PrescriptionWebApp/1.0 (student-project)'
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        data = resp.json()
        address = data.get('address', {})
        pincode = address.get('postcode', '')

        if pincode and re.match(r'^[1-9]\d{5}$', pincode):
            return pincode
    except Exception as e:
        print(f"[GEO] Nominatim error: {e}")

    return _fallback_reverse_geocode(lat, lng)


# ── Main Finder ──────────────────────────────────────────────

def find_pharmacies_with_medicines(medicines, lat=None, lng=None, pincode=None, db_session=None):
    """
    Find nearby pharmacies that stock the given medicines.
    Accepts lat/lng (preferred) or pincode (fallback).
    """
    if not medicines or not db_session:
        return []

    # Resolve coordinates
    user_lat = lat
    user_lng = lng

    if user_lat is None or user_lng is None:
        if pincode:
            user_lat, user_lng = _estimate_coords_from_pincode(pincode)
        else:
            return []

    # Check cache
    cached = get_cached_result(user_lat, user_lng, medicines)
    if cached is not None:
        return cached

    from model import PharmacyInventory
    from medicine_availability import estimate_availability

    # Step 1: Find nearby pharmacies (geo search with progressive radius)
    if lat is not None and lng is not None:
        pharmacies = _find_pharmacies_nearby(user_lat, user_lng, radius_km=10)
    else:
        # Fallback to pincode search if no real coords
        pharmacies = _find_pharmacies_by_pincode(pincode)

    if not pharmacies:
        cache_result(user_lat, user_lng, medicines, [])
        return []

    # Step 2: Bulk-load inventory (for pharmacies that have it)
    pharmacy_ids = [p.id for p in pharmacies]
    all_inventory = (
        PharmacyInventory.query
        .filter(PharmacyInventory.pharmacy_id.in_(pharmacy_ids))
        .all()
    )

    inv_by_pharmacy = defaultdict(list)
    for inv in all_inventory:
        inv_by_pharmacy[inv.pharmacy_id].append(inv)

    # Step 3: Match medicines for each pharmacy
    results = []

    for pharmacy in pharmacies:
        p_inventory = inv_by_pharmacy.get(pharmacy.id, [])
        inv_names = [inv.medicine for inv in p_inventory]
        inv_lookup = {inv.medicine.lower(): inv for inv in p_inventory}
        has_real_inventory = len(p_inventory) > 0

        med_results = []
        matched_count = 0

        for med_name in medicines:
            if has_real_inventory:
                # Use real inventory data
                match_name, score = fuzzy_match_inventory(med_name, inv_names)

                if match_name and score >= 65:
                    inv_item = inv_lookup.get(match_name.lower())
                    in_stock = inv_item.in_stock if inv_item else False
                    price = inv_item.price if inv_item else None
                    med_results.append({
                        'name': med_name,
                        'matched_to': match_name,
                        'match_score': score,
                        'in_stock': in_stock,
                        'price': price,
                        'available': in_stock,
                        'confidence': 'high' if in_stock else 'high',
                        'label': 'In Stock' if in_stock else 'Out of Stock',
                    })
                    if in_stock:
                        matched_count += 1
                else:
                    med_results.append({
                        'name': med_name,
                        'matched_to': None,
                        'match_score': 0,
                        'in_stock': False,
                        'price': None,
                        'available': False,
                        'confidence': 'high',
                        'label': 'Not Found',
                    })
            else:
                # Use estimation (for Google-fetched pharmacies without inventory)
                est = estimate_availability(pharmacy.name, med_name)
                med_results.append({
                    'name': med_name,
                    'matched_to': None,
                    'match_score': 0,
                    'in_stock': est['available'] is True,
                    'price': None,
                    'available': est['available'],
                    'confidence': est['confidence'],
                    'label': est['label'],
                })
                if est['available'] is True:
                    matched_count += 1

        availability_pct = round((matched_count / len(medicines)) * 100) if medicines else 0

        # Distance calculation
        if hasattr(pharmacy, '_distance_km'):
            dist_km = pharmacy._distance_km
        elif pharmacy.lat and pharmacy.lng:
            dist_km = round(_haversine_km(user_lat, user_lng, pharmacy.lat, pharmacy.lng), 1)
        else:
            try:
                dist_km = abs(int(pharmacy.pincode) - int(pincode or '0')) * 0.5
            except ValueError:
                dist_km = 99.0

        results.append({
            'id': pharmacy.id,
            'name': pharmacy.name,
            'address': pharmacy.address or '',
            'pincode': pharmacy.pincode,
            'phone': pharmacy.phone or '',
            'rating': pharmacy.rating or 4.0,
            'is_open': pharmacy.is_open,
            'lat': pharmacy.lat,
            'lng': pharmacy.lng,
            'distance_km': round(dist_km, 1),
            'medicines': med_results,
            'matched_count': matched_count,
            'total_prescribed': len(medicines),
            'availability_pct': availability_pct,
            'source': getattr(pharmacy, 'source', 'manual'),
            'city': getattr(pharmacy, 'city', ''),
        })

    # Step 4: Rank and limit
    results.sort(key=lambda r: (-r['availability_pct'], -r['rating'], r['distance_km']))
    results = results[:15]

    cache_result(user_lat, user_lng, medicines, results)
    return results

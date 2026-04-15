"""
============================================================================
 TEST APIs - Verify OpenStreetMap APIs work (FREE, no key needed)
============================================================================
 Run:  python test_google_api.py
============================================================================
"""

import requests
import sys
import io

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def test_overpass_api():
    print("\n[TEST 1] Overpass API - Pharmacy Search (FREE)")
    print("-" * 50)

    query = """
    [out:json][timeout:25];
    (
      node["amenity"="pharmacy"](28.55,77.15,28.67,77.30);
      way["amenity"="pharmacy"](28.55,77.15,28.67,77.30);
    );
    out center tags;
    """

    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={'data': query},
            timeout=30,
            headers={'User-Agent': 'PrescriptionWebApp/1.0 (student-project)'}
        )

        if resp.status_code != 200:
            print(f"  [FAIL] HTTP Error: {resp.status_code}")
            return False

        data = resp.json()
        elements = data.get('elements', [])
        named = [e for e in elements if e.get('tags', {}).get('name')]

        print(f"  [PASS] Found {len(elements)} pharmacies ({len(named)} with names) near Delhi")
        for elem in named[:5]:
            tags = elem.get('tags', {})
            name = tags.get('name', 'Unnamed')
            lat = elem.get('lat') or elem.get('center', {}).get('lat', '')
            lng = elem.get('lon') or elem.get('center', {}).get('lon', '')
            print(f"    - {name} ({lat}, {lng})")

        return len(named) > 0

    except Exception as e:
        print(f"  [FAIL] Request failed: {e}")
        return False


def test_nominatim_api():
    print("\n[TEST 2] Nominatim API - Reverse Geocode (FREE)")
    print("-" * 50)

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        'lat': 28.6139,
        'lon': 77.2090,
        'format': 'json',
        'addressdetails': 1,
    }
    headers = {
        'User-Agent': 'PrescriptionWebApp/1.0 (student-project)'
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()

        address = data.get('address', {})
        pincode = address.get('postcode', '')
        city = address.get('city', '') or address.get('town', '')
        state = address.get('state', '')

        if pincode:
            print(f"  [PASS] Reverse geocode successful!")
            print(f"    Coordinates: (28.6139, 77.2090)")
            print(f"    Pincode:     {pincode}")
            print(f"    City:        {city}")
            print(f"    State:       {state}")
            return True
        else:
            print(f"  [FAIL] No pincode in response")
            return False

    except Exception as e:
        print(f"  [FAIL] Request failed: {e}")
        return False


def test_osm_tiles():
    print("\n[TEST 3] OpenStreetMap Tiles - Map Display (FREE)")
    print("-" * 50)

    try:
        resp = requests.head(
            "https://tile.openstreetmap.org/10/580/356.png",
            timeout=10,
            headers={'User-Agent': 'PrescriptionWebApp/1.0 (student-project)'}
        )
        if resp.status_code == 200:
            print(f"  [PASS] OSM tile server is reachable")
            print(f"    Leaflet.js + OSM tiles will work for map display")
            return True
        else:
            print(f"  [FAIL] HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"  [FAIL] Request failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("  FREE API VERIFICATION - No payment needed!")
    print("=" * 60)

    r1 = test_overpass_api()
    r2 = test_nominatim_api()
    r3 = test_osm_tiles()

    print("\n" + "=" * 60)
    results = sum([r1, r2, r3])
    if results == 3:
        print("  ALL 3 TESTS PASSED - Everything is working!")
        print("  Next steps:")
        print("    1. python migrate_pharmacies.py")
        print("    2. python fetch_pharmacies.py")
        print("    3. python app.py")
    elif results > 0:
        print(f"  {results}/3 tests passed. Check failures above.")
    else:
        print("  ALL TESTS FAILED - Check your internet connection.")
    print("=" * 60)

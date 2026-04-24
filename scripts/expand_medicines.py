"""
============================================================================
 EXPAND MEDICINES - Scale medicine database from ~491 to 2000+
============================================================================
 Run:  python scripts/expand_medicines.py

 Sources:
   1. Curated expansion JSON (data/medicine_expansion.json)
   2. OpenFDA API supplement (optional, internet required)
============================================================================
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

env_path = os.path.join(BASE_DIR, 'config', '.env')
load_dotenv(env_path)

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in config/.env")
    sys.exit(1)


def fetch_openfda_medicines(limit=200):
    """Fetch common generic drugs from OpenFDA (free, no API key)."""
    try:
        import requests
    except ImportError:
        print("[OpenFDA] requests module not found, skipping.")
        return []

    url = "https://api.fda.gov/drug/label.json"
    results = []
    skip = 0
    batch_size = 100

    print(f"  Fetching from OpenFDA (up to {limit} entries)...")

    while len(results) < limit:
        params = {
            'search': 'openfda.product_type:"HUMAN PRESCRIPTION DRUG"',
            'limit': min(batch_size, limit - len(results)),
            'skip': skip,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            items = data.get('results', [])
            if not items:
                break

            for item in items:
                openfda = item.get('openfda', {})
                brand_names = openfda.get('brand_name', [])
                generic_names = openfda.get('generic_name', [])
                manufacturers = openfda.get('manufacturer_name', [])
                pharm_classes = openfda.get('pharm_class_epc', [])

                brand = (brand_names[0] if brand_names else '').strip()
                generic = (generic_names[0] if generic_names else '').strip()
                manufacturer = (manufacturers[0] if manufacturers else '').strip()
                category = (pharm_classes[0] if pharm_classes else 'General').strip()

                if brand and generic and 3 <= len(brand) <= 50:
                    results.append({
                        'brand': brand.title(),
                        'generic': generic.title(),
                        'category': category.title() if len(category) < 50 else 'General',
                        'manufacturer': manufacturer[:200] if manufacturer else '',
                    })

            skip += batch_size
        except Exception as e:
            print(f"  [OpenFDA] Error: {e}")
            break

    print(f"  [OpenFDA] Fetched {len(results)} medicines")
    return results


def expand():
    engine = create_engine(DATABASE_URL)

    print("=" * 60)
    print("  MEDICINE DATABASE EXPANSION")
    print("=" * 60)

    with engine.connect() as conn:
        # Get existing brands
        rows = conn.execute(text("SELECT brand FROM medicines")).fetchall()
        existing_brands = {row[0].lower() for row in rows}
        initial_count = len(existing_brands)
        print(f"  Current count: {initial_count}")
        added = 0

        # -- Source 1: Curated expansion JSON --
        expansion_path = os.path.join(BASE_DIR, 'data', 'medicine_expansion.json')
        if os.path.exists(expansion_path):
            with open(expansion_path, 'r', encoding='utf-8') as f:
                expansion_data = json.load(f)

            curated_added = 0
            for item in expansion_data:
                if item['brand'].lower() not in existing_brands:
                    dosage_forms = json.dumps(item['dosage_forms']) if 'dosage_forms' in item else None
                    strengths = json.dumps(item['strengths']) if 'strengths' in item else None

                    conn.execute(text("""
                        INSERT INTO medicines (brand, generic, category, manufacturer,
                                              dosage_forms, strengths, schedule, is_otc)
                        VALUES (:brand, :generic, :category, :manufacturer,
                                :dosage_forms, :strengths, :schedule, :is_otc)
                    """), {
                        'brand': item['brand'],
                        'generic': item['generic'],
                        'category': item['category'],
                        'manufacturer': item.get('manufacturer', ''),
                        'dosage_forms': dosage_forms,
                        'strengths': strengths,
                        'schedule': item.get('schedule'),
                        'is_otc': item.get('is_otc', False),
                    })
                    existing_brands.add(item['brand'].lower())
                    curated_added += 1
                    added += 1

            conn.commit()
            print(f"  [Curated] Added {curated_added} medicines")
        else:
            print(f"  [Curated] {expansion_path} not found, skipping")

        # -- Source 2: OpenFDA supplement --
        try:
            fda_meds = fetch_openfda_medicines(200)
            fda_added = 0
            for item in fda_meds:
                if item['brand'].lower() not in existing_brands:
                    conn.execute(text("""
                        INSERT INTO medicines (brand, generic, category, manufacturer)
                        VALUES (:brand, :generic, :category, :manufacturer)
                    """), {
                        'brand': item['brand'],
                        'generic': item['generic'],
                        'category': item['category'],
                        'manufacturer': item.get('manufacturer', ''),
                    })
                    existing_brands.add(item['brand'].lower())
                    fda_added += 1
                    added += 1

            conn.commit()
            print(f"  [OpenFDA] Added {fda_added} medicines")
        except Exception as e:
            print(f"  [OpenFDA] Skipped: {e}")

        # Get final count
        total = conn.execute(text("SELECT COUNT(*) FROM medicines")).scalar()

    print(f"\n{'=' * 60}")
    print(f"  EXPANSION COMPLETE")
    print(f"  Before: {initial_count}")
    print(f"  Added:  {added}")
    print(f"  Total:  {total}")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    expand()

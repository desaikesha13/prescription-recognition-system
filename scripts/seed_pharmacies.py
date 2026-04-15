"""
============================================================================
 SEED PHARMACIES — Populate pharmacy data for demo
============================================================================
 Run once:  python scripts/seed_pharmacies.py
 
 Creates ~400+ pharmacies across Indian cities with DENSE coverage
 in Surat (25+ areas) and major Gujarat cities.
 Each pharmacy stocks 40–80% of medicines from medicine_database.json.
============================================================================
"""

import json
import random
import os
import sys

# Add project root to sys.path (script in scripts/ subdirectory)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

random.seed(42)

# ── Pharmacy Templates ───────────────────────────────────────

PHARMACY_CHAINS = [
    "MedPlus", "Apollo Pharmacy", "Netmeds Store", "Wellness Forever",
    "Frank Ross", "Guardian Pharmacy", "Jan Aushadhi", "GenericPlus",
    "HealthKart Store", "Davaindia", "PharmEasy Store", "Noble Plus",
    "Care Pharmacy", "Sanjivani Medicals", "Lifeline Pharmacy",
    "Star Medicals", "City Drug House", "Om Medicals", "Shree Pharma",
    "Raj Medicals", "Krishna Pharmacy", "Aarogya Medicals",
    "Sanjeevani Chemist", "Medi World", "Cure Well Pharmacy",
    "Health First", "Patel Medicals", "Sunrise Pharmacy",
    "National Medicals", "Royal Chemist", "Bharat Pharmacy",
    "Swastik Medicals", "Life Care Pharmacy", "Metro Drug House",
    "Central Medicals", "Green Cross Pharmacy", "Prime Pharmacy",
    "Reliable Chemist", "Sagar Medicals", "Vinayak Pharmacy",
]

SUFFIXES = ["", " Plus", " Express", " 24x7", " Mart", " Point", " Hub"]

# ── Location Data ────────────────────────────────────────────
# Format: (city, pincode, lat, lng, state, pharmacy_count)
# pharmacy_count: how many pharmacies to generate at this location
# Dense coverage for Surat, good coverage for Gujarat,
# standard coverage for rest of India.

LOCATION_DATA = [
    # ═══════════════════════════════════════════════════════════
    # SURAT — DENSE COVERAGE (25+ distinct areas)
    # Real area coordinates for different Surat neighborhoods
    # ═══════════════════════════════════════════════════════════

    # Central / Old City
    ("Surat", "395001", 21.1702, 72.8311, "Gujarat", 3),  # Chowk Bazaar / Ring Road
    ("Surat", "395002", 21.1810, 72.8200, "Gujarat", 3),  # Nanpura / Athwa Gate
    ("Surat", "395003", 21.1950, 72.8300, "Gujarat", 3),  # Majura Gate / Ghod Dod Road

    # Athwa / Adajan / Piplod (affluent areas)
    ("Surat", "395006", 21.1580, 72.7970, "Gujarat", 3),  # Athwa Lines
    ("Surat", "395007", 21.1670, 72.7830, "Gujarat", 3),  # Adajan Patiya
    ("Surat", "395009", 21.1490, 72.7710, "Gujarat", 3),  # Piplod / VIP Road
    ("Surat", "395004", 21.1530, 72.8120, "Gujarat", 2),  # Umra / Dumas Road

    # Varachha / Kapodra (dense residential)
    ("Surat", "395006", 21.2100, 72.8600, "Gujarat", 3),  # Varachha Road
    ("Surat", "395008", 21.2030, 72.8450, "Gujarat", 3),  # Kapodra / Yogi Chowk
    ("Surat", "395010", 21.2200, 72.8700, "Gujarat", 2),  # Katargam

    # Udhna / Pandesara (industrial belt)
    ("Surat", "394210", 21.1600, 72.8500, "Gujarat", 2),  # Udhna
    ("Surat", "394221", 21.1350, 72.8600, "Gujarat", 2),  # Pandesara GIDC
    ("Surat", "394220", 21.1400, 72.8700, "Gujarat", 2),  # Sachin

    # Vesu / Pal / Althan
    ("Surat", "395007", 21.1400, 72.7650, "Gujarat", 3),  # Vesu
    ("Surat", "395009", 21.1300, 72.7850, "Gujarat", 2),  # Pal / Bhatar
    ("Surat", "395017", 21.1750, 72.7600, "Gujarat", 2),  # Althan / SVNIT area

    # Rander / Adajan West
    ("Surat", "395005", 21.2050, 72.7900, "Gujarat", 2),  # Rander
    ("Surat", "395009", 21.1900, 72.7700, "Gujarat", 2),  # Adajan Gam

    # Dindoli / Bhestan / Kamrej
    ("Surat", "394210", 21.1250, 72.8350, "Gujarat", 2),  # Dindoli
    ("Surat", "394185", 21.1100, 72.8100, "Gujarat", 2),  # Bhestan
    ("Surat", "394180", 21.2500, 72.8500, "Gujarat", 2),  # Kamrej

    # Rundh / Dumas / Hajira
    ("Surat", "395007", 21.1200, 72.7400, "Gujarat", 2),  # Dumas Road
    ("Surat", "394270", 21.1050, 72.6800, "Gujarat", 1),  # Hajira

    # New developing areas
    ("Surat", "395023", 21.2300, 72.8200, "Gujarat", 2),  # Bamroli / LP Savani
    ("Surat", "394107", 21.2400, 72.8900, "Gujarat", 2),  # Kosad
    ("Surat", "395010", 21.2100, 72.8100, "Gujarat", 2),  # Palanpur Jakatnaka

    # ═══════════════════════════════════════════════════════════
    # OTHER GUJARAT CITIES — GOOD COVERAGE
    # ═══════════════════════════════════════════════════════════

    # Ahmedabad (multiple areas)
    ("Ahmedabad", "380001", 23.0225, 72.5714, "Gujarat", 3),  # Old City / Lal Darwaja
    ("Ahmedabad", "380006", 23.0390, 72.5660, "Gujarat", 2),  # Navrangpura
    ("Ahmedabad", "380009", 23.0290, 72.5070, "Gujarat", 2),  # Satellite
    ("Ahmedabad", "380015", 23.0500, 72.5300, "Gujarat", 2),  # Vastrapur / IIM
    ("Ahmedabad", "380054", 23.0710, 72.5170, "Gujarat", 2),  # Bopal / South Bopal
    ("Ahmedabad", "380058", 23.0100, 72.5030, "Gujarat", 2),  # Thaltej / SG Highway
    ("Ahmedabad", "380004", 23.0690, 72.6330, "Gujarat", 2),  # Maninagar
    ("Ahmedabad", "382350", 23.0480, 72.6700, "Gujarat", 2),  # Naroda / CTM

    # Vadodara
    ("Vadodara", "390001", 22.3072, 73.1812, "Gujarat", 3),  # Alkapuri / Sayajigunj
    ("Vadodara", "390005", 22.3190, 73.1700, "Gujarat", 2),  # Manjalpur
    ("Vadodara", "390007", 22.2830, 73.1640, "Gujarat", 2),  # Karelibaug
    ("Vadodara", "390019", 22.3120, 73.2070, "Gujarat", 2),  # Waghodia Road

    # Rajkot
    ("Rajkot", "360001", 22.3039, 70.8022, "Gujarat", 3),
    ("Rajkot", "360005", 22.2900, 70.7830, "Gujarat", 2),
    ("Rajkot", "360007", 22.2750, 70.8100, "Gujarat", 2),

    # Other Gujarat cities (1-2 each)
    ("Gandhinagar", "382010", 23.2156, 72.6369, "Gujarat", 2),
    ("Bhavnagar",   "364001", 21.7645, 72.1519, "Gujarat", 2),
    ("Junagadh",    "362001", 21.5222, 70.4579, "Gujarat", 2),
    ("Anand",       "388001", 22.5645, 72.9289, "Gujarat", 2),
    ("Mehsana",     "384001", 23.6000, 72.4000, "Gujarat", 2),
    ("Nadiad",      "387001", 22.6916, 72.8634, "Gujarat", 2),
    ("Bharuch",     "392001", 21.7051, 72.9959, "Gujarat", 2),
    ("Navsari",     "396445", 20.9467, 72.9520, "Gujarat", 2),
    ("Valsad",      "396001", 20.5992, 72.9342, "Gujarat", 2),
    ("Palanpur",    "385001", 24.1725, 72.4381, "Gujarat", 1),
    ("Morbi",       "363641", 22.8173, 70.8370, "Gujarat", 1),
    ("Gandhidham",  "370201", 23.0753, 70.1337, "Gujarat", 1),
    ("Vapi",        "396191", 20.3714, 72.9042, "Gujarat", 1),
    ("Porbandar",   "360575", 21.6417, 69.6293, "Gujarat", 1),

    # ═══════════════════════════════════════════════════════════
    # REST OF INDIA — STANDARD COVERAGE
    # ═══════════════════════════════════════════════════════════

    # Delhi NCR
    ("New Delhi",  "110001", 28.6139, 77.2090, "Delhi", 2),
    ("New Delhi",  "110005", 28.6692, 77.2272, "Delhi", 2),
    ("New Delhi",  "110020", 28.5672, 77.2300, "Delhi", 2),
    ("New Delhi",  "110085", 28.7041, 77.1025, "Delhi", 1),
    ("Noida",      "201301", 28.5355, 77.3910, "UP", 2),
    ("Gurgaon",    "122001", 28.4595, 77.0266, "Haryana", 2),
    ("Faridabad",  "121001", 28.4089, 77.3178, "Haryana", 1),
    ("Ghaziabad",  "201001", 28.6692, 77.4538, "UP", 1),

    # Punjab / Haryana / HP / J&K
    ("Chandigarh", "160001", 30.7333, 76.7794, "Chandigarh", 2),
    ("Ludhiana",   "141001", 30.9010, 75.8573, "Punjab", 2),
    ("Amritsar",   "143001", 31.6340, 74.8723, "Punjab", 1),
    ("Jalandhar",  "144001", 31.3260, 75.5762, "Punjab", 1),
    ("Shimla",     "171001", 31.1048, 77.1734, "HP", 1),
    ("Jammu",      "180001", 32.7266, 74.8570, "J&K", 1),
    ("Dehradun",   "248001", 30.3165, 78.0322, "Uttarakhand", 1),

    # UP
    ("Lucknow",    "226001", 26.8467, 80.9462, "UP", 2),
    ("Kanpur",     "208001", 26.4499, 80.3319, "UP", 1),
    ("Agra",       "282001", 27.1767, 78.0081, "UP", 1),
    ("Varanasi",   "221001", 25.3176, 82.9739, "UP", 1),
    ("Meerut",     "250001", 28.9845, 77.7064, "UP", 1),

    # Rajasthan
    ("Jaipur",     "302001", 26.9124, 75.7873, "Rajasthan", 2),
    ("Jodhpur",    "342001", 26.2389, 73.0243, "Rajasthan", 1),
    ("Udaipur",    "313001", 24.5854, 73.7125, "Rajasthan", 1),
    ("Kota",       "324001", 25.2138, 75.8648, "Rajasthan", 1),

    # Maharashtra
    ("Mumbai",     "400001", 19.0760, 72.8777, "Maharashtra", 3),
    ("Mumbai",     "400050", 19.0590, 72.8375, "Maharashtra", 2),
    ("Mumbai",     "400070", 19.0453, 72.8884, "Maharashtra", 2),
    ("Pune",       "411001", 18.5204, 73.8567, "Maharashtra", 2),
    ("Pune",       "411038", 18.5590, 73.9170, "Maharashtra", 2),
    ("Nagpur",     "440001", 21.1458, 79.0882, "Maharashtra", 2),
    ("Nashik",     "422001", 20.0063, 73.7901, "Maharashtra", 1),
    ("Thane",      "400601", 19.2183, 72.9781, "Maharashtra", 1),
    ("Navi Mumbai","400703", 19.0330, 73.0297, "Maharashtra", 1),

    # MP / CG
    ("Bhopal",     "462001", 23.2599, 77.4126, "MP", 2),
    ("Indore",     "452001", 22.7196, 75.8577, "MP", 2),
    ("Raipur",     "492001", 21.2514, 81.6296, "CG", 1),

    # Telangana / AP
    ("Hyderabad",  "500001", 17.3850, 78.4867, "Telangana", 2),
    ("Hyderabad",  "500034", 17.4400, 78.4983, "Telangana", 2),
    ("Visakhapatnam","530001",17.6868, 83.2185, "AP", 1),
    ("Vijayawada", "520001", 16.5062, 80.6480, "AP", 1),

    # Karnataka
    ("Bangalore",  "560001", 12.9716, 77.5946, "Karnataka", 2),
    ("Bangalore",  "560034", 12.9340, 77.6150, "Karnataka", 2),
    ("Mysore",     "570001", 12.2958, 76.6394, "Karnataka", 1),
    ("Mangalore",  "575001", 12.9141, 74.8560, "Karnataka", 1),

    # Tamil Nadu
    ("Chennai",    "600001", 13.0827, 80.2707, "TN", 2),
    ("Chennai",    "600017", 13.0478, 80.2507, "TN", 2),
    ("Coimbatore", "641001", 11.0168, 76.9558, "TN", 1),
    ("Madurai",    "625001", 9.9252,  78.1198, "TN", 1),

    # Kerala
    ("Kochi",      "682001", 9.9312,  76.2673, "Kerala", 2),
    ("Thiruvananthapuram","695001", 8.5241, 76.9366, "Kerala", 1),
    ("Kozhikode",  "673001", 11.2588, 75.7804, "Kerala", 1),

    # West Bengal / NE
    ("Kolkata",    "700001", 22.5726, 88.3639, "WB", 2),
    ("Kolkata",    "700020", 22.5180, 88.3480, "WB", 2),
    ("Guwahati",   "781001", 26.1445, 91.7362, "Assam", 1),
    ("Siliguri",   "734001", 26.7271, 88.3953, "WB", 1),

    # Odisha / Jharkhand / Bihar
    ("Bhubaneswar","751001", 20.2961, 85.8245, "Odisha", 2),
    ("Ranchi",     "834001", 23.3441, 85.3096, "Jharkhand", 1),
    ("Patna",      "800001", 25.6093, 85.1376, "Bihar", 2),

    # Goa
    ("Panaji",     "403001", 15.4909, 73.8278, "Goa", 1),
]


STREET_NAMES_SURAT = [
    "Ring Road", "Ghod Dod Road", "Dumas Road", "Athwa Lines",
    "Station Road", "City Light Road", "Parle Point", "Pal Road",
    "VIP Road", "Udhna Darwaja", "Sahara Darwaja", "Relief Road",
    "Varachha Main Road", "LP Savani Road", "Vesu Main Road",
    "Adajan Patiya", "Rander Road", "Katargam Main Road",
    "Puna Kumbharia Road", "Yogi Chowk", "Bamroli Road",
    "Canal Road", "Dindoli Road", "Sachin GIDC Road",
    "Althan-Bhatar Road", "Piplod Road",
]

STREET_NAMES_GENERAL = [
    "MG Road", "Station Road", "Gandhi Nagar", "Market Street",
    "Main Road", "Ring Road", "Highway Plaza", "Civil Lines",
    "Nehru Street", "Patel Road", "Lake View Road", "Temple Street",
    "Bus Stand Road", "Clock Tower Area", "Subhash Chowk",
    "Railway Colony", "Industrial Area", "Collector Office Road",
]


def generate_pharmacies():
    """Generate pharmacy data with dense Surat coverage."""
    pharmacies = []
    used_place_ids = set()  # ensure unique place_ids

    for loc in LOCATION_DATA:
        city, pincode, base_lat, base_lng, state, count = loc

        # Choose appropriate street names
        if city == "Surat":
            streets = STREET_NAMES_SURAT
        else:
            streets = STREET_NAMES_GENERAL

        for i in range(count):
            chain = random.choice(PHARMACY_CHAINS)
            suffix = random.choice(SUFFIXES)
            street = random.choice(streets)
            branch_num = random.randint(1, 99)
            name = f"{chain}{suffix}"

            # Generate a unique place_id for deduplication
            place_id = f"seed_{pincode}_{i}_{random.randint(1000,9999)}"
            while place_id in used_place_ids:
                place_id = f"seed_{pincode}_{i}_{random.randint(1000,9999)}"
            used_place_ids.add(place_id)

            # Lat/lng jitter — varies by city density
            if city == "Surat":
                jitter = 0.008  # ~800m spread per location
            elif city in ("Mumbai", "Delhi", "Bangalore", "Chennai", "Kolkata",
                          "Hyderabad", "Ahmedabad", "Pune"):
                jitter = 0.012
            else:
                jitter = 0.015

            lat = base_lat + random.uniform(-jitter, jitter)
            lng = base_lng + random.uniform(-jitter, jitter)

            pharmacies.append({
                'name': name,
                'address': f"{branch_num}, {street}, {city}",
                'pincode': pincode,
                'phone': f"+91 {random.randint(70000, 99999)}{random.randint(10000, 99999)}",
                'lat': round(lat, 6),
                'lng': round(lng, 6),
                'rating': round(random.uniform(3.2, 4.9), 1),
                'is_open': random.random() > 0.15,
                'city': city,
                'state': state,
                'place_id': place_id,
                'source': 'seed',
            })

    return pharmacies


def generate_inventory(pharmacy_id, all_medicines, stock_pct=None):
    """Generate inventory for a pharmacy."""
    if stock_pct is None:
        stock_pct = random.uniform(0.40, 0.80)

    sample_size = max(1, int(len(all_medicines) * stock_pct))
    stocked_meds = random.sample(all_medicines, sample_size)

    inventory = []
    for med in stocked_meds:
        base_price = random.uniform(5, 500)
        inventory.append({
            'pharmacy_id': pharmacy_id,
            'medicine': med['brand'],
            'generic': med.get('generic', ''),
            'in_stock': random.random() > 0.1,
            'price': round(base_price, 2),
        })

    return inventory


# ── Main Seeder ──────────────────────────────────────────────

def seed():
    from app import app, db
    from model import Pharmacy, PharmacyInventory

    med_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'medicine_database.json')
    with open(med_db_path, 'r') as f:
        all_medicines = json.load(f)

    with app.app_context():
        # Clear only seed data (preserve Google-fetched pharmacies)
        seed_pharmacies = Pharmacy.query.filter(
            (Pharmacy.source == 'seed') | (Pharmacy.source == 'manual') | (Pharmacy.source.is_(None))
        ).all()
        seed_ids = [p.id for p in seed_pharmacies]

        if seed_ids:
            PharmacyInventory.query.filter(PharmacyInventory.pharmacy_id.in_(seed_ids)).delete(synchronize_session=False)
            Pharmacy.query.filter(Pharmacy.id.in_(seed_ids)).delete(synchronize_session=False)
            db.session.commit()
            print(f"  Cleaned {len(seed_ids)} old seed pharmacies")

        # Generate pharmacies
        pharmacy_data = generate_pharmacies()
        pharmacy_objs = []

        for pd in pharmacy_data:
            p = Pharmacy(
                name=pd['name'],
                address=pd['address'],
                pincode=pd['pincode'],
                phone=pd['phone'],
                lat=pd['lat'],
                lng=pd['lng'],
                rating=pd['rating'],
                is_open=pd['is_open'],
                city=pd.get('city', ''),
                state=pd.get('state', ''),
                place_id=pd.get('place_id'),
                source=pd.get('source', 'seed'),
            )
            db.session.add(p)
            pharmacy_objs.append(p)

        db.session.flush()

        # Generate inventory
        total_inv = 0
        for p in pharmacy_objs:
            inv_data = generate_inventory(p.id, all_medicines)
            for inv in inv_data:
                db.session.add(PharmacyInventory(
                    pharmacy_id=inv['pharmacy_id'],
                    medicine=inv['medicine'],
                    generic=inv['generic'],
                    in_stock=inv['in_stock'],
                    price=inv['price'],
                ))
                total_inv += 1

        db.session.commit()

        # Summary
        surat_count = sum(1 for p in pharmacy_objs if p.city == 'Surat')
        gujarat_count = sum(1 for p in pharmacy_objs if p.state == 'Gujarat')
        unique_pincodes = set(p.pincode for p in pharmacy_objs)
        surat_pincodes = set(p.pincode for p in pharmacy_objs if p.city == 'Surat')

        print(f"\n{'=' * 60}")
        print(f"  PHARMACY SEED COMPLETE")
        print(f"{'=' * 60}")
        print(f"  Total pharmacies:     {len(pharmacy_objs)}")
        print(f"  Surat pharmacies:     {surat_count} ({len(surat_pincodes)} pincodes)")
        print(f"  Gujarat pharmacies:   {gujarat_count}")
        print(f"  Inventory items:      {total_inv}")
        print(f"  Unique pincodes:      {len(unique_pincodes)}")
        print(f"  Surat pincodes:       {sorted(surat_pincodes)}")
        print(f"{'=' * 60}\n")


if __name__ == '__main__':
    seed()

import sys
import os

# Add project root to sys.path (script moved to scripts/ subdirectory)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from app import app, db
from model import Medicine

with app.app_context():
    med_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'medicine_database.json')
    with open(med_db_path, 'r') as f:
        medicines = json.load(f)

    count = 0
    for item in medicines:
        medicine = Medicine(
            brand    = item['brand'],
            generic  = item['generic'],
            category = item['category']
        )
        db.session.add(medicine)
        count += 1

    db.session.commit()
    print(f"Successfully migrated {count} medicines to PostgreSQL!")
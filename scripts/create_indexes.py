"""
============================================================================
 CREATE INDEXES - PostgreSQL trigram indexes for fast fuzzy search
============================================================================
 Run once:  python scripts/create_indexes.py

 Requires PostgreSQL pg_trgm extension (ships with most installs).
============================================================================
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'config', '.env')
load_dotenv(env_path)

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in config/.env")
    sys.exit(1)


def create_indexes():
    engine = create_engine(DATABASE_URL)

    print("=" * 60)
    print("  CREATING POSTGRESQL INDEXES")
    print("=" * 60)

    with engine.connect() as conn:
        statements = [
            # Enable trigram extension
            "CREATE EXTENSION IF NOT EXISTS pg_trgm",

            # Trigram GIN indexes for fuzzy search
            "CREATE INDEX IF NOT EXISTS ix_medicine_brand_trgm ON medicines USING GIN (brand gin_trgm_ops)",
            "CREATE INDEX IF NOT EXISTS ix_medicine_generic_trgm ON medicines USING GIN (generic gin_trgm_ops)",
            "CREATE INDEX IF NOT EXISTS ix_synonym_trgm ON medicine_synonyms USING GIN (synonym gin_trgm_ops)",

            # Composite indexes for common queries
            "CREATE INDEX IF NOT EXISTS ix_medicine_category_brand ON medicines (category, brand)",
            "CREATE INDEX IF NOT EXISTS ix_feedback_unused ON feedback (used_in_training) WHERE used_in_training = false",
            "CREATE INDEX IF NOT EXISTS ix_pharmacy_inv_med ON pharmacy_inventory (medicine, pharmacy_id)",
        ]

        for sql in statements:
            try:
                conn.execute(text(sql))
                name = sql.split("ix_")[-1].split(" ")[0] if "ix_" in sql else sql.split("IF NOT EXISTS ")[-1].split(";")[0]
                print(f"  [OK] {name}")
            except Exception as e:
                print(f"  [SKIP] {e}")
        conn.commit()

    print(f"\n{'=' * 60}")
    print("  INDEXES CREATED")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    create_indexes()

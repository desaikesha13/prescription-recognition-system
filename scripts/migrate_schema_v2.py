"""
============================================================================
 SCHEMA MIGRATION V2 — Add extended medicine fields & new tables
============================================================================
 Run once:  python scripts/migrate_schema_v2.py

 Non-destructive: adds columns with IF NOT EXISTS, creates new tables.
 This script uses direct SQL and avoids importing app.py (which triggers
 model queries at import time).
============================================================================
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

# Load env directly (bypass app.py module-level queries)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'config', '.env')
load_dotenv(env_path)

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in config/.env")
    sys.exit(1)


def migrate():
    engine = create_engine(DATABASE_URL)

    print("=" * 60)
    print("  SCHEMA MIGRATION v2")
    print("=" * 60)

    with engine.connect() as conn:
        migrations = [
            # ── Medicine extended fields ──
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(200)",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS dosage_forms TEXT",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS strengths TEXT",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS schedule VARCHAR(10)",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS is_otc BOOLEAN DEFAULT false",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS side_effects TEXT",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS typical_dosage VARCHAR(200)",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS avg_price FLOAT",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT true",
            "ALTER TABLE medicines ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now()",

            # ── Feedback extended fields ──
            "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS feedback_type VARCHAR(20) DEFAULT 'correction'",
            "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS api_confidence VARCHAR(10)",
            "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS db_similarity FLOAT",
            "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS used_in_training BOOLEAN DEFAULT false",

            # ── Indexes on existing tables ──
            "CREATE INDEX IF NOT EXISTS ix_medicine_brand ON medicines (brand)",
            "CREATE INDEX IF NOT EXISTS ix_medicine_generic ON medicines (generic)",
            "CREATE INDEX IF NOT EXISTS ix_medicine_category ON medicines (category)",
        ]

        for sql in migrations:
            try:
                conn.execute(text(sql))
                col_name = sql.split("IF NOT EXISTS ")[-1].split(" ")[0] if "ADD COLUMN" in sql else sql.split("ix_")[-1].split(" ")[0]
                print(f"  [OK] {col_name}")
            except Exception as e:
                print(f"  [SKIP] {e}")
        conn.commit()

        # ── Create new tables via raw SQL ──
        new_tables = [
            """
            CREATE TABLE IF NOT EXISTS medicine_synonyms (
                id SERIAL PRIMARY KEY,
                medicine_id INTEGER NOT NULL REFERENCES medicines(id),
                synonym VARCHAR(200) NOT NULL,
                synonym_type VARCHAR(30)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_synonym_medicine_id ON medicine_synonyms (medicine_id)",
            "CREATE INDEX IF NOT EXISTS ix_synonym_synonym ON medicine_synonyms (synonym)",

            """
            CREATE TABLE IF NOT EXISTS drug_interactions (
                id SERIAL PRIMARY KEY,
                medicine_id INTEGER NOT NULL REFERENCES medicines(id),
                interacts_with_id INTEGER NOT NULL REFERENCES medicines(id),
                severity VARCHAR(20),
                description TEXT,
                clinical_note TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_interaction_medicine_id ON drug_interactions (medicine_id)",
            "CREATE INDEX IF NOT EXISTS ix_interaction_interacts_with ON drug_interactions (interacts_with_id)",
        ]

        for sql in new_tables:
            try:
                conn.execute(text(sql))
                print(f"  [OK] table/index created")
            except Exception as e:
                print(f"  [SKIP] {e}")
        conn.commit()

    # ── Verify ──
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\n  Tables in DB: {', '.join(sorted(tables))}")

    med_cols = [c['name'] for c in inspector.get_columns('medicines')]
    print(f"  Medicine columns: {', '.join(med_cols)}")

    fb_cols = [c['name'] for c in inspector.get_columns('feedback')]
    print(f"  Feedback columns: {', '.join(fb_cols)}")

    if 'medicine_synonyms' in tables:
        syn_cols = [c['name'] for c in inspector.get_columns('medicine_synonyms')]
        print(f"  MedicineSynonym columns: {', '.join(syn_cols)}")

    if 'drug_interactions' in tables:
        int_cols = [c['name'] for c in inspector.get_columns('drug_interactions')]
        print(f"  DrugInteraction columns: {', '.join(int_cols)}")

    print(f"\n{'=' * 60}")
    print("  MIGRATION COMPLETE")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    migrate()

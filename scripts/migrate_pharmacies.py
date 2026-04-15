import sys
import io
import os

# Add project root to sys.path (script moved to scripts/ subdirectory)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def migrate():
    from app import app, db

    with app.app_context():
        conn = db.engine.raw_connection()
        cursor = conn.cursor()

        print("=" * 60)
        print("  PHARMACY TABLE MIGRATION")
        print("=" * 60)

        # -- Add new columns (IF NOT EXISTS) --
        columns = [
            ("place_id",   "VARCHAR(100) UNIQUE"),
            ("city",       "VARCHAR(100)"),
            ("state",      "VARCHAR(100)"),
            ("source",     "VARCHAR(20) DEFAULT 'manual'"),
            ("types",      "TEXT"),
            ("fetched_at", "TIMESTAMP"),
        ]

        for col_name, col_type in columns:
            try:
                cursor.execute(f"""
                    ALTER TABLE pharmacies
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type};
                """)
                print(f"  [OK] Column '{col_name}'")
            except Exception as e:
                print(f"  [FAIL] Column '{col_name}' - {e}")
                conn.rollback()

        # -- Create indexes --
        indexes = [
            ("idx_pharmacies_lat_lng",  "CREATE INDEX IF NOT EXISTS idx_pharmacies_lat_lng ON pharmacies (lat, lng)"),
            ("idx_pharmacies_place_id", "CREATE INDEX IF NOT EXISTS idx_pharmacies_place_id ON pharmacies (place_id)"),
            ("idx_pharmacies_city",     "CREATE INDEX IF NOT EXISTS idx_pharmacies_city ON pharmacies (city)"),
        ]

        for idx_name, idx_sql in indexes:
            try:
                cursor.execute(idx_sql)
                print(f"  [OK] Index  '{idx_name}'")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  [OK] Index  '{idx_name}' - already exists")
                else:
                    print(f"  [FAIL] Index  '{idx_name}' - {e}")
                conn.rollback()

        conn.commit()

        # -- Verify --
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'pharmacies'
            ORDER BY ordinal_position;
        """)
        rows = cursor.fetchall()

        print(f"\n  Current 'pharmacies' table columns:")
        for col_name, data_type in rows:
            print(f"    - {col_name:20s} {data_type}")

        cursor.execute("SELECT COUNT(*) FROM pharmacies;")
        count = cursor.fetchone()[0]
        print(f"\n  Existing pharmacy rows: {count}")

        cursor.close()
        conn.close()

        print(f"\n{'=' * 60}")
        print("  MIGRATION COMPLETE")
        print(f"{'=' * 60}\n")


if __name__ == '__main__':
    migrate()

"""
Database Migration Script for PharmaTrack DW
Safely updates pharmatrack_dw.sqlite schema:
1. Adds category_key, dosage_form_key to dim_product
2. Adds city_key to dim_pharmacy
3. Adds city_key, type_key to dim_hospital
4. Creates organization_verification_requests table
"""
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "pharmatrack_dw.sqlite"

def run_migration():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 1. dim_product columns
    cur.execute("PRAGMA table_info(dim_product);")
    cols = [r[1] for r in cur.fetchall()]
    if "category_key" not in cols:
        cur.execute("ALTER TABLE dim_product ADD COLUMN category_key INTEGER REFERENCES dim_category(category_key);")
    if "dosage_form_key" not in cols:
        cur.execute("ALTER TABLE dim_product ADD COLUMN dosage_form_key INTEGER REFERENCES dim_dosage_form(dosage_form_key);")

    cur.execute("""
        UPDATE dim_product
        SET category_key = (SELECT category_key FROM dim_category WHERE category_name = dim_product.category),
            dosage_form_key = (SELECT dosage_form_key FROM dim_dosage_form WHERE dosage_form_name = dim_product.dosage_form);
    """)

    # 2. dim_pharmacy columns
    cur.execute("PRAGMA table_info(dim_pharmacy);")
    p_cols = [r[1] for r in cur.fetchall()]
    if "city_key" not in p_cols:
        cur.execute("ALTER TABLE dim_pharmacy ADD COLUMN city_key INTEGER REFERENCES dim_city(city_key);")

    cur.execute("""
        UPDATE dim_pharmacy
        SET city_key = (
            SELECT city_key FROM dim_city 
            WHERE dim_city.city_name = dim_pharmacy.city 
               OR dim_pharmacy.city LIKE '%' || dim_city.city_name || '%'
            LIMIT 1
        );
    """)
    cur.execute("UPDATE dim_pharmacy SET city_key = 3 WHERE city_key IS NULL AND (city LIKE '%Chennai%' OR district LIKE '%Chennai%');")
    cur.execute("UPDATE dim_pharmacy SET city_key = 1 WHERE city_key IS NULL AND address LIKE '%Ayapakkam%';")
    cur.execute("UPDATE dim_pharmacy SET city_key = 1 WHERE city_key IS NULL;")

    # 3. dim_hospital columns
    cur.execute("PRAGMA table_info(dim_hospital);")
    h_cols = [r[1] for r in cur.fetchall()]
    if "city_key" not in h_cols:
        cur.execute("ALTER TABLE dim_hospital ADD COLUMN city_key INTEGER REFERENCES dim_city(city_key);")
    if "type_key" not in h_cols:
        cur.execute("ALTER TABLE dim_hospital ADD COLUMN type_key INTEGER REFERENCES dim_hospital_type(type_key);")

    cur.execute("""
        UPDATE dim_hospital
        SET city_key = (
            SELECT city_key FROM dim_city 
            WHERE dim_city.city_name = dim_hospital.city 
               OR dim_hospital.city LIKE '%' || dim_city.city_name || '%'
            LIMIT 1
        ),
        type_key = (
            SELECT type_key FROM dim_hospital_type 
            WHERE dim_hospital_type.type_name = dim_hospital.hospital_type
            LIMIT 1
        );
    """)
    cur.execute("UPDATE dim_hospital SET city_key = 3 WHERE city_key IS NULL;")
    cur.execute("UPDATE dim_hospital SET type_key = 1 WHERE type_key IS NULL;")

    # 4. organization_verification_requests table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS organization_verification_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            organization_name TEXT NOT NULL,
            registration_number TEXT,
            contact_phone TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION',
            notes TEXT,
            submitted_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_users(user_id)
        );
    """)

    conn.commit()
    conn.close()
    print("Database schema migration completed successfully.")

if __name__ == "__main__":
    run_migration()


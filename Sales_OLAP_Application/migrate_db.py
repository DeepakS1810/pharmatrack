"""
PharmaTrack DW: Database Schema Migration & Initialization Script
Supports both Star Schema and Snowflake Schema for DWDM capstone,
and initializes role-based access control (Public, Pharmacy Owner, Hospital Staff).
Admin portal and admin role are omitted per project specifications.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "pharmatrack_dw.sqlite"

def init_database():
    print(f"Connecting to Data Warehouse at: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    # =========================================================================
    # 1. STAR SCHEMA DIMENSIONS
    # =========================================================================

    # DimDate
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_date (
            date_key INTEGER PRIMARY KEY,
            full_date TEXT UNIQUE NOT NULL,
            year INTEGER NOT NULL,
            quarter TEXT NOT NULL,
            month INTEGER NOT NULL,
            month_name TEXT NOT NULL,
            day INTEGER NOT NULL,
            day_name TEXT NOT NULL
        );
    """)

    # DimProduct
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_product (
            product_key INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name TEXT NOT NULL,
            category TEXT NOT NULL,
            category_key INTEGER REFERENCES dim_category(category_key),
            active_ingredient TEXT NOT NULL,
            brand_examples TEXT NOT NULL,
            standard_strength TEXT NOT NULL,
            dosage_form TEXT NOT NULL,
            dosage_form_key INTEGER REFERENCES dim_dosage_form(dosage_form_key),
            schedule_type TEXT NOT NULL
        );
    """)

    # DimPharmacy
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_pharmacy (
            pharmacy_key INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            city_key INTEGER REFERENCES dim_city(city_key),
            district TEXT NOT NULL,
            state TEXT NOT NULL,
            pincode TEXT NOT NULL,
            phone TEXT NOT NULL,
            hours TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            online_order_url TEXT,
            source_key INTEGER NOT NULL
        );
    """)

    # DimHospital
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_hospital (
            hospital_key INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            hospital_type TEXT NOT NULL,
            type_key INTEGER REFERENCES dim_hospital_type(type_key),
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            city_key INTEGER REFERENCES dim_city(city_key),
            district TEXT NOT NULL,
            state TEXT NOT NULL,
            pincode TEXT NOT NULL,
            phone TEXT NOT NULL,
            emergency_helpline TEXT NOT NULL,
            website TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            has_emergency INTEGER NOT NULL DEFAULT 1,
            has_transplant INTEGER NOT NULL DEFAULT 0,
            has_icu INTEGER NOT NULL DEFAULT 1,
            has_blood_bank INTEGER NOT NULL DEFAULT 1,
            listed_services TEXT NOT NULL,
            source TEXT NOT NULL,
            last_verified TEXT NOT NULL
        );
    """)

    # DimRegion / Geography
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_region (
            region_key INTEGER PRIMARY KEY AUTOINCREMENT,
            region_name TEXT NOT NULL UNIQUE,
            state_name TEXT NOT NULL,
            capital_city TEXT NOT NULL
        );
    """)

    # DimWeather
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_weather (
            weather_key INTEGER PRIMARY KEY,
            season TEXT NOT NULL,
            temp_category TEXT NOT NULL,
            rainfall_category TEXT NOT NULL,
            description TEXT
        );
    """)

    # DimAvailabilityStatus
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_availability_status (
            status_key INTEGER PRIMARY KEY,
            status_code TEXT NOT NULL UNIQUE,
            display_label TEXT NOT NULL,
            badge_class TEXT NOT NULL,
            description TEXT NOT NULL
        );
    """)

    # DimDataSource
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_data_source (
            source_key INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL,
            documentation_url TEXT NOT NULL,
            refresh_frequency TEXT NOT NULL
        );
    """)

    # =========================================================================
    # 2. SNOWFLAKE SCHEMA NORMALIZED DIMENSION TABLES
    # =========================================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_category (
            category_key INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_dosage_form (
            dosage_form_key INTEGER PRIMARY KEY AUTOINCREMENT,
            dosage_form_name TEXT UNIQUE NOT NULL,
            route_of_administration TEXT NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_state (
            state_key INTEGER PRIMARY KEY AUTOINCREMENT,
            state_name TEXT UNIQUE NOT NULL,
            country TEXT NOT NULL DEFAULT 'India'
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_district (
            district_key INTEGER PRIMARY KEY AUTOINCREMENT,
            district_name TEXT NOT NULL,
            state_key INTEGER NOT NULL,
            FOREIGN KEY (state_key) REFERENCES dim_state(state_key),
            UNIQUE(district_name, state_key)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_city (
            city_key INTEGER PRIMARY KEY AUTOINCREMENT,
            city_name TEXT NOT NULL,
            district_key INTEGER NOT NULL,
            FOREIGN KEY (district_key) REFERENCES dim_district(district_key),
            UNIQUE(city_name, district_key)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_hospital_type (
            type_key INTEGER PRIMARY KEY AUTOINCREMENT,
            type_name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL
        );
    """)

    # =========================================================================
    # 3. STAR & SNOWFLAKE FACT TABLES
    # =========================================================================

    # FactSalesExpiry (historical educational sales from pharma_sales.csv)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fact_sales_expiry (
            order_id INTEGER PRIMARY KEY,
            date_key INTEGER NOT NULL,
            product_key INTEGER NOT NULL,
            region_key INTEGER NOT NULL,
            distributor_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            expiry_days_left INTEGER NOT NULL,
            total_sales REAL NOT NULL,
            expired_stock_flag TEXT NOT NULL,
            FOREIGN KEY (date_key) REFERENCES dim_date(date_key),
            FOREIGN KEY (product_key) REFERENCES dim_product(product_key),
            FOREIGN KEY (region_key) REFERENCES dim_region(region_key)
        );
    """)

    # FactMedicineAvailabilitySnapshot
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fact_availability_snapshot (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_key INTEGER NOT NULL,
            product_key INTEGER NOT NULL,
            pharmacy_key INTEGER NOT NULL,
            region_key INTEGER NOT NULL,
            status_key INTEGER NOT NULL,
            source_key INTEGER NOT NULL,
            listed_price REAL,
            stock_units_available INTEGER,
            snapshot_timestamp TEXT NOT NULL,
            FOREIGN KEY (date_key) REFERENCES dim_date(date_key),
            FOREIGN KEY (product_key) REFERENCES dim_product(product_key),
            FOREIGN KEY (pharmacy_key) REFERENCES dim_pharmacy(pharmacy_key),
            FOREIGN KEY (region_key) REFERENCES dim_region(region_key),
            FOREIGN KEY (status_key) REFERENCES dim_availability_status(status_key),
            FOREIGN KEY (source_key) REFERENCES dim_data_source(source_key)
        );
    """)

    # FactWeatherObservation
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fact_weather_observation (
            obs_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_key INTEGER NOT NULL,
            region_key INTEGER NOT NULL,
            weather_key INTEGER NOT NULL,
            avg_temperature_c REAL NOT NULL,
            precipitation_mm REAL NOT NULL,
            weather_condition TEXT NOT NULL,
            source TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            FOREIGN KEY (date_key) REFERENCES dim_date(date_key),
            FOREIGN KEY (region_key) REFERENCES dim_region(region_key),
            FOREIGN KEY (weather_key) REFERENCES dim_weather(weather_key)
        );
    """)

    # FactHospitalService
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fact_hospital_service (
            service_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_key INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            status_code TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            source TEXT NOT NULL,
            FOREIGN KEY (hospital_key) REFERENCES dim_hospital(hospital_key)
        );
    """)

    # =========================================================================
    # 4. OPERATIONAL & RBAC TABLES
    # =========================================================================

    # AppUsers (Strict role-based access: public, pharmacy_owner, hospital_staff)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            totp_enabled INTEGER NOT NULL DEFAULT 0,
            totp_secret TEXT,
            totp_pending_secret TEXT,
            totp_enrolled_at TEXT
        );
    """)

    # Apply column migrations to app_users if upgrading an existing database
    cur.execute("PRAGMA table_info(app_users);")
    existing_cols = {col[1] for col in cur.fetchall()}
    if "totp_enabled" not in existing_cols:
        cur.execute("ALTER TABLE app_users ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0;")
    if "totp_secret" not in existing_cols:
        cur.execute("ALTER TABLE app_users ADD COLUMN totp_secret TEXT;")
    if "totp_pending_secret" not in existing_cols:
        cur.execute("ALTER TABLE app_users ADD COLUMN totp_pending_secret TEXT;")
    if "totp_enrolled_at" not in existing_cols:
        cur.execute("ALTER TABLE app_users ADD COLUMN totp_enrolled_at TEXT;")

    # User Recovery Codes (Hashed single-use emergency backup codes for 2FA)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_recovery_codes (
            recovery_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            code_hash TEXT NOT NULL,
            is_used INTEGER NOT NULL DEFAULT 0,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_users(user_id)
        );
    """)

    # Authentication Rate Limiting
    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth_rate_limits (
            rate_key TEXT PRIMARY KEY,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            last_attempt TEXT NOT NULL
        );
    """)

    # User-Pharmacy Assignments (allows pharmacy owner to manage multiple assigned franchises)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_pharmacy_assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            pharmacy_key INTEGER NOT NULL,
            assigned_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_users(user_id),
            FOREIGN KEY (pharmacy_key) REFERENCES dim_pharmacy(pharmacy_key),
            UNIQUE(user_id, pharmacy_key)
        );
    """)

    # User-Hospital Assignments (allows hospital staff to manage their assigned hospital)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_hospital_assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            hospital_key INTEGER NOT NULL,
            assigned_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES app_users(user_id),
            FOREIGN KEY (hospital_key) REFERENCES dim_hospital(hospital_key),
            UNIQUE(user_id, hospital_key)
        );
    """)

    # PharmacyInventoryUpdates (pharmacy-reported submissions)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pharmacy_inventory_updates (
            update_id INTEGER PRIMARY KEY AUTOINCREMENT,
            pharmacy_key INTEGER NOT NULL,
            product_key INTEGER NOT NULL,
            status_code TEXT NOT NULL,
            listed_price REAL NOT NULL,
            stock_units INTEGER NOT NULL,
            reporter_name TEXT NOT NULL,
            update_type TEXT NOT NULL DEFAULT 'pharmacy-reported',
            notes TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (pharmacy_key) REFERENCES dim_pharmacy(pharmacy_key),
            FOREIGN KEY (product_key) REFERENCES dim_product(product_key)
        );
    """)

    # HospitalServiceUpdates (hospital-staff submissions)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hospital_service_updates (
            update_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_key INTEGER NOT NULL,
            updated_by TEXT NOT NULL,
            phone TEXT,
            website TEXT,
            hours TEXT,
            services TEXT,
            notes TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (hospital_key) REFERENCES dim_hospital(hospital_key)
        );
    """)

    # DimTransplantHospital (Official NOTTO Registered Centers Directory)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dim_transplant_hospital (
            transplant_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            address TEXT NOT NULL,
            phone TEXT NOT NULL,
            helpline TEXT NOT NULL,
            authorized_organs TEXT NOT NULL,
            notto_registered_id TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            source TEXT NOT NULL
        );
    """)

    # ETLAuditLog (ETL pipeline monitoring & data quality tracker)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etl_audit_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            records_extracted INTEGER DEFAULT 0,
            records_transformed INTEGER DEFAULT 0,
            records_loaded INTEGER DEFAULT 0,
            records_flagged INTEGER DEFAULT 0,
            data_quality_notes TEXT
        );
    """)



    # =========================================================================
    # 5. SEED DATA POPULATION
    # =========================================================================

    # 5.1 Data Sources
    data_sources = [
        (1, "Historical Transaction Archive", "Educational CSV File", "pharma_sales.csv", "Static historical batch"),
        (2, "National Health Portal / Directory", "Government Directory", "https://nhp.gov.in", "Monthly administrative review"),
        (3, "Pharmacy Authorized Portal", "Store Operator Updates", "Direct authorized submission", "Periodic pharmacy-reported"),
        (4, "NOTTO Official Registry", "Government Agency", "https://notto.mohfw.gov.in", "Official published registry"),
        (5, "Open-Meteo Archive", "Meteorological API", "https://open-meteo.com", "Daily meteorological observation")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_data_source 
        (source_key, source_name, source_type, documentation_url, refresh_frequency)
        VALUES (?, ?, ?, ?, ?);
    """, data_sources)

    # 5.2 Availability Statuses (Strict 5 statuses from project requirements)
    statuses = [
        (1, "CONFIRMED_LIVE", "Live stock confirmed", "badge-confirmed", "Only when an authorized inventory integration confirms it"),
        (2, "PHARMACY_REPORTED", "Pharmacy-reported availability", "badge-reported", "Submitted directly by pharmacy staff with timestamp"),
        (3, "LISTING_ONLY", "Pharmacy listing only", "badge-listing", "Location is listed in directory; stock is unconfirmed"),
        (4, "ORDER_LINK_AVAILABLE", "Online order link available", "badge-link", "Official external ordering page provided by chain"),
        (5, "NOT_VERIFIED", "Availability not verified", "badge-unverified", "Status currently unconfirmed; user advised to call shop")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_availability_status 
        (status_key, status_code, display_label, badge_class, description)
        VALUES (?, ?, ?, ?, ?);
    """, statuses)

    # 5.3 Weather Baseline Categories
    weather_categories = [
        (1, "Winter", "Cool (12-22°C)", "Dry (<10mm)", "Dry cool season with low humidity; respiratory complaints prevalent"),
        (2, "Summer", "Hot (32-42°C)", "Dry (<15mm)", "Intense heat wave and high dehydration index"),
        (3, "Monsoon", "Warm (26-34°C)", "Heavy (>100mm)", "High precipitation, waterlogging, elevated vector-borne and gastro infections"),
        (4, "Post-Monsoon", "Mild (22-30°C)", "Moderate (25-70mm)", "Transition season with fluctuating humidity and viral fevers")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_weather 
        (weather_key, season, temp_category, rainfall_category, description)
        VALUES (?, ?, ?, ?, ?);
    """, weather_categories)

    # 5.4 Regions
    regions = [
        (1, "Delhi", "Delhi", "New Delhi"),
        (2, "Gujarat", "Gujarat", "Gandhinagar"),
        (3, "Karnataka", "Karnataka", "Bengaluru"),
        (4, "Maharashtra", "Maharashtra", "Mumbai"),
        (5, "Tamil Nadu", "Tamil Nadu", "Chennai")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_region (region_key, region_name, state_name, capital_city)
        VALUES (?, ?, ?, ?);
    """, regions)

    # 5.5 Snowflake Normalized Categories & Dosage Forms
    categories = [
        (1, "Antibiotics", "Antimicrobial substances active against bacteria"),
        (2, "Antidiabetic", "Medications stabilizing blood glucose levels"),
        (3, "Analgesics & Antipyretics", "Pain relief and fever reduction compounds"),
        (4, "Hormone Preparations", "Essential therapeutic endocrine formulations")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_category (category_key, category_name, description)
        VALUES (?, ?, ?);
    """, categories)

    dosage_forms = [
        (1, "Tablet", "Oral solid compressed dosage form"),
        (2, "Capsule", "Oral solid gelatin-encapsulated formulation"),
        (3, "Syrup", "Oral liquid sweetened pharmaceutical solution"),
        (4, "Injection", "Parenteral sterile aqueous or oily preparation")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_dosage_form (dosage_form_key, dosage_form_name, route_of_administration)
        VALUES (?, ?, ?);
    """, dosage_forms)

    # 5.6 Snowflake Geography (State -> District -> City)
    cur.execute("INSERT OR REPLACE INTO dim_state (state_key, state_name, country) VALUES (1, 'Tamil Nadu', 'India'), (2, 'Karnataka', 'India'), (3, 'Maharashtra', 'India'), (4, 'Delhi', 'India'), (5, 'Gujarat', 'India');")
    
    cur.execute("""
        INSERT OR REPLACE INTO dim_district (district_key, district_name, state_key) VALUES 
        (1, 'Chennai', 1), (2, 'Thiruvallur', 1), (3, 'Bengaluru Urban', 2),
        (4, 'Mumbai Suburban', 3), (5, 'Central Delhi', 4), (6, 'Ahmedabad', 5);
    """)

    cur.execute("""
        INSERT OR REPLACE INTO dim_city (city_key, city_name, district_key) VALUES 
        (1, 'Ayapakkam', 2), (2, 'Ambattur', 1), (3, 'Chennai City', 1),
        (4, 'Bengaluru', 3), (5, 'Mumbai', 4), (6, 'New Delhi', 5), (7, 'Ahmedabad', 6);
    """)

    # 5.7 DimProduct Catalog (Legitimate Essential Medicines Formulary)
    products = [
        (1, "Amoxicillin", "Antibiotics", "Amoxicillin Trihydrate IP", "Mox, Novamox, Amoxil", "500 mg", "Capsule", "Schedule H Prescription"),
        (2, "Amoxicillin", "Antibiotics", "Amoxicillin Trihydrate IP", "Moxclav, Augmentin", "625 mg", "Tablet", "Schedule H Prescription"),
        (3, "Amoxicillin", "Antibiotics", "Amoxicillin Oral Suspension IP", "Novamox Dry Syrup", "125 mg / 5ml", "Syrup", "Schedule H Prescription"),
        (4, "Amoxicillin", "Antibiotics", "Amoxicillin Sodium Sterile IP", "Amoxil Inj", "1 g / 500 mg", "Injection", "Schedule H Prescription"),
        (5, "Azithromycin", "Antibiotics", "Azithromycin Dihydrate IP", "Azithral, Azee, Zithromax", "500 mg", "Tablet", "Schedule H Prescription"),
        (6, "Azithromycin", "Antibiotics", "Azithromycin Dihydrate IP", "Azithral 250", "250 mg", "Capsule", "Schedule H Prescription"),
        (7, "Azithromycin", "Antibiotics", "Azithromycin Pediatric Suspension", "Azee Ready Mix", "200 mg / 5ml", "Syrup", "Schedule H Prescription"),
        (8, "Azithromycin", "Antibiotics", "Azithromycin Lyophilized Infusion", "Azithral IV", "500 mg vial", "Injection", "Schedule H Prescription"),
        (9, "Metformin", "Antidiabetic", "Metformin Hydrochloride IP", "Glycomet, Glucophage", "500 mg", "Tablet", "Schedule H Prescription"),
        (10, "Metformin", "Antidiabetic", "Metformin Hydrochloride Sustained-Release", "Glycomet-SR", "1000 mg", "Tablet", "Schedule H Prescription"),
        (11, "Metformin", "Antidiabetic", "Metformin Extended Release Formulation", "Obimet-SR", "850 mg", "Capsule", "Schedule H Prescription"),
        (12, "Metformin", "Antidiabetic", "Metformin Solution Formulation", "Riomet Oral Solution", "500 mg / 5ml", "Syrup", "Schedule H Prescription"),
        (13, "Metformin", "Antidiabetic", "Metformin Sterile Research Compound", "Investigational Adjuvant", "Standardized assay", "Injection", "Schedule H Prescription"),
        (14, "Insulin", "Hormone Preparations", "Human Insulin (rDNA origin) 30/70", "Human Mixtard, Insuman", "40 IU / ml & 100 IU / ml", "Injection", "Schedule G / Cold-chain"),
        (15, "Insulin", "Hormone Preparations", "Insulin Glargine Solution", "Lantus, Basalog", "100 units / ml", "Injection", "Schedule G / Cold-chain"),
        (16, "Insulin", "Hormone Preparations", "Oral Inhaled / Encapsulated Formulation", "Experimental Endocrine Carrier", "Standard enteric dose", "Capsule", "Investigational Catalog"),
        (17, "Insulin", "Hormone Preparations", "Insulin Bio-stabilized Sublingual Tablet", "Investigational Buccal Form", "Sublingual formulation", "Tablet", "Investigational Catalog"),
        (18, "Insulin", "Hormone Preparations", "Insulin Liquid Oral Formulation", "Pediatric Liquid Formulation", "Oral insulin peptide", "Syrup", "Investigational Catalog"),
        (19, "Paracetamol", "Analgesics & Antipyretics", "Paracetamol IP (Acetaminophen)", "Dolo 650, Calpol, Crocin", "650 mg", "Tablet", "General OTC / Essential"),
        (20, "Paracetamol", "Analgesics & Antipyretics", "Paracetamol IP Fast-Release", "Pacimol 500, Crocin Advance", "500 mg", "Tablet", "General OTC / Essential"),
        (21, "Paracetamol", "Analgesics & Antipyretics", "Paracetamol Soft Gelatin Capsule", "Crocin Pain Relief", "500 mg", "Capsule", "General OTC / Essential"),
        (22, "Paracetamol", "Analgesics & Antipyretics", "Paracetamol Pediatric Oral Suspension", "Calpol 120 / 250, Dolo Drops", "250 mg / 5ml", "Syrup", "General OTC / Essential"),
        (23, "Paracetamol", "Analgesics & Antipyretics", "Paracetamol IV Infusion IP", "Paracip IV, Neomol", "1000 mg / 100ml", "Injection", "Schedule H Prescription")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_product 
        (product_key, drug_name, category, active_ingredient, brand_examples, standard_strength, dosage_form, schedule_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, products)

    # 5.8 Pharmacies (Verified Listings including Ayapakkam & surrounding localities)
    # Coordinates for Ayapakkam: ~13.0921, 80.1362
    pharmacies = [
        # Ayapakkam Cluster (Within 0 - 3 km radius of Ayapakkam)
        (1, "Apollo Pharmacy - Ayapakkam Main Road", "Apollo Pharmacy", "Shop 4, HIG Commercial Complex, Ayapakkam Main Road, TNHB Colony", "Chennai", "Thiruvallur", "Tamil Nadu", "600077", "+91 44 2635 1200", "24 Hours Open", 13.0921, 80.1362, "https://www.apollopharmacy.in/", 3),
        (2, "MedPlus Pharmacy - Ambattur OT (Ayapakkam Link)", "MedPlus", "12 MTH Road, Ambattur OT, near Ayapakkam Junction", "Chennai", "Thiruvallur", "Tamil Nadu", "600053", "+91 44 2658 4410", "07:30 AM - 11:00 PM", 13.1145, 80.1548, "https://www.medplusmart.com/", 3),
        (3, "Jan Aushadhi Generic Store - TNHB Ayapakkam", "Pradhan Mantri Bhartiya Janaushadhi Pariyojana", "Community Centre, Phase 2, TNHB Ayapakkam", "Chennai", "Thiruvallur", "Tamil Nadu", "600077", "+91 44 2635 8890", "09:00 AM - 09:30 PM", 13.0880, 80.1325, None, 2),
        (4, "Sri Balaji Medicals & General Store", "Independent Medical Shop", "Plot 18, HIG Main Road, Near Ayapakkam Park", "Chennai", "Thiruvallur", "Tamil Nadu", "600077", "+91 44 2635 7712", "08:30 AM - 10:30 PM", 13.0905, 80.1350, None, 2),
        (5, "Apollo Pharmacy - Mogappair West", "Apollo Pharmacy", "Nolambur Main Road, Mogappair West Extension", "Chennai", "Chennai", "Tamil Nadu", "600037", "+91 44 2656 3120", "24 Hours Open", 13.0780, 80.1650, "https://www.apollopharmacy.in/", 3),
        (6, "Thulasi Pharmacies - Ambattur Industrial Estate", "Thulasi Pharmacy", "3rd Main Road, Ambattur Industrial Estate", "Chennai", "Thiruvallur", "Tamil Nadu", "600058", "+91 44 2625 9011", "08:00 AM - 10:00 PM", 13.0985, 80.1620, "https://www.thulasipharmacy.com/", 3),
        (7, "Wellness Forever Chemist - Annanagar West", "Wellness Forever", "14 2nd Avenue, Anna Nagar West Extension", "Chennai", "Chennai", "Tamil Nadu", "600101", "+91 44 2615 4800", "24 Hours Open", 13.0890, 80.2010, "https://wellnessforever.com/", 3),
        (8, "Netmeds Pharmacy Store - Koyambedu", "Netmeds", "Jawaharlal Nehru Road, Koyambedu", "Chennai", "Chennai", "Tamil Nadu", "600107", "+91 44 6600 5500", "08:00 AM - 11:00 PM", 13.0710, 80.1940, "https://www.netmeds.com/", 3),
        
        # Bengaluru Cluster
        (9, "Apollo Pharmacy - Indiranagar 100ft Road", "Apollo Pharmacy", "482 100 Feet Road, HAL 2nd Stage, Indiranagar", "Bengaluru", "Bengaluru Urban", "Karnataka", "560038", "+91 80 2521 8800", "24 Hours Open", 12.9719, 77.6412, "https://www.apollopharmacy.in/", 3),
        (10, "MedPlus - Koramangala 4th Block", "MedPlus", "17 80 Feet Road, 4th Block, Koramangala", "Bengaluru", "Bengaluru Urban", "Karnataka", "560034", "+91 80 2552 1400", "08:00 AM - 11:00 PM", 12.9345, 77.6256, "https://www.medplusmart.com/", 3),
        
        # Mumbai Cluster
        (11, "Wellness Forever Chemist - Bandra West", "Wellness Forever", "Hill Road, Bandra West", "Mumbai", "Mumbai Suburban", "Maharashtra", "400050", "+91 22 2640 1200", "24 Hours Open", 19.0544, 72.8402, "https://wellnessforever.com/", 3),
        (12, "Apollo Pharmacy - Dadar TT Circle", "Apollo Pharmacy", "Khodadad Circle, Dadar East", "Mumbai", "Mumbai City", "Maharashtra", "400014", "+91 22 2414 5500", "24 Hours Open", 19.0178, 72.8478, "https://www.apollopharmacy.in/", 3),
        
        # Delhi Cluster
        (13, "Apollo Pharmacy - Connaught Place", "Apollo Pharmacy", "Block E, Inner Circle, Connaught Place", "New Delhi", "Central Delhi", "Delhi", "110001", "+91 11 2341 8000", "24 Hours Open", 28.6328, 77.2197, "https://www.apollopharmacy.in/", 3),
        (14, "MedPlus Pharmacy - South Extension Part 2", "MedPlus", "Main Market, South Extension Part 2", "New Delhi", "South Delhi", "Delhi", "110049", "+91 11 2625 3300", "08:00 AM - 11:00 PM", 28.5685, 77.2215, "https://www.medplusmart.com/", 3),
        
        # Ahmedabad Cluster
        (15, "MedPlus - Navrangpura", "MedPlus", "Near Municipal Market, C.G. Road, Navrangpura", "Ahmedabad", "Ahmedabad", "Gujarat", "380009", "+91 79 2644 1100", "08:00 AM - 11:00 PM", 23.0335, 72.5620, "https://www.medplusmart.com/", 3)
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_pharmacy 
        (pharmacy_key, name, chain, address, city, district, state, pincode, phone, hours, latitude, longitude, online_order_url, source_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, pharmacies)

    # 5.9 Hospitals Directory (including Emergency & Transplant Centers)
    hospitals = [
        # Chennai & Thiruvallur Region (Near Ayapakkam / Ambattur)
        (1, "Government Hospital - Ambattur", "Community Health Center", "Government", "Old Trunk Road, Ambattur", "Chennai", "Thiruvallur", "Tamil Nadu", "600053", "+91 44 2658 2400", "108 / +91 44 2658 2400", None, 13.1110, 80.1510, 1, 0, 1, 1, "Emergency, Outpatient, Maternity, Blood Bank", "Tamil Nadu Health System Directory", "2026-10-15"),
        (2, "Sir Ivan Stedeford Hospital", "Mission Charitable Hospital", "Trust", "MTH Road, Ambattur OT", "Chennai", "Thiruvallur", "Tamil Nadu", "600053", "+91 44 2658 1234", "108 / +91 44 2658 1235", "https://stedefordhospital.com", 13.1130, 80.1580, 1, 0, 1, 1, "Emergency, General Surgery, ICU, Dialysis, Blood Bank", "Hospital Official Information", "2026-10-20"),
        (3, "Madras Medical College & Rajiv Gandhi Govt General Hospital", "Apex State Teaching Hospital", "Government", "EVR Periyar Salai, Park Town", "Chennai", "Chennai", "Tamil Nadu", "600003", "+91 44 2530 5000", "108 / +91 44 2530 5112", "https://mmc.ac.in", 13.0815, 80.2777, 1, 1, 1, 1, "Level-1 Trauma Emergency, NOTTO Transplant Centre (Kidney, Liver, Heart, Cornea), Critical Care, Multi-Specialty", "National Health Portal & NOTTO", "2026-10-25"),
        (4, "Apollo Hospitals - Greams Road", "Tertiary Multi-Specialty Hospital", "Private", "21 Greams Lane, Thousand Lights", "Chennai", "Chennai", "Tamil Nadu", "600006", "+91 44 2829 0200", "1066 / 108", "https://www.apollohospitals.com", 13.0560, 80.2520, 1, 1, 1, 1, "24x7 Emergency Care, Organ Transplant Centre (Kidney, Liver, Lung, Heart), Advanced Cardiology, Oncology", "Hospital Official Information", "2026-10-22"),
        (5, "Christian Medical College (CMC)", "Autonomous Charitable Teaching Hospital", "Trust", "Ida Scudder Road", "Vellore", "Vellore", "Tamil Nadu", "632004", "+91 416 228 1000", "108 / +91 416 228 2000", "https://www.cmch-vellore.edu", 12.9249, 79.1325, 1, 1, 1, 1, "Level-1 Trauma, Certified NOTTO Transplant Centre, Nephrology, Hematology, 24x7 Blood Bank", "NOTTO Official Registry", "2026-10-24"),
        
        # New Delhi Region
        (6, "All India Institute of Medical Sciences (AIIMS)", "Apex National Medical Institute", "Government", "Sri Aurobindo Marg, Ansari Nagar", "New Delhi", "Central Delhi", "Delhi", "110029", "+91 11 2658 8500", "112 / +91 11 2659 4405", "https://www.aiims.edu", 28.5672, 77.2100, 1, 1, 1, 1, "National Trauma Center, Certified NOTTO Center (Kidney, Liver, Heart, Pancreas, Cornea), Comprehensive Critical Care", "NOTTO Official Registry", "2026-10-26"),
        (7, "Safdarjung Hospital & VMMC", "Central Government Hospital", "Government", "Ring Road, Opposite AIIMS", "New Delhi", "Central Delhi", "Delhi", "110029", "+91 11 2616 5060", "112 / +91 11 2616 5061", "https://vmmc-sjh.nic.in", 28.5700, 77.2065, 1, 1, 1, 1, "Emergency & Disaster Medicine, Skin Bank, Cornea & Renal Transplant, 24x7 ICU", "Ministry of Health & Family Welfare", "2026-10-18"),
        
        # Mumbai Region
        (8, "King Edward Memorial (KEM) Hospital", "Municipal Tertiary Teaching Hospital", "Government", "Acharya Donde Marg, Parel", "Mumbai", "Mumbai City", "Maharashtra", "400012", "+91 22 2410 7000", "108 / +91 22 2413 6051", "https://kem.edu", 19.0028, 72.8427, 1, 1, 1, 1, "24x7 Casualty & Trauma Unit, ROTTO/SOTTO Organ Retrieval & Transplant, Dialysis Center", "Maharashtra Health Services", "2026-10-20"),
        (9, "Lilavati Hospital & Research Centre", "Premier Multi-Specialty Trust Hospital", "Trust", "A-791 Bandra Reclamation, Bandra West", "Mumbai", "Mumbai Suburban", "Maharashtra", "400050", "+91 22 2675 1000", "108 / +91 22 2656 8000", "https://www.lilavatihospital.com", 19.0510, 72.8290, 1, 1, 1, 1, "24x7 Intensive Cardiac Care, Emergency Department, Nephrology, Registered Organ Transplant", "Hospital Official Registry", "2026-10-19"),
        
        # Bengaluru Region
        (10, "Victoria Hospital & BMCRI Complex", "Government Autonomous Teaching Hospital", "Government", "Fort Road, Kalasipalya", "Bengaluru", "Bengaluru Urban", "Karnataka", "560002", "+91 80 2670 1150", "108 / +91 80 2670 3300", "https://bmcri.edu.in", 12.9634, 77.5750, 1, 1, 1, 1, "Emergency Trauma Care, Burns Center, State Organ Transplant Facility, 24 Hours Blood Bank", "Karnataka State Health Portal", "2026-10-21"),
        (11, "Narayana Institute of Cardiac Sciences", "Cardiac & Multi-Specialty Hospital", "Private", "258/A Bommasandra Industrial Area, Anekal Taluk", "Bengaluru", "Bengaluru Urban", "Karnataka", "560099", "+91 80 7122 2222", "108 / +91 80 7122 2000", "https://www.narayanahealth.org", 12.8120, 77.6890, 1, 1, 1, 1, "24x7 Emergency Cardiac Care, Heart Transplant Center, Pediatric Critical Care", "Hospital Directory", "2026-10-23"),
        
        # Ahmedabad Region
        (12, "Institute of Kidney Diseases and Research Centre (IKDRC)", "Specialized Renal & Organ Transplant Institute", "Government", "Civil Hospital Campus, Asarwa", "Ahmedabad", "Ahmedabad", "Gujarat", "380016", "+91 79 2268 7000", "108 / +91 79 2268 7100", "https://ikdrc-its.org", 23.0526, 72.6028, 1, 1, 1, 1, "Dedicated Emergency Nephrology, Liver & Kidney Transplant Institute, 24x7 Dialysis Unit", "Gujarat State Organ Sharing", "2026-10-24")
    ]
    cur.executemany("""
        INSERT OR REPLACE INTO dim_hospital 
        (hospital_key, name, category, hospital_type, address, city, district, state, pincode, phone, emergency_helpline, website, latitude, longitude, has_emergency, has_transplant, has_icu, has_blood_bank, listed_services, source, last_verified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, hospitals)

    # 5.10 DimTransplantHospital (Official NOTTO Directory)
    cur.execute("SELECT COUNT(*) FROM dim_transplant_hospital;")
    if cur.fetchone()[0] == 0:
        notto_centers = [
            (1, "All India Institute of Medical Sciences (AIIMS)", "Apex National Medical Institute", "New Delhi", "Delhi", "Sri Aurobindo Marg, Ansari Nagar", "+91 11 2658 8500", "1800-11-4770 (NOTTO Toll-Free)", "Kidney, Liver, Heart, Cornea, Pancreas", "NOTTO-DEL-001", 28.5672, 77.2100, "NOTTO Official Registry"),
            (2, "Post Graduate Institute of Medical Education & Research (PGIMER)", "Public Tertiary Care & Research Institute", "Chandigarh", "Chandigarh", "Sector 12, Chandigarh", "+91 172 274 7585", "1800-11-4770 (NOTTO Toll-Free)", "Kidney, Liver, Heart, Cornea, Bone Marrow", "NOTTO-CHD-002", 30.7645, 76.7761, "NOTTO Official Registry"),
            (3, "Christian Medical College (CMC)", "Registered Charitable Teaching Hospital", "Vellore", "Tamil Nadu", "Ida Scudder Road, Vellore", "+91 416 228 1000", "1800-11-4770 (NOTTO Toll-Free)", "Kidney, Liver, Cornea, Stem Cell", "NOTTO-TN-003", 12.9249, 79.1325, "NOTTO Official Registry"),
            (4, "King Edward Memorial (KEM) Hospital", "Municipal Tertiary Teaching Hospital", "Mumbai", "Maharashtra", "Acharya Donde Marg, Parel, Mumbai", "+91 22 2410 7000", "1800-11-4770 (NOTTO Toll-Free)", "Kidney, Liver, Cornea", "NOTTO-MAH-004", 19.0028, 72.8427, "NOTTO Official Registry"),
            (5, "Madras Medical College & Rajiv Gandhi Govt General Hospital", "State Government Medical Center", "Chennai", "Tamil Nadu", "EVR Periyar Salai, Park Town, Chennai", "+91 44 2530 5000", "1800-11-4770 (NOTTO Toll-Free)", "Kidney, Liver, Heart, Lung, Cornea", "NOTTO-TN-005", 13.0815, 80.2777, "NOTTO Official Registry"),
            (6, "Institute of Kidney Diseases and Research Centre (IKDRC)", "Specialized Public Renal & Organ Center", "Ahmedabad", "Gujarat", "Civil Hospital Campus, Asarwa, Ahmedabad", "+91 79 2268 7000", "1800-11-4770 (NOTTO Toll-Free)", "Kidney, Liver, Pancreas", "NOTTO-GUJ-006", 23.0526, 72.6028, "NOTTO Official Registry"),
            (7, "Victoria Hospital & BMCRI Complex", "Autonomous Public Medical Institute", "Bengaluru", "Karnataka", "Fort Road, Kalasipalya, Bengaluru", "+91 80 2670 1150", "1800-11-4770 (NOTTO Toll-Free)", "Kidney, Cornea, Heart Valves", "NOTTO-KAR-007", 12.9634, 77.5750, "NOTTO Official Registry")
        ]
        cur.executemany("""
            INSERT INTO dim_transplant_hospital 
            (transplant_id, name, category, city, state, address, phone, helpline, authorized_organs, notto_registered_id, latitude, longitude, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, notto_centers)

    # 5.11 AppUsers for Role-Based Access Control
    # Public Citizen, Pharmacy Owner, Hospital Staff
    # NOTE: NO admin role or credentials!
    cur.execute("SELECT COUNT(*) FROM app_users;")
    if cur.fetchone()[0] == 0:
        demo_users = [
            ("citizen_chennai", "citizen.chennai@example.com", generate_password_hash("citizen123"), "public", "Selvi Anbarasan (Public Citizen)", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("citizen_delhi", "citizen.delhi@example.com", generate_password_hash("delhi123"), "public", "Rajesh Sharma (Public Citizen)", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("ayapakkam_apollo", "apollo.ayapakkam@example.com", generate_password_hash("apollo123"), "pharmacy_owner", "K. Ramanathan (Apollo Ayapakkam & Mogappair Franchise)", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("ambattur_medplus", "medplus.ambattur@example.com", generate_password_hash("medplus123"), "pharmacy_owner", "P. Venkatesh (MedPlus Ambattur & Navrangpura Franchise)", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("stedeford_staff", "stedeford.hospital@example.com", generate_password_hash("hospital123"), "hospital_staff", "Dr. A. Sudhakar (Stedeford Hospital Medical Admin)", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("gh_ambattur_staff", "gh.ambattur@example.com", generate_password_hash("ghambattur123"), "hospital_staff", "Sister Mary (Ambattur GH Nursing Superintendent)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cur.executemany("""
            INSERT INTO app_users (username, email, password_hash, role, display_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
        """, demo_users)

        # Pharmacy assignments (User 3 -> Pharmacies 1 & 5; User 4 -> Pharmacies 2 & 15)
        assignments_pharm = [
            (3, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            (3, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            (4, 2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            (4, 15, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO user_pharmacy_assignments (user_id, pharmacy_key, assigned_at)
            VALUES (?, ?, ?);
        """, assignments_pharm)

        # Hospital assignments (User 5 -> Hospital 2; User 6 -> Hospital 1)
        assignments_hosp = [
            (5, 2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            (6, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO user_hospital_assignments (user_id, hospital_key, assigned_at)
            VALUES (?, ?, ?);
        """, assignments_hosp)

    # 4. Organization verification requests table for registration auditing
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

    # 5.12 Initial Verified & Stale Pharmacy Updates
    cur.execute("SELECT COUNT(*) FROM pharmacy_inventory_updates;")
    if cur.fetchone()[0] == 0:
        sample_updates = [
            (1, 2, "CONFIRMED_LIVE", 120.00, 180, "K. Ramanathan", "pharmacy-reported", "Fresh cold-chain batch received", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")),
            (1, 19, "CONFIRMED_LIVE", 32.50, 450, "K. Ramanathan", "pharmacy-reported", "Regular shelf stock verified", (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")),
            (2, 5, "CONFIRMED_LIVE", 95.00, 220, "P. Venkatesh", "pharmacy-reported", "Adequate inventory verified", (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")),
            (2, 14, "LOW_STOCK", 260.00, 12, "P. Venkatesh", "pharmacy-reported", "Critical stock: less than 15 vials left", (datetime.now() - timedelta(days=9)).strftime("%Y-%m-%d %H:%M:%S")) # Stale (>7 days)
        ]
        cur.executemany("""
            INSERT INTO pharmacy_inventory_updates
            (pharmacy_key, product_key, status_code, listed_price, stock_units, reporter_name, update_type, notes, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, sample_updates)

    # 5.13 Sample Hospital Service Updates
    cur.execute("SELECT COUNT(*) FROM hospital_service_updates;")
    if cur.fetchone()[0] == 0:
        sample_hosp_updates = [
            (2, "Dr. A. Sudhakar", "+91 44 2658 1234", "https://stedefordhospital.com", "24x7 Emergency, OPD: 08:00 - 18:00", "24x7 Emergency, ICU, Hemodialysis, Trauma Surgery, Blood Bank", "All diagnostic and emergency wings operational", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")),
            (1, "Sister Mary", "+91 44 2658 2400", None, "24 Hours Casualty, OPD: 08:30 - 13:30", "Casualty, Maternity, Pediatric Ward, Free Generic Dispensary", "Updated emergency duty roster active", (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"))
        ]
        cur.executemany("""
            INSERT INTO hospital_service_updates
            (hospital_key, updated_by, phone, website, hours, services, notes, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, sample_hosp_updates)

    # =========================================================================
    # 6. OTP ATTEMPTS TABLE (Brevo SMS/WhatsApp OTP delivery tracking)
    # =========================================================================
    migrate_add_otp_attempts(cur)

    conn.commit()
    conn.close()
    print("Database migration & seed data initialization complete.")


def migrate_add_otp_attempts(cur=None):
    """
    Creates the otp_attempts table for Brevo OTP delivery and verification tracking.
    Safe to call on an existing database — uses CREATE TABLE IF NOT EXISTS.
    Can accept an existing cursor or open its own connection.
    """
    _own_conn = None
    if cur is None:
        import sqlite3
        _own_conn = sqlite3.connect(str(DB_PATH))
        _own_conn.execute("PRAGMA foreign_keys = ON;")
        cur = _own_conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS otp_attempts (
            attempt_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            otp_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            verified INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            channel TEXT DEFAULT 'email',
            message_id TEXT,
            delivery_status TEXT DEFAULT 'pending',
            destination_masked TEXT
        );
    """)

    if _own_conn is not None:
        _own_conn.commit()
        _own_conn.close()
        print("otp_attempts table migration complete.")


def assign_user_role(username: str, role: str, pharmacy_key: int = None, hospital_key: int = None):
    """
    Developer / Admin CLI helper to assign privileged roles to user accounts.
    Supported roles: 'public', 'pharmacy_owner', 'hospital_staff'.
    Enforces that public signup accounts can be assigned institutional roles securely.
    """
    valid_roles = ("public", "pharmacy_owner", "hospital_staff")
    if role not in valid_roles:
        raise ValueError(f"Invalid role '{role}'. Allowed roles are: {', '.join(valid_roles)}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    cur.execute("SELECT user_id, display_name FROM app_users WHERE LOWER(username) = LOWER(?);", (username,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"User '{username}' does not exist in the database.")

    user_id, display_name = row
    cur.execute("UPDATE app_users SET role = ? WHERE user_id = ?;", (role, user_id))

    if role == "pharmacy_owner" and pharmacy_key:
        cur.execute("SELECT name FROM dim_pharmacy WHERE pharmacy_key = ?;", (pharmacy_key,))
        p_row = cur.fetchone()
        if not p_row:
            conn.close()
            raise ValueError(f"Pharmacy key '{pharmacy_key}' not found in dim_pharmacy.")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT OR IGNORE INTO user_pharmacy_assignments (user_id, pharmacy_key, assigned_at)
            VALUES (?, ?, ?);
        """, (user_id, pharmacy_key, now_str))
        print(f"Assigned pharmacy '{p_row[0]}' (Key: {pharmacy_key}) to Pharmacy Owner '{username}'.")

    if role == "hospital_staff" and hospital_key:
        cur.execute("SELECT name FROM dim_hospital WHERE hospital_key = ?;", (hospital_key,))
        h_row = cur.fetchone()
        if not h_row:
            conn.close()
            raise ValueError(f"Hospital key '{hospital_key}' not found in dim_hospital.")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT OR IGNORE INTO user_hospital_assignments (user_id, hospital_key, assigned_at)
            VALUES (?, ?, ?);
        """, (user_id, hospital_key, now_str))
        print(f"Assigned hospital '{h_row[0]}' (Key: {hospital_key}) to Hospital Staff '{username}'.")

    conn.commit()
    conn.close()
    print(f"Successfully updated user '{username}' ({display_name}) to role '{role}'.")


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="PharmaTrack DW Database Migrator & Role Assignment CLI")
    parser.add_argument("--assign-role", nargs=2, metavar=("USERNAME", "ROLE"), help="Assign role to user ('public', 'pharmacy_owner', 'hospital_staff')")
    parser.add_argument("--pharmacy-id", type=int, help="Pharmacy key to associate with Pharmacy Owner")
    parser.add_argument("--hospital-id", type=int, help="Hospital key to associate with Hospital Staff")

    args = parser.parse_args()

    if args.assign_role:
        u_name, r_name = args.assign_role
        assign_user_role(u_name, r_name, pharmacy_key=args.pharmacy_id, hospital_key=args.hospital_id)
    else:
        init_database()

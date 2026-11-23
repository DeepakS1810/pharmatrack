"""
PharmaTrack DW: Medicine Catalog Importer
Developer CLI utility to import legitimate pharmaceutical catalog files (CSV / JSON)
into dim_product in pharmatrack_dw.sqlite.
"""
import sys
import argparse
import sqlite3
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "pharmatrack_dw.sqlite"

def import_catalog(file_path):
    p = Path(file_path)
    if not p.exists():
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)

    print(f"Reading catalog from: {p.name}")
    if p.suffix.lower() == ".csv":
        df = pd.read_csv(p)
    elif p.suffix.lower() in [".json", ".jsonl"]:
        df = pd.read_json(p)
    else:
        print("[ERROR] Unsupported format. Please provide a CSV or JSON file.")
        sys.exit(1)

    # Required fields
    required = ["drug_name", "category", "active_ingredient", "brand_examples", "standard_strength", "dosage_form"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"[ERROR] Missing required columns in catalog file: {missing}")
        print("Required schema: drug_name, category, active_ingredient, brand_examples, standard_strength, dosage_form, [schedule_type]")
        sys.exit(1)

    if "schedule_type" not in df.columns:
        df["schedule_type"] = "Schedule H / Prescription"

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    count = 0
    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO dim_product 
            (drug_name, category, active_ingredient, brand_examples, standard_strength, dosage_form, schedule_type)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            str(row["drug_name"]).strip(),
            str(row["category"]).strip(),
            str(row["active_ingredient"]).strip(),
            str(row["brand_examples"]).strip(),
            str(row["standard_strength"]).strip(),
            str(row["dosage_form"]).strip(),
            str(row.get("schedule_type", "Schedule H / Prescription")).strip()
        ))
        count += 1

    conn.commit()
    conn.close()
    print(f"✓ Successfully imported {count} medicine formulary records into dim_product.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import legitimate medicine catalog into PharmaTrack DW")
    parser.add_argument("file", help="Path to CSV or JSON file containing medicine formulary data")
    args = parser.parse_args()
    import_catalog(args.file)

#!/usr/bin/env python3
"""Add enrichment columns to ConfigurationItem table."""

import sqlite3
from datetime import datetime

DB_PATH = "data/itom.db"

# SQL statements to add new columns
ADD_COLUMNS_SQL = [
    # Organizational enrichment fields
    "ALTER TABLE configuration_items ADD COLUMN company_name VARCHAR(255) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN cost_center VARCHAR(64) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN cost_center_name VARCHAR(255) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN approver_name VARCHAR(128) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN owner VARCHAR(128) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN owner_email VARCHAR(128) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN reporting_manager VARCHAR(128) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN reporting_manager_email VARCHAR(128) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN project VARCHAR(128) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN project_id VARCHAR(64) DEFAULT NULL;",
    
    # Hardware and asset enrichment fields
    "ALTER TABLE configuration_items ADD COLUMN country VARCHAR(64) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN region VARCHAR(64) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN site VARCHAR(255) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN firmware_version VARCHAR(128) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN eol_date TIMESTAMP DEFAULT NULL;",
    
    # AMC and warranty fields
    "ALTER TABLE configuration_items ADD COLUMN amc_status VARCHAR(32) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN amc_provider VARCHAR(128) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN amc_start_date TIMESTAMP DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN amc_end_date TIMESTAMP DEFAULT NULL;",
    
    # Device details
    "ALTER TABLE configuration_items ADD COLUMN device_type VARCHAR(64) DEFAULT NULL;",
    "ALTER TABLE configuration_items ADD COLUMN login_status VARCHAR(32) DEFAULT NULL;",
]

def add_columns():
    """Add enrichment columns to database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print(f"Connecting to database: {DB_PATH}")
        print()
        
        # Get current columns
        cursor.execute("PRAGMA table_info(configuration_items);")
        existing_cols = {row[1] for row in cursor.fetchall()}
        print(f"Existing columns: {len(existing_cols)}")
        print()
        
        # Add only columns that don't exist
        added_count = 0
        skipped_count = 0
        
        for sql in ADD_COLUMNS_SQL:
            col_name = sql.split("ADD COLUMN")[1].split()[0]
            
            if col_name in existing_cols:
                print(f"[SKIP] {col_name}: already exists")
                skipped_count += 1
            else:
                try:
                    cursor.execute(sql)
                    print(f"[ADD] {col_name}: added")
                    added_count += 1
                except sqlite3.OperationalError as e:
                    print(f"[ERR] {col_name}: {e}")
        
        conn.commit()
        conn.close()
        
        print()
        print(f"Summary: {added_count} added, {skipped_count} skipped")
        print("SUCCESS: Database schema updated!")
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    
    return True

if __name__ == "__main__":
    add_columns()


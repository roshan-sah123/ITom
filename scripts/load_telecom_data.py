#!/usr/bin/env python3
"""Load enriched telecom asset data from Excel file into ConfigurationItem table."""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

DB_PATH = "data/itom.db"
TELECOM_FILE = r"c:\Users\Roshan.Sah\Documents\Telcom Inventory_21st Oct 2026.xlsx"

def load_telecom_data():
    """Load Telecom/WAN circuit data."""
    print("Loading Telecom Inventory file...")
    
    try:
        df = pd.read_excel(TELECOM_FILE, sheet_name=0, skiprows=2)
        df = df.dropna(how='all')  # Remove empty rows
        
        print(f"  Loaded {len(df)} rows")
        print(f"  Columns: {list(df.columns[:5])}...")
        
        # Create enrichment data mapping
        # Key: Circuit ID (unique identifier for WAN circuits)
        enrichment_map = {}
        
        for idx, row in df.iterrows():
            circuit_id = str(row.get('Circuit ID') or '').strip()
            if not circuit_id or circuit_id == 'nan':
                continue
            
            # Parse and convert dates to strings immediately
            amc_end_date = row.get('AMC End Date')
            if amc_end_date and pd.notna(amc_end_date):
                try:
                    amc_end_date = str(pd.Timestamp(amc_end_date))
                except Exception:
                    amc_end_date = None
            else:
                amc_end_date = None
            
            end_of_support = row.get('End of Support')
            if end_of_support and pd.notna(end_of_support):
                try:
                    end_of_support = str(pd.Timestamp(end_of_support))
                except Exception:
                    end_of_support = None
            else:
                end_of_support = None
            
            enrichment_map[circuit_id] = {
                'region': str(row.get('Region')) if pd.notna(row.get('Region')) else None,
                'site': str(row.get('Site Location')) if pd.notna(row.get('Site Location')) else None,
                'company_name': str(row.get('Entity')) if pd.notna(row.get('Entity')) else None,
                'device_type': str(row.get('Roles')) if pd.notna(row.get('Roles')) else None,
                'vendor': str(row.get('Provider')) if pd.notna(row.get('Provider')) else None,
                'model': str(row.get('Model')) if pd.notna(row.get('Model')) else None,
                'amc_status': str(row.get('AMC Status')) if pd.notna(row.get('AMC Status')) else None,
                'amc_end_date': amc_end_date,
                'eol_date': end_of_support,
            }
        
        print(f"  Mapped {len(enrichment_map)} circuits")
        return enrichment_map
    
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {}

def enrich_database(telecom_data):
    """Update database with telecom enrichment data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print(f"\nEnriching database with Telecom data...")
    print(f"  Database: {DB_PATH}")
    
    # Count total SPLUNK telecom records
    cursor.execute("""
        SELECT COUNT(*) FROM configuration_items 
        WHERE source_system='SPLUNK' 
        AND ci_type IN ('Telecom', 'PBX', 'VoIP', 'WAN', 'Circuit', 'Router', 'Switch')
    """)
    total_telecom = cursor.fetchone()[0]
    print(f"  Total potential Telecom records: {total_telecom}")
    
    telecom_matched = 0
    
    # Enrich by circuit ID or provider matching
    for circuit_id, data in telecom_data.items():
        # Try exact name match first
        cursor.execute("""
            UPDATE configuration_items 
            SET region = ?, site = ?, company_name = ?, device_type = ?, 
                vendor = ?, model = ?, amc_status = ?, amc_end_date = ?, eol_date = ?
            WHERE source_system='SPLUNK' 
            AND (name LIKE ? OR name LIKE ?)
        """, (
            data.get('region'),
            data.get('site'),
            data.get('company_name'),
            data.get('device_type'),
            data.get('vendor'),
            data.get('model'),
            data.get('amc_status'),
            data.get('amc_end_date'),
            data.get('eol_date'),
            f"%{circuit_id}%",
            f"%WAN%"
        ))
        
        if cursor.rowcount > 0:
            telecom_matched += cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"  Telecom enrichment: {telecom_matched} records updated")
    print("SUCCESS: Telecom data enrichment complete!")
    return telecom_matched

if __name__ == "__main__":
    # Check file exists
    if not Path(TELECOM_FILE).exists():
        print(f"ERROR: Telecom file not found: {TELECOM_FILE}")
        sys.exit(1)
    
    # Load data
    telecom_data = load_telecom_data()
    
    # Enrich database
    if telecom_data:
        enrich_database(telecom_data)
    else:
        print("ERROR: No data loaded from Telecom file")
        sys.exit(1)

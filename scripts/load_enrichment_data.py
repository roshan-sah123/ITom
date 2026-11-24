#!/usr/bin/env python3
"""Load enriched asset data from Excel files into ConfigurationItem table."""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

DB_PATH = "data/itom.db"
ENCORA_FILE = r"C:\Users\Roshan.Sah\Documents\Encora Sites Combined Inventory List.xlsx"
ENTITY_FILE = r"C:\Users\Roshan.Sah\Documents\03Backup_13-11-2026ITOMsDataSheet.xlsx"

def load_encora_data():
    """Load Encora network device data."""
    print("Loading Encora file...")
    
    try:
        df = pd.read_excel(ENCORA_FILE, sheet_name=0)
        print(f"  Loaded {len(df)} rows")
        print(f"  Columns: {list(df.columns[:5])}...")
        
        # Create hostname to enrichment data mapping
        enrichment_map = {}
        
        for idx, row in df.iterrows():
            hostname = row.get('HOST NAME') or row.get('Host Name') or row.get('Hostname')
            if not hostname:
                continue
            
            enrichment_map[str(hostname).strip()] = {
                'country': row.get('Country'),
                'site': row.get('SITE') or row.get('Site'),
                'vendor': row.get('Make') or row.get('PROVIDER'),
                'model': row.get('Model') or row.get('MODEL'),
                'serial_number': row.get('SERIAL NUMBER') or row.get('Serial Number'),
                'firmware_version': row.get('Firmware/IOS Version') or row.get('Firmware/IOS Version'),
                'login_status': row.get('Login Status'),
                'device_type': row.get('TYPE') or row.get('Type'),
                'amc_status': row.get('AMC') or row.get('AMC/Warranty Status'),
                'amc_provider': row.get('AMC PROVIDER NAME'),
                'amc_end_date': row.get('AMC END DATE') or row.get('AMC/Warranty Status'),
                'eol_date': row.get('EOL'),
            }
        
        print(f"  Mapped {len(enrichment_map)} devices")
        return enrichment_map
    
    except Exception as e:
        print(f"  ERROR: {e}")
        return {}

def load_entity_data():
    """Load entity organizational data."""
    print("Loading entity data...")
    
    try:
        df = pd.read_excel(ENTITY_FILE, sheet_name=0)
        print(f"  Loaded {len(df)} entities")
        
        entity_map = {}
        for idx, row in df.iterrows():
            entity = str(row.get('Entity') or row.get('S.N', '')).strip()
            if not entity:
                continue
            
            entity_map[entity] = {
                'company_name': row.get('Company Name'),
                'location': row.get('Location'),
                'cost_center': row.get('CC Code'),
                'domain': row.get('Domain'),
                'cost_center_name': row.get('Cost Center Name'),
                'approver_name': row.get('Approver Name'),
            }
        
        print(f"  Mapped {len(entity_map)} entities")
        return entity_map
    
    except Exception as e:
        print(f"  ERROR: {e}")
        return {}

def enrich_database(encora_data, entity_data):
    """Update database with enrichment data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print(f"\nEnriching database...")
    print(f"  Database: {DB_PATH}")
    
    # Count records with SPLUNK source that could be enriched
    cursor.execute("SELECT COUNT(*) FROM configuration_items WHERE source_system='SPLUNK'")
    total_splunk = cursor.fetchone()[0]
    print(f"  Total SPLUNK records: {total_splunk}")
    
    # Enrich by hostname (Encora data)
    encora_matched = 0
    for hostname, data in encora_data.items():
        cursor.execute("""
            UPDATE configuration_items 
            SET country = ?, site = ?, vendor = ?, model = ?, serial_number = ?,
                firmware_version = ?, login_status = ?, device_type = ?, 
                amc_status = ?, amc_provider = ?, eol_date = ?
            WHERE source_system='SPLUNK' AND LOWER(name) = LOWER(?)
        """, (
            data.get('country'),
            data.get('site'),
            data.get('vendor'),
            data.get('model'),
            data.get('serial_number'),
            data.get('firmware_version'),
            data.get('login_status'),
            data.get('device_type'),
            data.get('amc_status'),
            data.get('amc_provider'),
            data.get('eol_date'),
            hostname
        ))
        if cursor.rowcount > 0:
            encora_matched += cursor.rowcount
    
    print(f"  Encora enrichment: {encora_matched} records updated")
    
    # Enrich by entity (organizational data)
    entity_matched = 0
    for entity_id, data in entity_data.items():
        cursor.execute("""
            UPDATE configuration_items 
            SET company_name = ?, cost_center = ?, cost_center_name = ?, approver_name = ?
            WHERE source_system='SPLUNK' AND attributes->'entity' = ?
        """, (
            data.get('company_name'),
            data.get('cost_center'),
            data.get('cost_center_name'),
            data.get('approver_name'),
            entity_id
        ))
        if cursor.rowcount > 0:
            entity_matched += cursor.rowcount
    
    print(f"  Entity enrichment: {entity_matched} records updated")
    
    conn.commit()
    conn.close()
    
    print(f"\nTotal enriched: {encora_matched + entity_matched} records")
    print("SUCCESS: Database enrichment complete!")

if __name__ == "__main__":
    # Check files exist
    if not Path(ENCORA_FILE).exists():
        print(f"ERROR: Encora file not found: {ENCORA_FILE}")
        sys.exit(1)
    
    if not Path(ENTITY_FILE).exists():
        print(f"ERROR: Entity file not found: {ENTITY_FILE}")
        sys.exit(1)
    
    # Load data
    encora_data = load_encora_data()
    entity_data = load_entity_data()
    
    # Enrich database
    if encora_data or entity_data:
        enrich_database(encora_data, entity_data)
    else:
        print("ERROR: No data loaded from Excel files")
        sys.exit(1)

"""Splunk asset inventory loader - reads Excel files and provides normalized asset records.

This module simulates a Splunk integration by loading asset data from Excel files
and providing it in a normalized format compatible with the sync pipeline.

Files sourced:
- 03Backup_13-11-2026ITOMsDataSheet.xlsx (Servers, Network devices, Telecom assets)
- Encora Sites Combined Inventory List.xlsx (Network and security appliances)
"""

import os
import logging
from typing import Any, Dict, List
from datetime import datetime, timezone

logger = logging.getLogger("itom.splunk_loader")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _normalize_asset_status(status_raw: Any) -> str:
    """Normalize asset operational status."""
    if not status_raw:
        return "Unknown"
    status_str = str(status_raw).strip().lower()
    if status_str in ("on", "active", "up", "running", "enabled", "operational", "yes"):
        return "Up"
    if status_str in ("off", "inactive", "down", "stopped", "disabled", "no"):
        return "Down"
    if status_str in ("maintenance", "degraded", "warning"):
        return "Warning"
    return "Unknown"


def _infer_health_tier(status: str, amc_status: Any = None) -> str:
    """Infer health tier from status and AMC coverage."""
    if status == "Up":
        return "High"
    if status == "Down":
        return "Low"
    if status == "Warning":
        return "Medium"
    return "Medium"


def _normalize_asset_type(device_type_raw: Any, model: Any = None, hostname: Any = None) -> tuple:
    """Infer asset type (ci_type) and category from device info.
    
    Returns (ci_type, category) tuple where category is "Server", "Network", or "Telecom".
    """
    if not device_type_raw:
        device_type_raw = ""
    device_type = str(device_type_raw).lower().strip()
    model_str = str(model or "").lower().strip() if model else ""
    hostname_str = str(hostname or "").lower().strip() if hostname else ""

    # Firewall detection
    if any(x in device_type for x in ["firewall", "fw", "asа"]):
        return ("Firewall", "Network")
    if "asа" in model_str or "palo" in model_str or "fortigate" in model_str or "sophos" in model_str:
        return ("Firewall", "Network")

    # Router detection
    if any(x in device_type for x in ["router", "rtr", "isr", "c1111"]):
        return ("Router", "Network")
    if any(x in model_str for x in ["router", "1921", "2911", "4321", "4331", "4431"]):
        return ("Router", "Network")

    # Switch detection
    if any(x in device_type for x in ["switch", "catalyst", "nexus", "fortis", "3560", "2960", "9300"]):
        return ("Switch", "Network")
    if any(x in model_str for x in ["catalyst", "nexus", "fortis", "c9300", "c2960", "c3560"]):
        return ("Switch", "Network")

    # Load balancer
    if any(x in device_type for x in ["load balancer", "lb", "adc"]):
        return ("Load Balancer", "Network")

    # Wireless controller
    if any(x in device_type for x in ["wireless", "wlc", "ap", "air-ctvm", "c9800"]):
        return ("Wireless Controller", "Network")
    if "c9800" in model_str or "5520" in model_str:
        return ("Wireless Controller", "Network")

    # Telecom/VoIP
    if any(x in device_type for x in ["telecom", "voip", "ucm", "uc"]):
        return ("VoIP Server", "Telecom")
    if "communication" in model_str or "ucm" in hostname_str:
        return ("VoIP Server", "Telecom")

    # Server detection
    if any(x in device_type for x in ["server", "vm", "dc", "app", "db"]):
        return ("Server", "Server")
    if any(x in model_str for x in ["server", "esxi", "hyper-v", "nutanix", "azure"]):
        return ("Server", "Server")

    # Default to Server
    return ("Server", "Server")


def load_servers_from_backup_sheet(filepath: str) -> List[Dict[str, Any]]:
    """Load server assets from the V.2 sheet of the backup spreadsheet."""
    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl not installed; skipping server asset loading")
        return []

    if not os.path.exists(filepath):
        logger.warning(f"Server backup file not found: {filepath}")
        return []

    try:
        wb = openpyxl.load_workbook(filepath)
        # Use V.2 sheet (more recent data)
        ws = wb["V.2"] if "V.2" in wb.sheetnames else wb[wb.sheetnames[0]]
        
        assets = []
        headers = {cell.value: idx for idx, cell in enumerate(ws[1], 0)}
        seen_ids = set()
        
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not any(row):  # Skip empty rows
                continue

            try:
                hostname = (headers.get("HOST NAME") is not None and 
                           row[headers["HOST NAME"]] or None)
                ip_address = (headers.get("IP ADDRESS") is not None and 
                             row[headers["IP ADDRESS"]] or None)
                serial = (headers.get("SERIAL NUMBER") is not None and 
                         row[headers["SERIAL NUMBER"]] or None)
                model = (headers.get("MODEL") is not None and 
                        row[headers["MODEL"]] or None)
                vendor = (headers.get("PROVIDER") is not None and 
                         row[headers["PROVIDER"]] or "Unknown")
                os_raw = (headers.get("OPERATING SYSTEM") is not None and 
                         row[headers["OPERATING SYSTEM"]] or None)
                status_raw = (headers.get("STATUS") is not None and 
                             row[headers["STATUS"]] or "Unknown")
                site = (headers.get("SITE") is not None and 
                       row[headers["SITE"]] or None)
                entity = (headers.get("ENTITY") is not None and 
                         row[headers["ENTITY"]] or None)
                region = (headers.get("REGION") is not None and 
                         row[headers["REGION"]] or None)

                if not hostname:
                    continue

                hostname_str = str(hostname).strip()
                external_id = f"SPLUNK-SERVER-{hostname_str.upper()}"
                
                # Skip duplicates
                if external_id in seen_ids:
                    logger.debug(f"Skipping duplicate hostname: {hostname_str}")
                    continue
                seen_ids.add(external_id)
                
                status = _normalize_asset_status(status_raw)
                ci_type, category = _normalize_asset_type("Server", model, hostname_str)
                health = _infer_health_tier(status)

                asset = {
                    "external_id": external_id,
                    "name": hostname_str,
                    "ci_type": ci_type,
                    "status": status,
                    "health_tier": health,
                    "ip_address": str(ip_address).strip() if ip_address else None,
                    "vendor": str(vendor).strip() if vendor else "Unknown",
                    "model": str(model).strip() if model else None,
                    "serial_number": str(serial).strip() if serial else None,
                    "operating_system": str(os_raw).strip() if os_raw else None,
                    "location": f"{region}/{site}" if region and site else site,
                    "attributes": {
                        "source": "SPLUNK",
                        "asset_category": category,
                        "entity": str(entity).strip() if entity else None,
                        "region": str(region).strip() if region else None,
                        "site": str(site).strip() if site else None,
                        "raw_status": str(status_raw),
                        "loaded_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
                assets.append(asset)
            except Exception as e:
                logger.warning(f"Failed to parse server row {row_idx}: {e}")
                continue

        logger.info(f"Loaded {len(assets)} server assets from backup sheet")
        return assets
    except Exception as e:
        logger.error(f"Error loading servers from backup sheet: {e}")
        return []


def load_network_devices_from_encora_sheet(filepath: str) -> List[Dict[str, Any]]:
    """Load network devices from Encora inventory sheet."""
    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl not installed; skipping network device loading")
        return []

    if not os.path.exists(filepath):
        logger.warning(f"Encora inventory file not found: {filepath}")
        return []

    try:
        wb = openpyxl.load_workbook(filepath)
        ws = wb["Sheet1"] if "Sheet1" in wb.sheetnames else wb[wb.sheetnames[0]]
        
        assets = []
        headers = {cell.value: idx for idx, cell in enumerate(ws[1], 0)}
        seen_ids = set()
        
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not any(row):
                continue

            try:
                hostname = (headers.get("Hostname") is not None and 
                           row[headers["Hostname"]] or None)
                ip_address = (headers.get("Host IP") is not None and 
                             row[headers["Host IP"]] or None)
                serial = (headers.get("Serial Number") is not None and 
                         row[headers["Serial Number"]] or None)
                model = (headers.get("Model") is not None and 
                        row[headers["Model"]] or None)
                vendor = (headers.get("Make") is not None and 
                         row[headers["Make"]] or "Unknown")
                device_type = (headers.get("Device") is not None and 
                              row[headers["Device"]] or None)
                location = (headers.get("Location") is not None and 
                           row[headers["Location"]] or None)
                country = (headers.get("Country") is not None and 
                          row[headers["Country"]] or None)
                amc_status = (headers.get("AMC Status") is not None and 
                             row[headers["AMC Status"]] or None)
                eol_date = (headers.get("EOL Date") is not None and 
                           row[headers["EOL Date"]] or None)
                firmware = (headers.get("Firmware/IOS Version") is not None and 
                           row[headers["Firmware/IOS Version"]] or None)
                login_status = (headers.get("Login Status") is not None and 
                               row[headers["Login Status"]] or None)

                if not hostname or not device_type:
                    continue

                hostname_str = str(hostname).strip()
                external_id = f"SPLUNK-NET-{hostname_str.upper()}"
                
                # Skip duplicates
                if external_id in seen_ids:
                    logger.debug(f"Skipping duplicate network device hostname: {hostname_str}")
                    continue
                seen_ids.add(external_id)
                
                status = _normalize_asset_status(login_status or "Up")
                ci_type, category = _normalize_asset_type(device_type, model, hostname_str)
                health = _infer_health_tier(status, amc_status)

                asset = {
                    "external_id": external_id,
                    "name": hostname_str,
                    "ci_type": ci_type,
                    "status": status,
                    "health_tier": health,
                    "ip_address": str(ip_address).strip() if ip_address else None,
                    "vendor": str(vendor).strip() if vendor else "Unknown",
                    "model": str(model).strip() if model else None,
                    "serial_number": str(serial).strip() if serial else None,
                    "operating_system": str(firmware).strip() if firmware else None,
                    "location": f"{country}/{location}" if country and location else location,
                    "attributes": {
                        "source": "SPLUNK",
                        "asset_category": category,
                        "device_type": str(device_type).strip() if device_type else None,
                        "country": str(country).strip() if country else None,
                        "amc_status": str(amc_status).strip() if amc_status else None,
                        "eol_date": str(eol_date) if eol_date else None,
                        "firmware_version": str(firmware).strip() if firmware else None,
                        "login_status": str(login_status).strip() if login_status else None,
                        "raw_status": str(login_status or "Up"),
                        "loaded_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
                assets.append(asset)
            except Exception as e:
                logger.warning(f"Failed to parse network device row {row_idx}: {e}")
                continue

        logger.info(f"Loaded {len(assets)} network devices from Encora sheet")
        return assets
    except Exception as e:
        logger.error(f"Error loading network devices from Encora sheet: {e}")
        return []


def load_all_splunk_assets() -> List[Dict[str, Any]]:
    """Load asset records from the workbooks configured in SPLUNK_ASSETS_*_FILE."""
    from app.core.config import settings

    assets = []
    if settings.SPLUNK_ASSETS_SERVERS_FILE:
        assets.extend(load_servers_from_backup_sheet(settings.SPLUNK_ASSETS_SERVERS_FILE))
    if settings.SPLUNK_ASSETS_NETWORK_FILE:
        assets.extend(load_network_devices_from_encora_sheet(settings.SPLUNK_ASSETS_NETWORK_FILE))

    logger.info(f"Total assets loaded from Splunk sources: {len(assets)}")
    return assets

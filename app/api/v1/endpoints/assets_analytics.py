"""Assets Analytics REST API endpoints for Servers, Network devices, and Telecom assets."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, or_

from app.core.database import get_db
from app.models.ci import ConfigurationItem

router = APIRouter(prefix="/assets", tags=["Assets Analytics"])


@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_assets_summary(
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve aggregated assets summary across Servers, Network, and Telecom categories."""
    # Query all SPLUNK assets
    stmt = select(
        ConfigurationItem.ci_type,
        ConfigurationItem.status,
        ConfigurationItem.health_tier,
        func.count(ConfigurationItem.id).label("count")
    ).where(
        ConfigurationItem.source_system == "SPLUNK"
    ).group_by(
        ConfigurationItem.ci_type,
        ConfigurationItem.status,
        ConfigurationItem.health_tier
    )
    
    result = await session.execute(stmt)
    rows = result.fetchall()
    
    # Initialize summary structure
    summary = {
        "data_available": len(rows) > 0,
        "total_assets": 0,
        "servers": {"count": 0, "up": 0, "down": 0, "health_breakdown": {"High": 0, "Medium": 0, "Low": 0}},
        "network_devices": {"count": 0, "up": 0, "down": 0, "health_breakdown": {"High": 0, "Medium": 0, "Low": 0}},
        "telecom_assets": {"count": 0, "up": 0, "down": 0, "health_breakdown": {"High": 0, "Medium": 0, "Low": 0}},
        "by_health_tier": {"High": 0, "Medium": 0, "Low": 0},
        "by_status": {"Up": 0, "Down": 0, "Warning": 0, "Unknown": 0},
    }
    
    # Categorize assets based on ci_type
    for ci_type, status_val, health, count in rows:
        # Determine category
        category_key = None
        if ci_type == "Server":
            category_key = "servers"
        elif ci_type in ("Switch", "Router", "Firewall", "Wireless Controller"):
            category_key = "network_devices"
        elif ci_type in ("VoIP Server", "VoIP Gateway"):
            category_key = "telecom_assets"
        
        if category_key:
            summary[category_key]["count"] += count
            summary[category_key]["health_breakdown"][health] = summary[category_key]["health_breakdown"].get(health, 0) + count
            if status_val == "Up":
                summary[category_key]["up"] += count
            elif status_val == "Down":
                summary[category_key]["down"] += count
        
        # Update global stats
        summary["total_assets"] += count
        summary["by_health_tier"][health] = summary["by_health_tier"].get(health, 0) + count
        summary["by_status"][status_val] = summary["by_status"].get(status_val, 0) + count
    
    return summary


@router.get("/servers", status_code=status.HTTP_200_OK)
async def get_servers(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(25, description="Page size"),
    search: Optional[str] = Query(None, description="Search term"),
    vendor: Optional[str] = Query(None, description="Filter by vendor"),
    status: Optional[str] = Query(None, description="Filter by status"),
    health: Optional[str] = Query(None, description="Filter by health tier"),
    sort_by: Optional[str] = Query("name", description="Sort column"),
    sort_order: Optional[str] = Query("asc", description="Sort order"),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get paginated Server assets with filtering and sorting."""
    # Build base query for servers
    stmt = select(ConfigurationItem).where(
        ConfigurationItem.source_system == "SPLUNK",
        ConfigurationItem.ci_type == "Server"
    )
    
    # Apply additional filters
    if search:
        stmt = stmt.where(ConfigurationItem.name.ilike(f"%{search}%"))
    if vendor:
        stmt = stmt.where(ConfigurationItem.vendor.ilike(f"%{vendor}%"))
    if status:
        stmt = stmt.where(ConfigurationItem.status == status)
    if health:
        stmt = stmt.where(ConfigurationItem.health_tier == health)
    
    # Apply sorting
    if sort_order.lower() == "desc":
        stmt = stmt.order_by(getattr(ConfigurationItem, sort_by).desc())
    else:
        stmt = stmt.order_by(getattr(ConfigurationItem, sort_by).asc())
    
    # Apply pagination
    stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    
    result = await session.execute(stmt)
    items = result.scalars().all()
    
    # Get total count
    count_stmt = select(func.count(ConfigurationItem.id)).where(
        ConfigurationItem.source_system == "SPLUNK",
        ConfigurationItem.ci_type == "Server"
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()
    
    return {
        "items": [
            {
                "id": str(item.id),
                "name": item.name,
                "ci_type": item.ci_type,
                "status": item.status,
                "health_tier": item.health_tier,
                "vendor": item.vendor,
                "model": item.model,
                "ip_address": item.ip_address,
                "operating_system": item.operating_system,
                "location": item.location,
                "serial_number": item.serial_number,
                "company_name": item.company_name,
                "cost_center": item.cost_center,
                "cost_center_name": item.cost_center_name,
                "approver_name": item.approver_name,
                "owner": item.owner,
                "owner_email": item.owner_email,
                "reporting_manager": item.reporting_manager,
                "reporting_manager_email": item.reporting_manager_email,
                "project": item.project,
                "project_id": item.project_id,
                "country": item.country,
                "region": item.region,
                "site": item.site,
                "firmware_version": item.firmware_version,
                "eol_date": item.eol_date.isoformat() if item.eol_date else None,
                "amc_status": item.amc_status,
                "amc_provider": item.amc_provider,
                "amc_start_date": item.amc_start_date.isoformat() if item.amc_start_date else None,
                "amc_end_date": item.amc_end_date.isoformat() if item.amc_end_date else None,
                "device_type": item.device_type,
                "login_status": item.login_status,
                "last_sync_time": item.last_sync_time.isoformat() if item.last_sync_time else None,
            }
            for item in items
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }

@router.get("/network-devices", status_code=status.HTTP_200_OK)
async def get_network_devices(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(25, description="Page size"),
    search: Optional[str] = Query(None, description="Search term"),
    device_type: Optional[str] = Query(None, description="Filter by device type (Switch, Router, Firewall, etc.)"),
    vendor: Optional[str] = Query(None, description="Filter by vendor"),
    status: Optional[str] = Query(None, description="Filter by status"),
    health: Optional[str] = Query(None, description="Filter by health tier"),
    sort_by: Optional[str] = Query("name", description="Sort column"),
    sort_order: Optional[str] = Query("asc", description="Sort order"),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get paginated Network Device assets with filtering and sorting."""
    # Build base query for network devices
    stmt = select(ConfigurationItem).where(
        ConfigurationItem.source_system == "SPLUNK",
        or_(
            ConfigurationItem.ci_type == "Switch",
            ConfigurationItem.ci_type == "Router",
            ConfigurationItem.ci_type == "Firewall",
            ConfigurationItem.ci_type == "Wireless Controller"
        )
    )
    
    # Apply additional filters
    if search:
        stmt = stmt.where(ConfigurationItem.name.ilike(f"%{search}%"))
    if device_type:
        stmt = stmt.where(ConfigurationItem.ci_type == device_type)
    if vendor:
        stmt = stmt.where(ConfigurationItem.vendor.ilike(f"%{vendor}%"))
    if status:
        stmt = stmt.where(ConfigurationItem.status == status)
    if health:
        stmt = stmt.where(ConfigurationItem.health_tier == health)
    
    # Apply sorting
    if sort_order.lower() == "desc":
        stmt = stmt.order_by(getattr(ConfigurationItem, sort_by).desc())
    else:
        stmt = stmt.order_by(getattr(ConfigurationItem, sort_by).asc())
    
    # Apply pagination
    stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    
    result = await session.execute(stmt)
    items = result.scalars().all()
    
    # Get total count
    count_stmt = select(func.count(ConfigurationItem.id)).where(
        ConfigurationItem.source_system == "SPLUNK",
        or_(
            ConfigurationItem.ci_type == "Switch",
            ConfigurationItem.ci_type == "Router",
            ConfigurationItem.ci_type == "Firewall",
            ConfigurationItem.ci_type == "Wireless Controller"
        )
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()
    
    return {
        "items": [
            {
                "id": str(item.id),
                "name": item.name,
                "ci_type": item.ci_type,
                "status": item.status,
                "health_tier": item.health_tier,
                "vendor": item.vendor,
                "model": item.model,
                "ip_address": item.ip_address,
                "location": item.location,
                "serial_number": item.serial_number,
                "operating_system": item.operating_system,
                "company_name": item.company_name,
                "cost_center": item.cost_center,
                "cost_center_name": item.cost_center_name,
                "approver_name": item.approver_name,
                "owner": item.owner,
                "owner_email": item.owner_email,
                "reporting_manager": item.reporting_manager,
                "reporting_manager_email": item.reporting_manager_email,
                "project": item.project,
                "project_id": item.project_id,
                "country": item.country,
                "region": item.region,
                "site": item.site,
                "firmware_version": item.firmware_version,
                "eol_date": item.eol_date.isoformat() if item.eol_date else None,
                "amc_status": item.amc_status,
                "amc_provider": item.amc_provider,
                "amc_start_date": item.amc_start_date.isoformat() if item.amc_start_date else None,
                "amc_end_date": item.amc_end_date.isoformat() if item.amc_end_date else None,
                "device_type": item.device_type,
                "login_status": item.login_status,
                "last_sync_time": item.last_sync_time.isoformat() if item.last_sync_time else None,
            }
            for item in items
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }

@router.get("/telecom", status_code=status.HTTP_200_OK)
async def get_telecom_assets(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(25, description="Page size"),
    search: Optional[str] = Query(None, description="Search term"),
    vendor: Optional[str] = Query(None, description="Filter by vendor"),
    status: Optional[str] = Query(None, description="Filter by status"),
    health: Optional[str] = Query(None, description="Filter by health tier"),
    sort_by: Optional[str] = Query("name", description="Sort column"),
    sort_order: Optional[str] = Query("asc", description="Sort order"),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get paginated Telecom assets with filtering and sorting."""
    # Build base query for telecom devices
    stmt = select(ConfigurationItem).where(
        ConfigurationItem.source_system == "SPLUNK",
        or_(
            ConfigurationItem.ci_type == "VoIP Server",
            ConfigurationItem.ci_type == "VoIP Gateway"
        )
    )
    
    # Apply additional filters
    if search:
        stmt = stmt.where(ConfigurationItem.name.ilike(f"%{search}%"))
    if vendor:
        stmt = stmt.where(ConfigurationItem.vendor.ilike(f"%{vendor}%"))
    if status:
        stmt = stmt.where(ConfigurationItem.status == status)
    if health:
        stmt = stmt.where(ConfigurationItem.health_tier == health)
    
    # Apply sorting
    if sort_order.lower() == "desc":
        stmt = stmt.order_by(getattr(ConfigurationItem, sort_by).desc())
    else:
        stmt = stmt.order_by(getattr(ConfigurationItem, sort_by).asc())
    
    # Apply pagination
    stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    
    result = await session.execute(stmt)
    items = result.scalars().all()
    
    # Get total count
    count_stmt = select(func.count(ConfigurationItem.id)).where(
        ConfigurationItem.source_system == "SPLUNK",
        or_(
            ConfigurationItem.ci_type == "VoIP Server",
            ConfigurationItem.ci_type == "VoIP Gateway"
        )
    )
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()
    
    return {
        "items": [
            {
                "id": str(item.id),
                "name": item.name,
                "ci_type": item.ci_type,
                "status": item.status,
                "health_tier": item.health_tier,
                "vendor": item.vendor,
                "model": item.model,
                "ip_address": item.ip_address,
                "location": item.location,
                "last_sync_time": item.last_sync_time.isoformat() if item.last_sync_time else None,
            }
            for item in items
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }

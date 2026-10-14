from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import PropertyNotFoundError, list_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _require_tenant(current_user) -> str:
    # Never fall back to a shared "default_tenant": a user without a resolved
    # tenant must not see any tenant's data.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this user")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(current_user=Depends(get_current_user)) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)
    try:
        properties = await list_properties(tenant_id)
    except Exception as e:
        print(f"Failed to list properties for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=503, detail="Property data temporarily unavailable")
    return {"properties": properties}


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)

    if (month is None) != (year is None):
        raise HTTPException(status_code=400, detail="month and year must be provided together")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
    except PropertyNotFoundError:
        raise HTTPException(status_code=404, detail="Property not found")
    except Exception as e:
        print(f"Revenue lookup failed for {property_id} (tenant {tenant_id}): {e}")
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")

    return {
        "property_id": revenue_data["property_id"],
        # Already rounded to 2dp with Decimal on the server; the string is the
        # exact value, the number is kept for backwards compatibility.
        "total_revenue": float(revenue_data["total"]),
        "total_revenue_str": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "timezone": revenue_data.get("timezone"),
        "period": revenue_data.get("period", "all"),
    }

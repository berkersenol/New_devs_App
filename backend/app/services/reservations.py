from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, List

from sqlalchemy import text

CENT = Decimal("0.01")


class PropertyNotFoundError(Exception):
    """Raised when a property does not exist for the requesting tenant."""


def to_money(value) -> Decimal:
    """
    Convert a DB NUMERIC value to a 2dp money amount.

    Amounts are stored with 3 decimals (sub-cent precision), so we sum the exact
    values first and round ONCE at the end, half-up. Never go through float:
    float(333.333) + ... accumulates binary rounding error ("off by a few cents").
    """
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _month_bounds(month: int, year: int):
    """Local (wall-clock) month boundaries; interpreted in each property's timezone in SQL."""
    start_date = datetime(year, month, 1)
    end_date = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start_date, end_date


async def _get_session():
    from app.core.database_pool import get_db_pool

    pool = await get_db_pool()
    if not pool.session_factory:
        raise RuntimeError("Database pool not available")
    return pool.get_session()


async def list_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """Properties owned by a tenant (used by the dashboard property selector)."""
    async with await _get_session() as session:
        result = await session.execute(
            text("SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY id"),
            {"tenant_id": tenant_id},
        )
        return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in result.fetchall()]


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month, in the PROPERTY's local timezone.

    Previously the month window was naive UTC, so a booking checking in at
    2024-02-29 23:30 UTC (= 2024-03-01 00:30 in Paris) was counted in February.
    """
    summary = await calculate_total_revenue(property_id, tenant_id, month=month, year=year)
    return Decimal(summary["total"])


async def calculate_total_revenue(
    property_id: str, tenant_id: str, month: Optional[int] = None, year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Aggregates revenue from the database for one tenant's property.
    Optionally restricted to a calendar month in the property's local timezone.

    Errors are raised to the caller. (Previously any DB error silently returned
    hardcoded mock figures, which were not even tenant-aware.)
    """
    params: Dict[str, Any] = {"property_id": property_id, "tenant_id": tenant_id}
    period_filter = ""
    if month and year:
        start_date, end_date = _month_bounds(month, year)
        # Convert the timestamptz to the property's local wall-clock time before comparing.
        period_filter = """
            AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
            AND (r.check_in_date AT TIME ZONE p.timezone) <  :end_date
        """
        params.update(start_date=start_date, end_date=end_date)

    async with await _get_session() as session:
        prop = await session.execute(
            text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        prop_row = prop.fetchone()
        if not prop_row:
            raise PropertyNotFoundError(property_id)

        query = text(f"""
            SELECT
                COALESCE(SUM(r.total_amount), 0) AS total_revenue,
                COUNT(r.id)                      AS reservation_count,
                COALESCE(MIN(r.currency), 'USD') AS currency,
                COUNT(DISTINCT r.currency)       AS currency_count
            FROM reservations r
            JOIN properties p
              ON p.id = r.property_id AND p.tenant_id = r.tenant_id
            WHERE r.property_id = :property_id
              AND r.tenant_id = :tenant_id
              {period_filter}
        """)
        row = (await session.execute(query, params)).fetchone()

    if row.currency_count and row.currency_count > 1:
        # Summing different currencies would produce a meaningless number.
        raise ValueError(f"Mixed currencies for property {property_id}; cannot sum")

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(to_money(row.total_revenue)),
        "currency": row.currency,
        "count": row.reservation_count,
        "timezone": prop_row.timezone,
        "period": f"{year}-{month:02d}" if month and year else "all",
    }

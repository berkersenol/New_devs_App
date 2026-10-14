import json
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

CACHE_TTL_SECONDS = 300


def _revenue_cache_key(
    tenant_id: str, property_id: str, month: Optional[int] = None, year: Optional[int] = None
) -> str:
    # The key MUST be tenant-scoped: property IDs are only unique per tenant
    # (e.g. 'prop-001' exists for both tenant-a and tenant-b). Without the tenant
    # in the key, one client's cached revenue was served to another client.
    period = f"{year}-{month:02d}" if month and year else "all"
    return f"revenue:{tenant_id}:{property_id}:{period}"


async def get_revenue_summary(
    property_id: str, tenant_id: str, month: Optional[int] = None, year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for revenue lookups")

    cache_key = _revenue_cache_key(tenant_id, property_id, month, year)

    # Try to get from cache (a Redis outage should not break the dashboard)
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            data = json.loads(cached)
            # Defence in depth: never return a cached payload for another tenant
            if data.get("tenant_id") == tenant_id:
                return data
    except Exception as e:
        print(f"Cache read failed for {cache_key}: {e}")

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id, month=month, year=year)

    try:
        await redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
    except Exception as e:
        print(f"Cache write failed for {cache_key}: {e}")

    return result

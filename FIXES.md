# Revenue Dashboard – Findings & Fixes

## 1. Cross-tenant data leak (Ocean Rentals' privacy issue)
- **Where:** `backend/app/services/cache.py`
- **Root cause:** The Redis key was `revenue:{property_id}`. Property IDs are only unique per tenant: `prop-001` is Sunset's *Beach House Alpha* **and** Ocean's *Mountain Lodge Beta*. Whichever tenant loaded it first had its result cached for 5 minutes and served to the other tenant.
- **Fix:** The key is now `revenue:{tenant_id}:{property_id}:{period}`. As a second check, a cached payload is only returned if its `tenant_id` matches. The endpoint no longer falls back to a shared `"default_tenant"`. It returns 403 if the user has no tenant.
- **Also:** The dashboard hardcoded all 5 properties for every client. A new `GET /api/v1/dashboard/properties` endpoint lists only the caller's properties, and requesting another tenant's property returns 404.

## 2. Dashboard never read the database (wrong totals for everyone)
- **Where:** `backend/app/core/database_pool.py`, `backend/app/services/reservations.py`
- **Root cause:** The pool built its URL from `settings.supabase_db_*`, but those fields don't exist in `config.py`. It used `QueuePool`, which is invalid for async engines, and `get_session()` was an `async def` used with `async with`. Every request raised, and `calculate_total_revenue` caught the error and returned **hardcoded mock numbers**. Those numbers weren't tenant-aware: Ocean saw `prop-001 = 1000.00`. A new engine was also created on every request.
- **Fix:** The pool now uses `DATABASE_URL` (converted to asyncpg) with the default async pool, uses a synchronous `get_session()`, and is a shared singleton initialized once. The mock fallback is removed. DB errors now return a 503 instead of fake numbers.

## 3. March totals wrong for Sunset Properties (timezone)
- **Root cause:** `res-tz-1` checks in at `2024-02-29 23:30 UTC`, which is **2024-03-01 00:30 in Paris**, the property's timezone. Month windows were naive UTC dates, so this booking fell into February.
- **Fix:** Month filtering compares `check_in_date AT TIME ZONE properties.timezone` against local month boundaries. `/dashboard/summary` accepts optional `month` and `year`, and the UI has a period selector.
- **Result:** Beach House Alpha for March 2024 is **2,250.00 (4 bookings)**, up from 1,000.00 (3) under UTC.

## 4. "Off by a few cents" (precision)
- **Root cause:** Amounts are `NUMERIC(10,3)`, which allows sub-cent values like 333.333. They were passed through `float` and re-rounded in JS with `Math.round(x*100)/100`, which drifts because of binary floating point (e.g. 1.005 → 1.00). Rounding each booking before summing would also lose a cent (3 × 333.33 = 999.99 instead of 1000.00).
- **Fix:** Exact `NUMERIC` sums in SQL, then a single `Decimal.quantize(0.01, ROUND_HALF_UP)` on the server. The API returns `total_revenue_str`, the exact value, and the UI displays it without float math. The query also refuses to sum mixed currencies.

## Verification (seed data)
| Tenant | Property | Period | Total | Bookings |
|---|---|---|---|---|
| tenant-a | prop-001 | all / Mar 2024 | 2250.00 | 4 |
| tenant-b | prop-001 | all | 0.00 | 0 (previously leaked 2250.00 / mock 1000.00) |
| tenant-a | prop-002 | Mar 2024 | 4975.50 | 4 |
| tenant-a | prop-003 | Mar 2024 | 6100.50 | 2 |
| tenant-b | prop-004 | Mar 2024 | 1776.50 | 4 |
| tenant-b | prop-005 | Mar 2024 | 3256.00 | 3 |
| tenant-a | prop-004 | – | 404 | – |

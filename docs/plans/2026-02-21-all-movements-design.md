# All Movements by Time Period — Design

## Problem

Currently the app requires searching by product group to view logs. Users need a way to pull ALL logs for a time period and see only cross-ASIN movements, with filtering for bundle-quantity mismatches.

## Solution

A new `/movements/` page that fetches all SoStocked logs for a configurable time period using the `created_at WITHINP` API filter, then shows only detected cross-ASIN movements.

## API Approach

Use SoStocked API with time-period filter instead of ASIN filter:
- `filters[0][c]=created_at`, `filters[0][o]=WITHINP`, `filters[0][v]={days}`
- Paginate through all results (100 per page)
- No ASIN-specific filter — pulls everything

## Backend Flow

1. `GET /movements/?days=60` (default 60 days)
2. Call `_fetch_all_logs(days)` — new function in `sostocked.py`
3. Filter to `type_id=14000` (manual inventory change)
4. Run `_detect_movements()` to find cross-ASIN groups (same timestamp, 2+ ASINs)
5. Keep only rows with a `movement_group`
6. Single WMS query: `Product.objects.filter(asin__in=unique_asins).values('asin', 'bundle_qty')`
7. Calculate `units = param_diff * bundle_qty` and `movement_net_units` per group
8. Render table

## UI

- **Navigation:** "All Movements" button in header (`base.html`)
- **Period selector:** Dropdown with presets: 7, 14, 30, 60, 90 days (default 60)
- **Table columns:** Date, Movement #, ASINs, Diff, Units, Net Units, Balanced, Product, Description
- **Mismatch toggle:** Button to show only movements where `movement_net_units != 0`
- **No chart** — movements span many product groups so chart would be noisy

## Files to Change

| File | Change |
|------|--------|
| `logs/sostocked.py` | Add `_build_params_by_period()`, `_fetch_all_logs()` |
| `logs/views.py` | Add `movements` view |
| `logs/urls.py` | Add `/movements/` route |
| `logs/templates/logs/base.html` | Add nav button |
| `logs/templates/logs/movements.html` | New template |

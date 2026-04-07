# SS Logs Viewer — Bug Fixes, Declutter & Movements View

**Date:** 2026-04-07
**Approach:** Incremental refactor (server-side rendered Django)

---

## 1. Bug Fixes

### 1a. Daily Report Timezone Fix

**File:** `logs/management/commands/send_daily_report.py`

`_to_eet()` assumes stored times are UTC. They are US Pacific (UTC-7). Fix: replace `timezone.utc` with `timezone(timedelta(hours=-7))` when interpreting raw datetime strings. This corrects the 7-hour offset in all emailed CSV timestamps.

### 1b. Date Filter Timezone Fix

**Files:** `logs/views.py`, `logs/templates/logs/explorer.html`

The filter bar accepts browser-local datetime values (e.g. EET, UTC+2) and compares them directly against Pacific-stored strings. The server also generates default dates in UTC (lines 96-98).

Fix:
- **Default dates:** Generate in Pacific (UTC-7) instead of UTC so "last 7 days" aligns with stored timestamps.
- **User-entered dates:** Add JS to the form's submit handler that converts the datetime-local values from browser-local to Pacific (UTC-7) before submission. The server then receives Pacific-aligned values that compare correctly against stored strings.
- This reuses the same `-07:00` offset the frontend already applies for display.

### 1c. Gunicorn Workers

**File:** `gunicorn.conf.py`

Add `workers = 9` (formula: 2 × 4 cores + 1). Currently defaults to 1 worker, underutilizing the 4-core 16GB VPS.

### 1d. Remove Movement Detection from Explorer

**Files:** `logs/views.py`, `logs/templates/logs/explorer.html`

Strip `_apply_movement_detection`, `_apply_movement_balance`, and all movement-related template markup (dots, yellow/red row classes, movement count in meta bar) from the explorer view. Movement logic moves exclusively to the new `/movements` route and daily email report.

---

## 2. Explorer Table Declutter

### 2a. Merge Diff + Units → Single "Units" Column

Display `units` (param_diff × bundle_qty) as the primary value with color coding (+green, -amber, 0 gray). Show raw `param_diff` as a small gray subscript only when `bundle_qty > 1` (otherwise redundant). Remove the separate Diff column.

### 2b. Remove Bundle Column

Drop the "Bundle" column entirely. Bundle qty is implied by the diff/units relationship and visible in the subscript from 2a.

### 2c. Shorter Type Labels

Shorten `TYPE_LABELS` in `logs/sostocked.py`:

| Current | New |
|---------|-----|
| Manual inventory change | Manual inv. |
| System: units arrived | Sys. arrived |
| Amazon: units arrived | AMZ arrived |
| Amazon: units missing | AMZ missing |
| Amazon: units ordered | AMZ ordered |
| Shipped from warehouse | Shipped |
| System shipped | Sys. shipped |
| Shipment canceled | Ship. canceled |
| Removed from shipment | Removed |
| Added to shipment | Added |
| Reduced sent qty | Reduced qty |
| Increased arrived qty | Increased qty |
| Work order combine | WO combine |
| Vendor update revert | Vendor revert |
| Combine product created | Combine created |
| Units arrived changed | Arrived changed |
| Units ordered changed | Ordered changed |
| Shipment → draft | Ship. → draft |
| Reconciliation | Reconciliation |
| Product config | Product cfg |
| Bundle config | Bundle cfg |
| WO/Shipment canceled | WO/Ship. canceled |
| Shipment deleted | Ship. deleted |
| Status changed | Status changed |
| Work order canceled | WO canceled |
| Date sent changed | Date changed |
| Lead time changed | Lead time chg. |
| Destination changed | Dest. changed |
| System: visibility hidden | Sys. hidden |
| Status → arrived | → arrived |

### 2d. Truncate Descriptions

Show first 40 characters with `…` suffix. Full text on hover via `title` attribute.

### Result

13 columns → 11 columns (removed: Bundle, Diff). Less horizontal spread and faster scanning.

---

## 3. Movements View

### Route

`/movements` — new Django view function and template.

### Data

- Queries `SoStockedLog` filtered to `type_id=14000` only
- Same filter bar as explorer: search, date range, Apply, CSV, Reset (no type dropdown — always 14000)
- Default date range: last 7 days
- Runs movement detection on the **full filtered queryset** (not page-scoped):
  - Groups type 14000 entries by exact `created_at` timestamp
  - If 2+ ASINs share a timestamp → movement group
  - Calculates unit balance: sum of `param_diff × bundle_qty` across group
  - Balanced = sum is 0, Mismatched = sum ≠ 0
- Paginates at 100 rows/page with movement flags pre-calculated

### Display

Table-based layout consistent with explorer. Columns:

1. Date
2. ASIN
3. Units (same merged format as decluttered explorer)
4. Qty Change (old → new)
5. Product
6. Warehouse
7. User
8. Description (truncated, title hover)

Movement groups visually connected:
- Colored left border bar (4px) spanning grouped rows
- Balanced groups: green-tinted background (`#f0fdf4`), green border (`#16a34a`)
- Mismatched groups: red-tinted background (`#fef2f2`), red border (`#ef4444`), net units displayed
- Single (unpaired) manual changes: normal row styling, no border bar

### Navigation

Add nav links in `base.html` header: **Logs** | **Movements**. Active state indicator on the current page.

### Filter Bar Meta

Shows: row count, movement group count, mismatch count.

---

## Files Changed

| File | Changes |
|------|---------|
| `gunicorn.conf.py` | Add `workers = 9` |
| `logs/sostocked.py` | Shorten `TYPE_LABELS` |
| `logs/views.py` | Remove movement detection from explorer, add timezone offset to date filters, add `movements` view function |
| `logs/urls.py` | Add `/movements` route |
| `logs/templates/logs/base.html` | Add Logs/Movements nav links |
| `logs/templates/logs/explorer.html` | Remove movement markup, merge Diff+Units, drop Bundle column, truncate descriptions |
| `logs/templates/logs/movements.html` | New template for movements view |
| `logs/management/commands/send_daily_report.py` | Fix `_to_eet()` timezone assumption |

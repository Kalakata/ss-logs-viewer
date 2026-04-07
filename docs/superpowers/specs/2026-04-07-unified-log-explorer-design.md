# Unified Log Explorer — Design Spec

## Goal

Replace the three separate pages (index/search, group logs, movements) with a single log explorer page at `/`. All SoStocked logs from the local SQLite database are browsable through a filter bar and paginated table.

## Architecture

One Django view serves `/` with query-param-driven filters. The view builds a queryset against `SoStockedLog`, applies filters, paginates, runs movement detection on the current page's results, and renders a single template.

## Filter Bar

Sticky bar below the header with these controls:

- **Search** — text input, filters across ASIN, product name, user name, and description using `Q` objects with `__icontains`. Debounce not needed since this is server-side (form submit / URL nav).
- **Date range** — two `<input type="date">` fields (from/to). Defaults to last 7 days. Filters on `created_at__gte` / `created_at__lte`.
- **Type** — `<select>` dropdown populated from `TYPE_LABELS`. Options: "All types", each type label, plus "Movements only" (filters `type_id=14000`).
- **Mismatches only** — checkbox/toggle. When active, adds filter for rows where `real_diff` differs from `param_diff` using a raw annotation or by filtering in Python after query (since SQLite supports `F()` expressions: `.exclude(real_diff=F('param_diff'))`).

All filter values are passed as GET query params: `?q=...&from=2026-04-01&to=2026-04-07&type=14000&mismatch=1&page=2`. This makes URLs shareable and bookmarkable.

## Table

Columns:
| Column | Source | Notes |
|--------|--------|-------|
| Date | `created_at` | Nowrap |
| ASIN | `asin` | Styled tag |
| Type | `type_id` → `TYPE_LABELS` | Styled tag |
| Diff | `param_diff` + `real_diff` | Green/amber/gray coloring. Grayed `real_diff` shown when it differs from `param_diff` |
| Qty | `old_qty` → `new_qty` | Arrow format |
| Product | `product_name` | Truncated |
| Warehouse | `vendor_name` | Purple text |
| User | `user_name` | Nowrap |
| Description | `description` | Word-break |

Row styling:
- Movement rows (detected cross-ASIN movements) get yellow background
- Mismatched movements get red background
- Movement dot indicator in a leading column

## Pagination

- 100 rows per page
- Django's `Paginator` class
- Bottom bar shows: "Page X of Y (Z total)" with prev/next links
- Page number passed as `?page=N` query param, preserved alongside filters

## Movement Detection

Same logic as current `_apply_movement_detection` and `_apply_movement_balance`:
- Groups manual inventory changes (type 14000) at the same timestamp across 2+ ASINs
- Calculates balance (units sum to 0 = balanced)
- Applied to the current page's queryset results only

Bundle qty lookup: query `Product` model from the WMS database for ASINs present in the current page.

## Removed

- `/api/search-groups/` endpoint
- `/group/<id>/logs/` page
- `/movements/` page
- `search_groups` view
- `group_logs` view  
- `movements` view
- `logs/templates/logs/index.html`
- `logs/templates/logs/group_logs.html`
- `logs/templates/logs/movements.html`
- Chart.js and related chart code
- Stock balance columns
- All JS (chart, zoom, filter toggles) — replaced by server-side filtering

## Kept

- `/cron/send-report/` endpoint (`trigger_report` view) — unchanged
- `logs/templates/logs/base.html` — kept as layout base
- Movement detection helpers (`_apply_movement_detection`, `_apply_movement_balance`)
- `real_diff` indicator styling

## Files Changed

| Action | File |
|--------|------|
| Create | `logs/templates/logs/explorer.html` |
| Rewrite | `logs/views.py` — single `explorer` view replaces index/group_logs/movements/search_groups |
| Modify | `logs/urls.py` — remove old routes, single `/` route |
| Keep | `logs/templates/logs/base.html` |
| Delete | `logs/templates/logs/index.html` |
| Delete | `logs/templates/logs/group_logs.html` |
| Delete | `logs/templates/logs/movements.html` |

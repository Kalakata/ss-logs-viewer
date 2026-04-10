# SoStocked API — Reverse-Engineered Endpoint Reference

**Date:** 2026-04-10
**Base URL:** `https://api.sostocked.com`
**Auth:** `Authorization: Bearer <token>` header + query params `client_id`, `client_secret`, `account_id`

Extracted from the app bundle (`index.BRhHoEvn.js`, 3MB) at `app.sostocked.com` plus network traffic capture.

---

## Authentication

```
POST /oauth/token
```

All other endpoints require:
- Header: `Authorization: Bearer <token>`
- Query/body params: `client_id`, `client_secret`, `account_id`

---

## ACCOUNTS

```
GET  /accounts/show/
GET  /accounts/audit/status
POST /accounts/update-currency
```

## AMAZON STORES

```
GET  /amazon-stores/read
GET  /amazon-stores/show/:id
POST /amazon-stores/destroy/:id
```

## BACKUPS

```
GET  /backups
GET  /backups/restoring
```

## BRANDS

```
GET  /brands/read
GET  /brands/show/:id
POST /brands/do-action
```

## BULK EXPORT / IMPORT

```
GET  /bulk-export-import/read
POST /bulk-export/create
```

## CONSTANTS (Reference Data)

Enum/lookup endpoints — all GET, no auth params needed beyond the token.

```
GET /constants/all-constants
GET /constants/account-user/types
GET /constants/account/beta_features
GET /constants/account/order-frequencies
GET /constants/account/auto-hide-cards
GET /constants/admin-notifications/types
GET /constants/brands/statuses
GET /constants/customer-orders/statuses
GET /constants/export/options
GET /constants/fba-buffer/options
GET /constants/fba-order-shipment/internal-statuses
GET /constants/fba-order-shipment/statuses
GET /constants/fba-order-shipment/sub-statuses
GET /constants/marketplace/countries
GET /constants/marketplace/countries-amazon-shopify
GET /constants/marketplace/country-addresses
GET /constants/marketplace/country-codes
GET /constants/marketplace/vendor-fields-relations
GET /constants/note/groups
GET /constants/notification-setting/days
GET /constants/notification-setting/days-in-month
GET /constants/notification-setting/frequency
GET /constants/order-attachment/file-types
GET /constants/order-shipment/delay-options
GET /constants/order-shipment/reconcile/statuses
GET /constants/order-shipment/statuses
GET /constants/order-shipment/statuses-with-icons
GET /constants/order-shipment/types
GET /constants/order-tracker/columns-with-statuses
GET /constants/order/send-order-actions
GET /constants/order/statuses
GET /constants/order/types
GET /constants/product-calculation-spike/save-options
GET /constants/product-calculation/days-in-month
GET /constants/product-calculation/days-in-week
GET /constants/product-calculation/order-frequency
GET /constants/product-calculation/order-within
GET /constants/product-calculation/save-options
GET /constants/product-calculation/trend-compare-periods
GET /constants/product-calculation/trend-ranges
GET /constants/product-calculation/velocity-preset-views
GET /constants/product/statuses
GET /constants/reconcile-shipment/remaining-units
GET /constants/reconcile-shipment/source
GET /constants/seasonality-record/types
GET /constants/stripe/subscription-statuses
GET /constants/user/statuses
GET /constants/vendor-payment-terms/statuses
GET /constants/vendor-type/kinds
GET /constants/vendors/statuses
GET /constants/work-order-shipment/statuses
GET /constants/work-order/actions
GET /constants/work-order/statuses
GET /constants/workflow-status/statuses
GET /constants/workflow-status/statuses-with-icons
GET /constants/workflow/types
```

## COUNTRIES

```
GET /countries/read
```

## CUSTOMER ORDERS

```
GET  /customer-orders/read
GET  /customer-orders/download
POST /customer-orders/do-action
```

## DOWNLOADS

```
GET  /downloads/download/:id
POST /downloads/create/:id
```

## EXCHANGE RATES

```
GET /exchange-rates/read
```

## FBA ORDERS

```
POST /fba-orders/read
POST /fba-orders/download
POST /fba-orders/do-action
```

## FBA SHIPMENTS

```
GET /fba-shipments/show/:id
```

## FILE UPLOADS

```
POST /file/upload
POST /file/upload-files
```

## GROUP AREAS (Markets/Regions)

```
GET /group-areas/read
GET /group-areas/read-marketplaces
```

## INVENTORIES

```
GET  /inventories/actions-progress
POST /inventories/export-snapshot
```

## NOTES

```
POST /notes/read
POST /notes/destroy/:id
```

## NOTIFICATION SETTINGS

```
GET /notification-settings/read
```

## ORDER SHIPMENTS

```
POST /order-shipment/updateLeadTime
```

## ORDER SHIPMENT LOGS (what our app currently uses)

```
GET /order-shipment-logs/logs
```

Query params: `page`, `per_page`, `order_by`, `order_direction`, `term`, `group_by`, `apply_custom_params`, `columns[N][id]`, `columns[N][show]`, `columns[N][text]`, `filters[N][x]`, `filters[N][c]`, `filters[N][o]`, `filters[N][v]`

Filter operators: `EQUAL`, `WITHINP` (within N days), `NOT IN`, `!=`, `=`

## ORDER TRACKER

```
GET /order-tracker/group-by-status
GET /order-tracker/group-by-calculation
GET /order-tracker/orders-by-status
GET /order-tracker/group-by-status-card/card-info/:orderId?columnId=<status>
GET /order-tracker/group-by-status-card-products/:orderId?page=1&per_page=3
GET /order-tracker-actions/actions-progress
```

## ORDERS

```
POST /orders/read
POST /orders/export
POST /orders/do-action
```

The `/orders/export` endpoint is documented in the official API docs. Uses same column/filter structure.

## PAGE VIEWS

```
POST /page-views-daily-statistics/increment-number-of-views
```

## PRODUCT CALCULATIONS (Forecasts)

```
GET /product-calculations/read
GET /product-calculations/download
GET /product-calculation/weekly-schedules/:id
```

## PRODUCT INVENTORIES

```
POST /product-inventories/read
POST /product-inventories/export                        (documented)
POST /product-inventories/warehouses-breakdown-export   (documented)
```

## PRODUCTS

```
POST /products/do-action
```

## PROFITABILITY

```
GET  /profit-killers/profit/status
POST /profit-killers/profit
POST /profit-killers/profit/percentage
POST /profit-killers/overstock-strategy
POST /profit-killers/overstock-strategy/percentage
```

## TAGS

```
GET  /tags/show/:id
POST /tags/do-action
POST /tags/destroy/:id
```

## TEAM

```
GET /team/read
GET /team/invite/read
```

## VENDOR INVENTORY LOG

```
GET /vendor-inventory-log/read
```

## VENDORS

```
GET  /vendors/read
GET  /vendors/show/:id
GET  /vendors/used-colors
POST /vendors/do-action
POST /vendors/destroy/:id
```

## WORKFLOWS

```
GET  /workflows/read
GET  /workflows/read-available-workflows
POST /workflows/do-action
POST /workflows/destroy/:id
```

---

## Common Request Patterns

### List/Read endpoints
Most `read` endpoints accept:
- `page`, `per_page` — pagination
- `order_by`, `order_direction` — sorting (ASC/DESC)
- `term` — search term
- `group_by` — grouping
- `apply_custom_params: 1` — enable column/filter system
- `columns[N][id]`, `columns[N][show]`, `columns[N][text]` — column definitions
- `filters[N][x]`, `filters[N][c]`, `filters[N][o]`, `filters[N][v]` — filter conditions
- `page_view_id` — saved view ID

### Filter operators
- `=` / `EQUAL` — exact match
- `!=` — not equal
- `NOT IN` — exclusion list
- `WITHINP` — within past N days
- `WITHINF` — within future N days

### do-action endpoints
Batch action endpoints (`/products/do-action`, `/vendors/do-action`, etc.) accept action type + item IDs for bulk operations.

### Export endpoints
Export endpoints typically accept the same column/filter structure as read endpoints, plus:
- `download_option: "current_view"` — export current filtered view
- `export_type: "expanded" | "collapsed" | "snapshot" | "warehouse-breakdown"`

---

## Frontend Routes (app.sostocked.com)

These are the SPA routes (not API endpoints):

```
/me/order-tracker          — Order Tracker (kanban board)
/me/product-calculations   — Forecasts
/me/inventory              — Inventory
/me/profitability/profit   — Profitability
/me/vendors                — Vendors
/me/settings               — Settings
/me/logs                   — Order Shipment Logs
/me/import-export          — Bulk Import/Export
```

---

## Endpoints NOT in Official Docs

The official docs only cover 4 export endpoints. The following are undocumented:

**High value for data extraction:**
- `GET /order-shipment-logs/logs` — what we currently use for log viewer
- `GET /vendor-inventory-log/read` — vendor-level inventory change log
- `POST /fba-orders/read` — FBA order data
- `GET /product-calculations/read` — forecast data
- `POST /profit-killers/profit` — profitability data
- `GET /order-tracker/group-by-status` — order pipeline status

**Useful for reference data:**
- `GET /constants/all-constants` — all enums in one call
- `GET /group-areas/read` — marketplace/region definitions
- `GET /vendors/read` — vendor list with details
- `GET /brands/read` — brand list
- `GET /exchange-rates/read` — currency exchange rates
- `GET /customer-orders/read` — customer order data

**Total: 122 API endpoints discovered across 35 resource groups**

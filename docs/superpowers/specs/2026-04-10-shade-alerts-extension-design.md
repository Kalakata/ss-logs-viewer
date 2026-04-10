# Shade Alerts in Browser Extension — Design Spec

**Date:** 2026-04-10
**Context:** The SoStocked Inventory Guard Chrome extension already prevents overshipping on work order edit pages. This extends it with real-time phantom quantity (shade) alerts and a guard override mechanism.

## 1. Backend API Endpoint

New endpoint on the ss-logs-viewer Django app:

```
GET /api/phantom-logs/?since=<ISO-timestamp>&token=<static-token>
```

**Query params:**
- `since` — ISO 8601 timestamp (e.g. `2026-04-10T08:00:00Z`). Returns shade logs with `created_at` after this time. If omitted, defaults to last 72 hours.
- `token` — static secret token for simple auth (stored in `.env` as `EXTENSION_API_TOKEN`).

**Response:** JSON array of shade log objects:
```json
[
  {
    "id": 12345,
    "asin": "B0FLFHMZ86",
    "shipment_id": "9438276",
    "shade": -24,
    "param_diff": -48,
    "real_diff": -24,
    "warehouse": "WH2 INDUSTRIALNA",
    "user": "Maya Trifonova",
    "created_at": "2026-01-28 03:50:06",
    "description": "Maya Trifonova shipped shipment 9438276..."
  }
]
```

**Implementation:** In `logs/views.py`, a new `phantom_api` view. Queries `SoStockedLog.objects.filter(created_at__gte=since).exclude(param_diff=F('real_diff'))`, returns JSON. New route in `logs/urls.py` at `api/phantom-logs/`.

**Auth:** Compare `token` query param against `settings.EXTENSION_API_TOKEN` env var. Return 403 if missing/wrong.

## 2. Extension Polling

The content script (`guard.js`) polls the backend every 60 seconds.

**State management:**
- `chrome.storage.local` stores:
  - `lastSeenTimestamp` — ISO timestamp of the newest log the user has been notified about
  - `unseenCount` — number of unseen phantom logs (drives badge)

**Flow:**
1. On each poll, fetch `/api/phantom-logs/?since=<lastSeenTimestamp>&token=<token>`
2. If new logs returned:
   - Show a toast for each new log
   - Update `lastSeenTimestamp` to the newest log's `created_at`
   - Increment `unseenCount`, update badge
3. If fetch fails (network error, 403), silently skip — retry next cycle

**Configuration:** The backend URL and token are stored in the extension's `chrome.storage.local`, configurable from the popup. Defaults to the production VPS URL.

## 3. Toast Notifications

In-page toast, bottom-right corner, inside a fixed-position container outside the Vue tree (same pattern as the guard overlay).

**Content per toast:**
```
⚠ Phantom quantity detected
B0FLFHMZ86 | #9438276 | shade: -24
WH2 INDUSTRIALNA — Maya Trifonova
2 мин. назад
```

**Behavior:**
- Auto-dismiss after 10 seconds
- Stacks vertically if multiple (newest on top, max 5 visible)
- Clicking a toast dismisses it
- Language: Bulgarian

## 4. History Popup

Clicking the extension icon opens `popup.html` — a small panel (400x500px) showing the last 72 hours of phantom logs.

**Content:**
- Header: "Phantom Alerts" with unseen count
- List of log entries, each showing: ASIN, shipment ID, shade, warehouse, user, relative time
- "Маркирай всички като прочетени" (Mark all read) button — clears badge and resets `unseenCount`
- Settings section at bottom: backend URL + token fields (persisted to `chrome.storage.local`)

**Data:** Fetches `/api/phantom-logs/?since=<72h-ago>&token=<token>` on popup open.

## 5. Guard Override

When the user clicks Save & Preview with active inventory violations:

1. Click is intercepted (existing behavior)
2. Warning banner shows with the violation message **plus** a "Продължи въпреки това" (Proceed anyway) button
3. Clicking "Proceed anyway" sets a temporary flag (`guardOverride = true`)
4. The next Save & Preview click within 10 seconds passes through (interceptor checks the flag and lets it go)
5. Flag auto-resets after 10 seconds or after one successful pass-through

## 6. Extension Manifest Changes

```json
{
  "permissions": ["storage"],
  "action": {
    "default_popup": "popup.html",
    "default_icon": { "48": "icon48.png", "128": "icon128.png" }
  },
  "content_scripts": [
    {
      "matches": ["https://app.sostocked.com/*"],
      "js": ["guard.js"],
      "css": ["guard.css"],
      "run_at": "document_idle"
    }
  ]
}
```

`storage` permission needed for `chrome.storage.local`. No host permissions needed beyond the content script match — fetch to the VPS is a regular CORS request (backend must set `Access-Control-Allow-Origin: *` header).

## 7. Files Modified/Created

**Backend (ss-logs-viewer):**
- `logs/views.py` — new `phantom_api` view function
- `logs/urls.py` — new route `api/phantom-logs/`
- `ss_logs_viewer/settings.py` — new `EXTENSION_API_TOKEN` env var

**Extension (ss-guard-extension):**
- `manifest.json` — add `storage` permission, `action` with popup
- `guard.js` — add polling, toasts, override button logic
- `guard.css` — add toast and override button styles
- `popup.html` — new file, history panel
- `popup.js` — new file, popup logic

## 8. CORS

The `phantom_api` view must return `Access-Control-Allow-Origin: *` header since the extension's content script runs in the context of `app.sostocked.com`, and the fetch goes to the VPS domain. A simple middleware or decorator on the single endpoint.

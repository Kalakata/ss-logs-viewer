# Shade Alerts Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time phantom quantity alerts to the SoStocked Inventory Guard extension, with a history popup and a guard override button.

**Architecture:** New Django API endpoint serves phantom logs as JSON. Extension content script polls every 60s, shows in-page toasts for new detections. Extension popup shows 72h history. Guard override adds a "Proceed anyway" button to the warning banner.

**Tech Stack:** Django views (JSON endpoint), Chrome Extension Manifest V3, chrome.storage.local, vanilla JS/CSS

**Spec:** `docs/superpowers/specs/2026-04-10-shade-alerts-extension-design.md`

---

### Task 1: Add EXTENSION_API_TOKEN setting

**Files:**
- Modify: `ss_logs_viewer/settings.py:107`

- [ ] **Step 1: Add the setting**

In `ss_logs_viewer/settings.py`, after the `CRON_SECRET` line (line 107), add:

```python
EXTENSION_API_TOKEN = os.environ.get('EXTENSION_API_TOKEN', '')
```

- [ ] **Step 2: Add to docker-compose.yml**

In `docker-compose.yml`, add `EXTENSION_API_TOKEN` to the `app` service environment section (same pattern as `CRON_SECRET`):

```yaml
      EXTENSION_API_TOKEN: ${EXTENSION_API_TOKEN:-}
```

- [ ] **Step 3: Commit**

```bash
git add ss_logs_viewer/settings.py docker-compose.yml
git commit -m "Add EXTENSION_API_TOKEN setting for phantom logs API"
```

---

### Task 2: Create phantom logs API endpoint

**Files:**
- Modify: `logs/views.py` (add new view)
- Modify: `logs/urls.py` (add route)

- [ ] **Step 1: Add the phantom_api view**

In `logs/views.py`, add this import at the top (line 10, after the existing `HttpResponse` import):

```python
from django.http import HttpResponse, JsonResponse
```

Then add the new view at the end of the file (after the `debug_types` view):

```python
@require_GET
def phantom_api(request):
    """JSON API for the browser extension — returns phantom logs (shade != 0)."""
    token = request.GET.get('token', '')
    if not settings.EXTENSION_API_TOKEN or token != settings.EXTENSION_API_TOKEN:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    since = request.GET.get('since', '')
    if not since:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        since = cutoff.strftime('%Y-%m-%d %H:%M:%S')
    else:
        since = since.replace('T', ' ').replace('Z', '')

    qs = SoStockedLog.objects.filter(
        created_at__gte=since,
    ).exclude(
        param_diff=F('real_diff'),
    ).order_by('-created_at')[:200]

    logs = []
    for row in qs:
        logs.append({
            'id': row.ss_id,
            'asin': row.asin,
            'shipment_id': row.order_shipment_id,
            'shade': (row.param_diff or 0) - (row.real_diff or 0),
            'param_diff': row.param_diff,
            'real_diff': row.real_diff,
            'warehouse': row.vendor_name,
            'user': row.user_name,
            'created_at': row.created_at,
            'description': row.description,
        })

    response = JsonResponse(logs, safe=False)
    response['Access-Control-Allow-Origin'] = '*'
    return response
```

- [ ] **Step 2: Add the import for settings**

In `logs/views.py`, add at the top (after the existing imports, around line 15):

```python
from django.conf import settings
```

- [ ] **Step 3: Add the URL route**

In `logs/urls.py`, add the new route:

```python
from django.urls import path
from . import views

urlpatterns = [
    path('', views.explorer, name='explorer'),
    path('movements/', views.movements, name='movements'),
    path('api/phantom-logs/', views.phantom_api, name='phantom_api'),
    path('cron/send-report/', views.trigger_report, name='trigger_report'),
    path('debug/types/', views.debug_types, name='debug_types'),
]
```

- [ ] **Step 4: Commit**

```bash
git add logs/views.py logs/urls.py
git commit -m "Add phantom logs JSON API endpoint for browser extension"
```

---

### Task 3: Update extension manifest

**Files:**
- Modify: `ss-guard-extension/manifest.json`

- [ ] **Step 1: Update manifest**

Replace the full content of `ss-guard-extension/manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "SoStocked Inventory Guard",
  "version": "2.0",
  "description": "Inventory guard + phantom quantity alerts for SoStocked",
  "permissions": ["storage"],
  "action": {
    "default_popup": "popup.html",
    "default_icon": {
      "48": "icon48.png",
      "128": "icon128.png"
    }
  },
  "content_scripts": [
    {
      "matches": ["https://app.sostocked.com/*"],
      "js": ["guard.js"],
      "css": ["guard.css"],
      "run_at": "document_idle"
    }
  ],
  "icons": {
    "48": "icon48.png",
    "128": "icon128.png"
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add ss-guard-extension/manifest.json
git commit -m "Update extension manifest with storage permission and popup"
```

---

### Task 4: Add guard override button

**Files:**
- Modify: `ss-guard-extension/guard.js:92-110` (save button intercept and overlay)
- Modify: `ss-guard-extension/guard.css` (override button styles)

- [ ] **Step 1: Add override CSS**

In `ss-guard-extension/guard.css`, append at the end:

```css
/* Override button in warning banner */
.ss-guard-override-btn {
  background: transparent;
  border: 1px solid #991b1b;
  color: #991b1b;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  margin-left: 12px;
  white-space: nowrap;
}

.ss-guard-override-btn:hover {
  background: #991b1b;
  color: #fff;
}
```

- [ ] **Step 2: Update guard.js with override logic**

Replace the entire content of `ss-guard-extension/guard.js`:

```javascript
/**
 * SoStocked Inventory Guard v2
 *
 * - Monitors work order edit pages, blocks overshipping
 * - Override button lets users proceed intentionally
 * - Polls backend for phantom quantity (shade) alerts
 * - Shows in-page toasts for new detections
 */

(function ssGuard() {
  'use strict';

  const GUARD_POLL_MS = 400;
  const SHADE_POLL_MS = 60000;
  const TOAST_DURATION_MS = 10000;
  const MAX_TOASTS = 5;

  // --- Guard state ---
  let currentViolations = [];
  let guardOverride = false;
  let overlay = null;

  function getOverlay() {
    if (overlay && document.body.contains(overlay)) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'ss-guard-overlay';
    overlay.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);z-index:99999;pointer-events:none;';
    document.body.appendChild(overlay);
    return overlay;
  }

  function showOverlay(count) {
    var ov = getOverlay();
    ov.textContent = '';
    var box = document.createElement('div');
    box.style.cssText = 'background:#fef2f2;border:2px solid #ef4444;border-radius:8px;padding:10px 20px;' +
      'font-size:14px;color:#991b1b;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.15);pointer-events:auto;' +
      'display:flex;align-items:center;gap:8px;';
    var icon = document.createElement('span');
    icon.style.fontSize = '20px';
    icon.textContent = '\u26A0';
    box.appendChild(icon);
    var msg = document.createElement('span');
    msg.textContent = count + (count === 1 ? ' \u043F\u0440\u043E\u0434\u0443\u043A\u0442' : ' \u043F\u0440\u043E\u0434\u0443\u043A\u0442\u0430') +
      ' \u0441 \u043F\u043E\u0432\u0435\u0447\u0435 \u0435\u0434\u0438\u043D\u0438\u0446\u0438 \u043E\u0442 \u043D\u0430\u043B\u0438\u0447\u043D\u0438\u0442\u0435. \u041A\u043E\u0440\u0438\u0433\u0438\u0440\u0430\u0439\u0442\u0435 \u043F\u0440\u0435\u0434\u0438 \u0437\u0430\u043F\u0438\u0441.';
    box.appendChild(msg);
    var overrideBtn = document.createElement('button');
    overrideBtn.className = 'ss-guard-override-btn';
    overrideBtn.textContent = '\u041F\u0440\u043E\u0434\u044A\u043B\u0436\u0438 \u0432\u044A\u043F\u0440\u0435\u043A\u0438 \u0442\u043E\u0432\u0430';
    overrideBtn.addEventListener('click', function() {
      guardOverride = true;
      hideOverlay();
      setTimeout(function() { guardOverride = false; }, 10000);
    });
    box.appendChild(overrideBtn);
    ov.appendChild(box);
  }

  function hideOverlay() {
    if (overlay && document.body.contains(overlay)) {
      overlay.textContent = '';
    }
  }

  function getSaveButton() {
    var buttons = document.querySelectorAll('button.btn.btn-success.btn-lg');
    for (var i = 0; i < buttons.length; i++) {
      if (buttons[i].textContent.trim().includes('Save')) return buttons[i];
    }
    return null;
  }

  function guardCheck() {
    if (!location.pathname.includes('/orders/') || !location.pathname.includes('/edit/')) {
      hideOverlay();
      return;
    }

    var rows = document.querySelectorAll('.shipmen-logistics-table__row');
    if (!rows.length) return;

    var violations = [];

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var invCell = row.querySelector('.shipmen-logistics-table__cell.width-120');
      if (!invCell) continue;
      var invSpan = invCell.querySelector('span.d-block');
      if (!invSpan) continue;
      var m = invSpan.textContent.match(/INV:\s*(\d+)/);
      if (!m) continue;
      var inv = parseInt(m[1], 10);

      var shippedCell = row.querySelector('.shipmen-logistics-table__cell.width-115');
      if (!shippedCell) continue;
      var input = shippedCell.querySelector('input.form-control');
      if (!input) continue;

      var shipped = parseInt(input.value, 10) || 0;

      if (shipped > inv) {
        shippedCell.classList.add('ss-guard-over');
        var badge = shippedCell.querySelector('.ss-guard-warning');
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'ss-guard-warning';
          shippedCell.appendChild(badge);
        }
        badge.textContent = shipped + ' > ' + inv + ' INV';
        violations.push({ shipped: shipped, inv: inv });
      } else {
        shippedCell.classList.remove('ss-guard-over');
        var b = shippedCell.querySelector('.ss-guard-warning');
        if (b) b.remove();
      }

      if (!input.dataset.ssGuard) {
        input.dataset.ssGuard = '1';
        input.addEventListener('input', guardCheck);
        input.addEventListener('change', guardCheck);
      }
    }

    currentViolations = violations;

    var saveBtn = getSaveButton();
    if (saveBtn && !saveBtn.dataset.ssGuardIntercept) {
      saveBtn.dataset.ssGuardIntercept = '1';
      saveBtn.addEventListener('click', function(e) {
        if (currentViolations.length > 0 && !guardOverride) {
          e.stopImmediatePropagation();
          e.preventDefault();
          showOverlay(currentViolations.length);
        }
        if (guardOverride) {
          guardOverride = false;
        }
      }, true);
    }

    if (violations.length > 0 && !guardOverride) {
      showOverlay(violations.length);
    } else {
      hideOverlay();
    }
  }

  // --- Shade alert toasts ---
  var toastContainer = null;

  function getToastContainer() {
    if (toastContainer && document.body.contains(toastContainer)) return toastContainer;
    toastContainer = document.createElement('div');
    toastContainer.id = 'ss-shade-toasts';
    toastContainer.style.cssText = 'position:fixed;top:20px;right:20px;z-index:99998;display:flex;flex-direction:column;gap:8px;max-width:380px;';
    document.body.appendChild(toastContainer);
    return toastContainer;
  }

  function showToast(log) {
    var container = getToastContainer();
    if (container.children.length >= MAX_TOASTS) return;

    var toast = document.createElement('div');
    toast.className = 'ss-shade-toast';

    var title = document.createElement('div');
    title.className = 'ss-shade-toast-title';
    title.textContent = '\u26A0 Phantom quantity detected';
    toast.appendChild(title);

    var line1 = document.createElement('div');
    line1.className = 'ss-shade-toast-line';
    line1.textContent = log.asin + ' | #' + log.shipment_id + ' | shade: ' + (log.shade > 0 ? '+' : '') + log.shade;
    toast.appendChild(line1);

    var line2 = document.createElement('div');
    line2.className = 'ss-shade-toast-line';
    line2.textContent = log.warehouse + ' \u2014 ' + log.user;
    toast.appendChild(line2);

    var timeEl = document.createElement('div');
    timeEl.className = 'ss-shade-toast-time';
    timeEl.textContent = relativeTime(log.created_at);
    toast.appendChild(timeEl);

    toast.addEventListener('click', function() { toast.remove(); });

    container.insertBefore(toast, container.firstChild);

    setTimeout(function() {
      if (toast.parentElement) toast.remove();
    }, TOAST_DURATION_MS);
  }

  function relativeTime(dateStr) {
    if (!dateStr) return '';
    var d = new Date(dateStr.replace(' ', 'T') + '-07:00');
    var diff = Math.floor((Date.now() - d.getTime()) / 60000);
    if (diff < 1) return '\u043F\u0440\u0435\u0434\u0438 \u043C\u0430\u043B\u043A\u043E';
    if (diff < 60) return '\u043F\u0440\u0435\u0434\u0438 ' + diff + ' \u043C\u0438\u043D.';
    var hours = Math.floor(diff / 60);
    if (hours < 24) return '\u043F\u0440\u0435\u0434\u0438 ' + hours + ' \u0447.';
    return '\u043F\u0440\u0435\u0434\u0438 ' + Math.floor(hours / 24) + ' \u0434\u043D.';
  }

  // --- Shade polling ---
  function pollShade() {
    chrome.storage.local.get(['ssApiUrl', 'ssApiToken', 'ssLastSeen', 'ssUnseenCount'], function(data) {
      var apiUrl = data.ssApiUrl;
      var token = data.ssApiToken;
      if (!apiUrl || !token) return;

      var since = data.ssLastSeen || '';
      var url = apiUrl + '/api/phantom-logs/?token=' + encodeURIComponent(token);
      if (since) url += '&since=' + encodeURIComponent(since);

      fetch(url).then(function(r) { return r.json(); }).then(function(logs) {
        if (!logs || !logs.length) return;

        logs.forEach(function(log) { showToast(log); });

        var newest = logs[0].created_at;
        var unseen = (data.ssUnseenCount || 0) + logs.length;
        chrome.storage.local.set({ ssLastSeen: newest, ssUnseenCount: unseen });
      }).catch(function() { /* silently skip */ });
    });
  }

  // --- Init ---
  setInterval(guardCheck, GUARD_POLL_MS);
  guardCheck();

  setInterval(pollShade, SHADE_POLL_MS);
  setTimeout(pollShade, 2000);
})();
```

- [ ] **Step 3: Commit**

```bash
git add ss-guard-extension/guard.js ss-guard-extension/guard.css
git commit -m "Add guard override button, shade polling, and toast notifications"
```

---

### Task 5: Add toast CSS styles

**Files:**
- Modify: `ss-guard-extension/guard.css` (append toast styles)

- [ ] **Step 1: Add toast CSS**

Append to the end of `ss-guard-extension/guard.css`:

```css
/* Shade alert toasts */
.ss-shade-toast {
  background: #1e1b4b;
  color: #e0e7ff;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  cursor: pointer;
  animation: ss-toast-in 0.3s ease;
  border-left: 4px solid #8b5cf6;
}

.ss-shade-toast-title {
  font-weight: 700;
  font-size: 13px;
  color: #c4b5fd;
  margin-bottom: 4px;
}

.ss-shade-toast-line {
  color: #e0e7ff;
  line-height: 1.4;
}

.ss-shade-toast-time {
  color: #818cf8;
  font-size: 11px;
  margin-top: 4px;
}

@keyframes ss-toast-in {
  from { opacity: 0; transform: translateX(40px); }
  to { opacity: 1; transform: translateX(0); }
}
```

- [ ] **Step 2: Commit**

```bash
git add ss-guard-extension/guard.css
git commit -m "Add toast notification styles for shade alerts"
```

---

### Task 6: Create extension popup (history panel)

**Files:**
- Create: `ss-guard-extension/popup.html`
- Create: `ss-guard-extension/popup.js`

- [ ] **Step 1: Create popup.html**

Create `ss-guard-extension/popup.html`:

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { width: 400px; max-height: 500px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 12px; background: #0f0b2e; color: #e0e7ff; }
  .header { padding: 12px 14px; background: #1e1b4b; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #312e81; }
  .header h1 { font-size: 14px; font-weight: 700; color: #c4b5fd; }
  .badge { background: #ef4444; color: #fff; font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 10px; }
  .actions { padding: 8px 14px; display: flex; gap: 8px; border-bottom: 1px solid #312e81; }
  .actions button { background: #312e81; border: none; color: #c4b5fd; font-size: 11px; padding: 4px 10px; border-radius: 4px; cursor: pointer; }
  .actions button:hover { background: #4338ca; }
  .list { overflow-y: auto; max-height: 380px; }
  .entry { padding: 10px 14px; border-bottom: 1px solid #1e1b4b; }
  .entry:hover { background: #1e1b4b; }
  .entry-asin { font-weight: 700; color: #c4b5fd; }
  .entry-detail { color: #a5b4fc; margin-top: 2px; }
  .entry-shade { color: #f87171; font-weight: 700; }
  .entry-time { color: #818cf8; font-size: 11px; margin-top: 2px; }
  .entry-user { color: #94a3b8; }
  .empty { padding: 40px; text-align: center; color: #6366f1; }
  .settings { padding: 10px 14px; border-top: 1px solid #312e81; }
  .settings label { display: block; color: #818cf8; font-size: 11px; margin-bottom: 2px; margin-top: 6px; }
  .settings input { width: 100%; background: #1e1b4b; border: 1px solid #312e81; color: #e0e7ff; padding: 4px 8px; border-radius: 4px; font-size: 11px; }
  .settings input:focus { outline: none; border-color: #6366f1; }
</style>
</head>
<body>
  <div class="header">
    <h1>Phantom Alerts</h1>
    <span class="badge" id="badge">0</span>
  </div>
  <div class="actions">
    <button id="mark-read">&#x2713; &#x41C;&#x430;&#x440;&#x43A;&#x438;&#x440;&#x430;&#x439; &#x432;&#x441;&#x438;&#x447;&#x43A;&#x438; &#x43A;&#x430;&#x442;&#x43E; &#x43F;&#x440;&#x43E;&#x447;&#x435;&#x442;&#x435;&#x43D;&#x438;</button>
    <button id="refresh">&#x21BB; &#x41E;&#x431;&#x43D;&#x43E;&#x432;&#x438;</button>
  </div>
  <div class="list" id="list"></div>
  <div class="settings">
    <label>Backend URL</label>
    <input type="text" id="api-url" placeholder="https://srv1563194.hstgr.cloud:4443">
    <label>API Token</label>
    <input type="password" id="api-token" placeholder="token">
  </div>
  <script src="popup.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create popup.js**

Create `ss-guard-extension/popup.js`:

```javascript
(function() {
  'use strict';

  var listEl = document.getElementById('list');
  var badgeEl = document.getElementById('badge');
  var urlInput = document.getElementById('api-url');
  var tokenInput = document.getElementById('api-token');

  // Load settings
  chrome.storage.local.get(['ssApiUrl', 'ssApiToken', 'ssUnseenCount'], function(data) {
    urlInput.value = data.ssApiUrl || '';
    tokenInput.value = data.ssApiToken || '';
    badgeEl.textContent = data.ssUnseenCount || 0;
    fetchLogs(data.ssApiUrl, data.ssApiToken);
  });

  // Save settings on change
  urlInput.addEventListener('change', function() {
    chrome.storage.local.set({ ssApiUrl: urlInput.value.replace(/\/+$/, '') });
  });
  tokenInput.addEventListener('change', function() {
    chrome.storage.local.set({ ssApiToken: tokenInput.value });
  });

  // Mark all read
  document.getElementById('mark-read').addEventListener('click', function() {
    chrome.storage.local.set({ ssUnseenCount: 0 });
    badgeEl.textContent = '0';
  });

  // Refresh
  document.getElementById('refresh').addEventListener('click', function() {
    chrome.storage.local.get(['ssApiUrl', 'ssApiToken'], function(data) {
      fetchLogs(data.ssApiUrl, data.ssApiToken);
    });
  });

  function fetchLogs(apiUrl, token) {
    if (!apiUrl || !token) {
      listEl.textContent = '';
      var msg = document.createElement('div');
      msg.className = 'empty';
      msg.textContent = '\u041D\u0430\u0441\u0442\u0440\u043E\u0439\u0442\u0435 URL \u0438 \u0442\u043E\u043A\u0435\u043D \u043F\u043E-\u0434\u043E\u043B\u0443.';
      listEl.appendChild(msg);
      return;
    }

    var since = new Date(Date.now() - 72 * 3600 * 1000).toISOString();
    var url = apiUrl + '/api/phantom-logs/?token=' + encodeURIComponent(token) + '&since=' + encodeURIComponent(since);

    fetch(url)
      .then(function(r) { return r.json(); })
      .then(function(logs) { renderLogs(logs); })
      .catch(function(e) {
        listEl.textContent = '';
        var msg = document.createElement('div');
        msg.className = 'empty';
        msg.textContent = '\u0413\u0440\u0435\u0448\u043A\u0430: ' + e.message;
        listEl.appendChild(msg);
      });
  }

  function renderLogs(logs) {
    listEl.textContent = '';
    if (!logs || !logs.length) {
      var msg = document.createElement('div');
      msg.className = 'empty';
      msg.textContent = '\u041D\u044F\u043C\u0430 phantom \u0430\u043B\u0435\u0440\u0442\u0438 \u0437\u0430 \u043F\u043E\u0441\u043B\u0435\u0434\u043D\u0438\u0442\u0435 72 \u0447\u0430\u0441\u0430.';
      listEl.appendChild(msg);
      return;
    }

    logs.forEach(function(log) {
      var entry = document.createElement('div');
      entry.className = 'entry';

      var asin = document.createElement('div');
      asin.className = 'entry-asin';
      asin.textContent = log.asin + '  #' + log.shipment_id;
      entry.appendChild(asin);

      var detail = document.createElement('div');
      detail.className = 'entry-detail';
      var shadeSpan = document.createElement('span');
      shadeSpan.className = 'entry-shade';
      shadeSpan.textContent = 'shade: ' + (log.shade > 0 ? '+' : '') + log.shade;
      detail.appendChild(shadeSpan);
      detail.appendChild(document.createTextNode('  |  param: ' + log.param_diff + '  real: ' + log.real_diff));
      entry.appendChild(detail);

      var warehouse = document.createElement('div');
      warehouse.className = 'entry-user';
      warehouse.textContent = log.warehouse + ' \u2014 ' + log.user;
      entry.appendChild(warehouse);

      var time = document.createElement('div');
      time.className = 'entry-time';
      time.textContent = relativeTime(log.created_at);
      entry.appendChild(time);

      listEl.appendChild(entry);
    });
  }

  function relativeTime(dateStr) {
    if (!dateStr) return '';
    var d = new Date(dateStr.replace(' ', 'T') + '-07:00');
    var diff = Math.floor((Date.now() - d.getTime()) / 60000);
    if (diff < 1) return '\u043F\u0440\u0435\u0434\u0438 \u043C\u0430\u043B\u043A\u043E';
    if (diff < 60) return '\u043F\u0440\u0435\u0434\u0438 ' + diff + ' \u043C\u0438\u043D.';
    var hours = Math.floor(diff / 60);
    if (hours < 24) return '\u043F\u0440\u0435\u0434\u0438 ' + hours + ' \u0447.';
    return '\u043F\u0440\u0435\u0434\u0438 ' + Math.floor(hours / 24) + ' \u0434\u043D.';
  }
})();
```

- [ ] **Step 3: Commit**

```bash
git add ss-guard-extension/popup.html ss-guard-extension/popup.js
git commit -m "Add extension popup with 72h phantom log history and settings"
```

---

### Task 7: Deploy backend and set token

**Files:**
- None (deployment task)

- [ ] **Step 1: Push code**

```bash
git push origin master
```

- [ ] **Step 2: Set the EXTENSION_API_TOKEN on VPS**

SSH into VPS, add `EXTENSION_API_TOKEN=<generate-a-random-token>` to `/docker/ss-logs-viewer/.env`, then pull and rebuild:

```bash
ssh root@72.62.0.128
# Add to .env: EXTENSION_API_TOKEN=<random-32-char-string>
cd /tmp/ss-logs-rebuild && git pull origin master
docker compose -p ss-logs-viewer up -d --build
```

- [ ] **Step 3: Test the API endpoint**

```bash
curl "https://srv1563194.hstgr.cloud:4443/api/phantom-logs/?token=<the-token>"
```

Expected: JSON array of phantom logs.

- [ ] **Step 4: Configure extension**

Open the extension popup, enter:
- Backend URL: `https://srv1563194.hstgr.cloud:4443`
- API Token: the token you set

Verify: logs appear in the popup history panel.

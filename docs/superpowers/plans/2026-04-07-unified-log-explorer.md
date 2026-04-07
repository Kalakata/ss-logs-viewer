# Unified Log Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace three separate pages with a single filterable, paginated log explorer at `/`.

**Architecture:** One Django view queries `SoStockedLog` with filter chains from query params, paginates with Django's `Paginator`, runs movement detection on current page results, renders a single template. Old views and templates are deleted.

**Tech Stack:** Django ORM, Django Paginator, server-side HTML rendering, Bootstrap 5 (already included)

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Rewrite | `logs/views.py` | Single `explorer` view + `trigger_report` (kept) + movement helpers (kept) |
| Create | `logs/templates/logs/explorer.html` | Filter bar + paginated table |
| Rewrite | `logs/templates/logs/base.html` | Simplified header (no search dropdown, no movements link) |
| Modify | `logs/urls.py` | Two routes: `/` and `/cron/send-report/` |
| Delete | `logs/templates/logs/index.html` | No longer needed |
| Delete | `logs/templates/logs/group_logs.html` | No longer needed |
| Delete | `logs/templates/logs/movements.html` | No longer needed |

---

### Task 1: Rewrite views.py with explorer view

**Files:**
- Rewrite: `logs/views.py`

- [ ] **Step 1: Replace `logs/views.py` entirely**

```python
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .models import Product, SoStockedLog
from .sostocked import TYPE_LABELS

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


def _apply_movement_detection(logs):
    """Detect cross-ASIN movements: manual inventory changes (type 14000)
    at the exact same timestamp across 2+ ASINs."""
    by_timestamp = defaultdict(list)
    for log in logs:
        if log['type_id'] == 14000:
            by_timestamp[log['created_at']].append(log)

    group_id = 0
    for ts, group_logs in by_timestamp.items():
        asins_involved = set(l['filter_asin'] for l in group_logs)
        if len(asins_involved) < 2:
            continue
        group_id += 1
        for l in group_logs:
            l['movement_group'] = group_id


def _apply_movement_balance(logs, bundle_map):
    """Calculate movement balance and units for logs with movement groups."""
    movement_groups = defaultdict(list)
    for log in logs:
        if log.get('movement_group'):
            movement_groups[log['movement_group']].append(log)
    for grp in movement_groups.values():
        total_units = sum(l['units'] for l in grp)
        for l in grp:
            l['movement_balanced'] = (total_units == 0)
            l['movement_net_units'] = total_units


def explorer(request):
    # --- Parse filters from query params ---
    q = request.GET.get('q', '').strip()
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    type_filter = request.GET.get('type', '')
    mismatch = request.GET.get('mismatch', '')
    page_num = request.GET.get('page', '1')

    try:
        page_num = int(page_num)
    except ValueError:
        page_num = 1

    # Default date range: last 7 days
    if not date_from and not date_to:
        default_from = datetime.now(timezone.utc) - timedelta(days=7)
        date_from = default_from.strftime('%Y-%m-%d')
        date_to = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # --- Build queryset ---
    qs = SoStockedLog.objects.all()

    if date_from:
        qs = qs.filter(created_at__gte=date_from)
    if date_to:
        # Include the full "to" day
        qs = qs.filter(created_at__lte=date_to + ' 23:59:59')

    if type_filter:
        try:
            qs = qs.filter(type_id=int(type_filter))
        except ValueError:
            pass

    if q:
        qs = qs.filter(
            Q(asin__icontains=q)
            | Q(product_name__icontains=q)
            | Q(user_name__icontains=q)
            | Q(description__icontains=q)
        )

    if mismatch:
        qs = qs.exclude(real_diff=F('param_diff'))

    qs = qs.order_by('-created_at')

    # --- Paginate ---
    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(page_num)

    # --- Build log dicts for template ---
    rows = list(page_obj.object_list)
    unique_asins = list({r.asin for r in rows})
    bundle_map = {}
    if unique_asins:
        try:
            products = Product.objects.filter(asin__in=unique_asins).values('asin', 'bundle_qty')
            bundle_map = {p['asin']: p['bundle_qty'] or 1 for p in products}
        except Exception as e:
            logger.error("Failed to query Product bundle_qty: %s", e)

    logs = []
    for row in rows:
        bq = bundle_map.get(row.asin, 1)
        logs.append({
            'filter_asin': row.asin,
            'id': row.ss_id,
            'created_at': row.created_at,
            'order_number': row.order_number,
            'param_diff': row.param_diff,
            'real_diff': row.real_diff,
            'old_qty': row.old_qty,
            'new_qty': row.new_qty,
            'user_name': row.user_name,
            'description': row.description,
            'vendor_name': row.vendor_name,
            'product_name': row.product_name,
            'order_shipment_id': row.order_shipment_id,
            'type_id': row.type_id,
            'type_label': TYPE_LABELS.get(row.type_id, str(row.type_id)),
            'bundle_qty': bq,
            'units': (row.param_diff or 0) * bq,
            'movement_group': None,
            'movement_balanced': None,
            'movement_net_units': 0,
        })

    _apply_movement_detection(logs)
    _apply_movement_balance(logs, bundle_map)

    movement_count = len(set(
        l['movement_group'] for l in logs if l.get('movement_group')
    ))

    # Build query string without page param for pagination links
    filter_params = []
    if q:
        filter_params.append(f'q={q}')
    if date_from:
        filter_params.append(f'from={date_from}')
    if date_to:
        filter_params.append(f'to={date_to}')
    if type_filter:
        filter_params.append(f'type={type_filter}')
    if mismatch:
        filter_params.append(f'mismatch={mismatch}')
    filter_qs = '&'.join(filter_params)

    return render(request, 'logs/explorer.html', {
        'logs': logs,
        'page_obj': page_obj,
        'movement_count': movement_count,
        'type_labels': TYPE_LABELS,
        'filter_qs': filter_qs,
        # Current filter values for form state
        'f_q': q,
        'f_from': date_from,
        'f_to': date_to,
        'f_type': type_filter,
        'f_mismatch': mismatch,
    })


@csrf_exempt
@require_GET
def trigger_report(request):
    from django.conf import settings as s
    token = request.GET.get('token', '')
    if not s.CRON_SECRET or token != s.CRON_SECRET:
        return HttpResponse('Forbidden', status=403)
    try:
        call_command('send_daily_report')
        return HttpResponse('OK')
    except Exception as e:
        return HttpResponse(f'Error: {e}', status=500)
```

- [ ] **Step 2: Commit**

```bash
git add logs/views.py
git commit -m "Replace views with single explorer view"
```

---

### Task 2: Create explorer template and update base

**Files:**
- Create: `logs/templates/logs/explorer.html`
- Rewrite: `logs/templates/logs/base.html`

- [ ] **Step 1: Replace `logs/templates/logs/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}SS Logs{% endblock %}</title>
  <style>
    :root { --header-h: 38px; }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 13px; margin: 0; padding: 0; background: #f5f6f8; color: #1a1a1a; }
    .app-header { height: var(--header-h); background: #1e1e2e; display: flex; align-items: center; padding: 0 12px; gap: 12px; position: fixed; top: 0; left: 0; right: 0; z-index: 100; }
    .app-header .brand { color: #a0a0b0; font-size: 12px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; white-space: nowrap; text-decoration: none; }
    .app-header .brand:hover { color: #fff; }
    {% block header_right_css %}{% endblock %}
    .app-body { padding-top: var(--header-h); }
    {% block extra_css %}{% endblock %}
  </style>
</head>
<body>
  <header class="app-header">
    <a class="brand" href="/">SS Logs</a>
    {% block header_right %}{% endblock %}
  </header>

  <div class="app-body">
    {% block content %}{% endblock %}
  </div>

  {% block extra_js %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Create `logs/templates/logs/explorer.html`**

```html
{% extends "logs/base.html" %}

{% block title %}Log Explorer — SS Logs{% endblock %}

{% block extra_css %}
<style>
  :root { --toolbar-h: auto; }

  .filter-bar { position: sticky; top: var(--header-h); z-index: 50; background: #fff; border-bottom: 1px solid #ddd; padding: 6px 12px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12px; }
  .filter-bar label { color: #888; font-size: 11px; white-space: nowrap; }
  .filter-bar input[type="text"],
  .filter-bar input[type="date"],
  .filter-bar select { height: 26px; font-size: 11px; padding: 0 6px; border: 1px solid #ccc; border-radius: 3px; background: #fff; }
  .filter-bar input[type="text"] { width: 200px; }
  .filter-bar input[type="date"] { width: 130px; }
  .filter-bar .btn-filter { height: 26px; font-size: 11px; padding: 0 10px; border: 1px solid #ccc; border-radius: 3px; background: #fff; cursor: pointer; color: #555; }
  .filter-bar .btn-filter:hover { background: #f0f0f0; }
  .filter-bar .btn-filter.active { background: #ffc107; border-color: #ffc107; color: #000; }
  .filter-bar .sep { width: 1px; height: 16px; background: #ddd; }
  .filter-bar .meta { color: #888; font-size: 11px; }

  .logs-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .logs-table thead { position: sticky; top: 72px; z-index: 40; }
  .logs-table th { background: #f0f1f3; padding: 3px 6px; text-align: left; font-weight: 600; font-size: 11px; color: #555; border-bottom: 2px solid #ddd; white-space: nowrap; }
  .logs-table td { padding: 2px 6px; border-bottom: 1px solid #eee; vertical-align: top; line-height: 1.4; }
  .logs-table tbody tr:hover > td { background: #f8f9fb; }

  .diff-pos { color: #16a34a; font-weight: 600; }
  .diff-neg { color: #b45309; font-weight: 600; }
  .diff-zero { color: #999; }
  .real-diff { color: #bbb; font-size: 10px; margin-left: 2px; font-weight: 400; }

  .movement-row > td { background: #fefce8 !important; }
  .movement-mismatch > td { background: #fef2f2 !important; }
  .movement-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #f59e0b; }

  .asin-tag { display: inline-block; padding: 0 4px; border-radius: 2px; background: #e0f2fe; color: #0369a1; font-size: 11px; }
  .type-tag { display: inline-block; padding: 0 4px; border-radius: 2px; background: #f1f5f9; color: #475569; font-size: 11px; }
  .qty-change { color: #888; font-size: 11px; }
  .wh-name { font-size: 11px; color: #7c3aed; }
  .desc { color: #666; word-break: break-word; max-width: 300px; }

  .pagination-bar { padding: 8px 12px; display: flex; align-items: center; justify-content: center; gap: 12px; font-size: 12px; color: #555; border-top: 1px solid #ddd; background: #fff; }
  .pagination-bar a { color: #1e40af; text-decoration: none; padding: 2px 8px; border: 1px solid #ccc; border-radius: 3px; }
  .pagination-bar a:hover { background: #eef2ff; }
  .pagination-bar .current { font-weight: 600; }

  .empty-state { padding: 40px; text-align: center; color: #999; font-size: 13px; }
</style>
{% endblock %}

{% block content %}
<form class="filter-bar" method="get" action="/">
  <label>Search</label>
  <input type="text" name="q" value="{{ f_q }}" placeholder="ASIN, product, user...">

  <span class="sep"></span>
  <label>From</label>
  <input type="date" name="from" value="{{ f_from }}">
  <label>To</label>
  <input type="date" name="to" value="{{ f_to }}">

  <span class="sep"></span>
  <label>Type</label>
  <select name="type">
    <option value="">All types</option>
    {% for tid, tlabel in type_labels.items %}
      <option value="{{ tid }}" {% if f_type == tid|stringformat:"d" %}selected{% endif %}>{{ tlabel }}</option>
    {% endfor %}
  </select>

  <span class="sep"></span>
  <label>
    <input type="checkbox" name="mismatch" value="1" {% if f_mismatch %}checked{% endif %} style="vertical-align:middle;">
    Mismatches only
  </label>

  <span class="sep"></span>
  <button type="submit" class="btn-filter">Apply</button>

  {% if f_q or f_type or f_mismatch %}
    <a href="/" class="btn-filter" style="text-decoration:none;">Reset</a>
  {% endif %}

  <span class="sep"></span>
  <span class="meta">{{ page_obj.paginator.count }} rows</span>
  {% if movement_count %}
    <span class="meta" style="color:#b45309;">{{ movement_count }} movements</span>
  {% endif %}
</form>

{% if logs %}
<table class="logs-table">
  <thead>
    <tr>
      <th style="width:14px;"></th>
      <th>Date</th>
      <th>ASIN</th>
      <th>Type</th>
      <th style="text-align:right;">Diff</th>
      <th>Qty</th>
      <th>Product</th>
      <th>Warehouse</th>
      <th>User</th>
      <th>Description</th>
    </tr>
  </thead>
  <tbody>
    {% for log in logs %}
    <tr class="{% if log.movement_group %}{% if log.movement_balanced %}movement-row{% else %}movement-mismatch{% endif %}{% endif %}">
      <td>{% if log.movement_group %}<span class="movement-dot" title="Movement #{{ log.movement_group }}{% if not log.movement_balanced %} — MISMATCH net {{ log.movement_net_units }}u{% endif %}"></span>{% endif %}</td>
      <td style="white-space:nowrap;color:#555;">{{ log.created_at }}</td>
      <td><span class="asin-tag">{{ log.filter_asin }}<span style="color:#0891b2;margin-left:2px;">x{{ log.bundle_qty }}</span></span></td>
      <td><span class="type-tag">{{ log.type_label }}</span></td>
      <td style="text-align:right;" class="{% if log.param_diff > 0 %}diff-pos{% elif log.param_diff < 0 %}diff-neg{% else %}diff-zero{% endif %}">{% if log.param_diff > 0 %}+{% endif %}{{ log.param_diff }}{% if log.real_diff != log.param_diff %}<span class="real-diff">{% if log.real_diff > 0 %}+{% endif %}{{ log.real_diff }}</span>{% endif %}</td>
      <td class="qty-change">{% if log.old_qty != None and log.new_qty != None %}{{ log.old_qty }}&rarr;{{ log.new_qty }}{% endif %}</td>
      <td style="font-size:11px;" class="desc">{{ log.product_name|truncatechars:60 }}</td>
      <td><span class="wh-name">{{ log.vendor_name }}</span></td>
      <td style="white-space:nowrap;">{{ log.user_name }}</td>
      <td class="desc">{{ log.description }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

{% if page_obj.paginator.num_pages > 1 %}
<div class="pagination-bar">
  {% if page_obj.has_previous %}
    <a href="?{{ filter_qs }}{% if filter_qs %}&{% endif %}page={{ page_obj.previous_page_number }}">&laquo; Prev</a>
  {% endif %}
  <span class="current">Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}</span>
  <span>({{ page_obj.paginator.count }} total)</span>
  {% if page_obj.has_next %}
    <a href="?{{ filter_qs }}{% if filter_qs %}&{% endif %}page={{ page_obj.next_page_number }}">Next &raquo;</a>
  {% endif %}
</div>
{% endif %}

{% else %}
  <div class="empty-state">No logs found matching your filters.</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 3: Commit**

```bash
git add logs/templates/logs/base.html logs/templates/logs/explorer.html
git commit -m "Add explorer template, simplify base layout"
```

---

### Task 3: Update routes, delete old files, deploy

**Files:**
- Rewrite: `logs/urls.py`
- Delete: `logs/templates/logs/index.html`
- Delete: `logs/templates/logs/group_logs.html`
- Delete: `logs/templates/logs/movements.html`

- [ ] **Step 1: Replace `logs/urls.py`**

```python
from django.urls import path
from . import views

urlpatterns = [
    path('', views.explorer, name='explorer'),
    path('cron/send-report/', views.trigger_report, name='trigger_report'),
]
```

- [ ] **Step 2: Delete old templates**

```bash
rm logs/templates/logs/index.html
rm logs/templates/logs/group_logs.html
rm logs/templates/logs/movements.html
```

- [ ] **Step 3: Commit**

```bash
git add logs/urls.py
git add -u logs/templates/logs/
git commit -m "Remove old pages, single explorer route at /"
```

- [ ] **Step 4: Push and deploy**

```bash
git push origin master
```

Then deploy via Hostinger API with the same environment variables.

- [ ] **Step 5: Verify**

Check that:
1. `/` loads the explorer with last 7 days of logs
2. Filters work (search, date range, type, mismatch)
3. Pagination works
4. Movement detection and row styling work
5. `/cron/send-report/?token=mySecret123xyz` still works

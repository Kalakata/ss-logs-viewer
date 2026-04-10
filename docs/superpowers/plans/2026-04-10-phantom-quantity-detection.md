# Phantom Quantity Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect and surface logs where `param_diff != real_diff` (phantom quantity) — annotate them in the UI and send a daily email alert.

**Architecture:** Compute `shade = param_diff - real_diff` on every log dict in the view layer. Show shade inline in Explorer and Movements templates with violet row highlighting. New management command emails a CSV of phantom logs daily.

**Tech Stack:** Django views, Django templates, Django management commands, Django `EmailMessage`

**Spec:** `docs/superpowers/specs/2026-04-10-phantom-quantity-detection-design.md`

---

### Task 1: Add shade field to Explorer view

**Files:**
- Modify: `logs/views.py:128-149` (explorer log dict building)

- [ ] **Step 1: Add `shade` and `real_diff` to log dict in explorer view**

In `logs/views.py`, in the `explorer()` function, find the log dict building loop (line ~131). Add `shade` after `units`:

```python
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
    'shade': (row.param_diff or 0) - (row.real_diff or 0),
})
```

- [ ] **Step 2: Commit**

```bash
git add logs/views.py
git commit -m "Add shade field to explorer view log dicts"
```

---

### Task 2: Add shade field to Movements view

**Files:**
- Modify: `logs/views.py:273-295` (movements log dict building)

- [ ] **Step 1: Add `shade` and `real_diff` to log dict in movements view**

In `logs/views.py`, in the `movements()` function, find the log dict building loop (line ~278). Add `shade` and `real_diff` to the dict:

```python
logs.append({
    'filter_asin': row.asin,
    'id': row.ss_id,
    'created_at': row.created_at,
    'param_diff': row.param_diff,
    'real_diff': row.real_diff,
    'old_qty': row.old_qty,
    'new_qty': row.new_qty,
    'user_name': row.user_name,
    'description': row.description,
    'vendor_name': row.vendor_name,
    'product_name': row.product_name,
    'type_label': TYPE_LABELS.get(row.type_id, str(row.type_id)),
    'bundle_qty': bq,
    'units': (row.param_diff or 0) * bq,
    'shade': (row.param_diff or 0) - (row.real_diff or 0),
    'movement_group': gid,
    'movement_balanced': meta.get('balanced'),
    'movement_net_units': meta.get('net_units', 0),
})
```

- [ ] **Step 2: Commit**

```bash
git add logs/views.py
git commit -m "Add shade field to movements view log dicts"
```

---

### Task 3: Update Explorer template with phantom styling and shade display

**Files:**
- Modify: `logs/templates/logs/explorer.html:32-33` (CSS), `logs/templates/logs/explorer.html:128-141` (table rows)

- [ ] **Step 1: Add phantom row CSS**

In `explorer.html`, after the `.row-disbalanced:hover` rule (line ~33), add:

```css
.logs-table tbody tr.row-phantom > td { background: #faf5ff; border-left: 4px solid #8b5cf6; }
.logs-table tbody tr.row-phantom:hover > td { background: #f3e8ff; }
.shade-val { color: #8b5cf6; font-size: 10px; margin-left: 3px; font-weight: 600; }
```

- [ ] **Step 2: Add phantom class to row and shade display in Units cell**

Change the `<tr>` tag (line ~129) to include `row-phantom` class when shade is non-zero:

```html
<tr data-units="{{ log.param_diff }}" data-asin="{{ log.filter_asin }}" {% if log.shade %}class="row-phantom"{% endif %}>
```

In the Units `<td>` (line ~133), after the existing bundle display and before the closing `</td>`, add the shade display:

```html
<td style="text-align:right;" class="units-cell {% if log.param_diff > 0 %}diff-pos{% elif log.param_diff < 0 %}diff-neg{% else %}diff-zero{% endif %}">{% if log.param_diff > 0 %}+{% endif %}{{ log.param_diff }}{% if log.bundle_qty > 1 %}<span class="raw-diff">({% if log.units > 0 %}+{% endif %}{{ log.units }})</span>{% endif %}{% if log.shade %}<span class="shade-val">real:{% if log.real_diff > 0 %}+{% endif %}{{ log.real_diff }}</span>{% endif %}</td>
```

- [ ] **Step 3: Verify in browser**

Open Explorer in the browser, find a date range that includes phantom logs (e.g. 2026-04-08 to 2026-04-09). Confirm:
- Phantom rows have violet left border and light purple background
- Units cell shows `real:X` in violet after the main param_diff
- Normal rows are unaffected
- Row selection (click-drag) still works on phantom rows

- [ ] **Step 4: Commit**

```bash
git add logs/templates/logs/explorer.html
git commit -m "Add phantom quantity highlighting to explorer template"
```

---

### Task 4: Update Movements template with phantom styling and shade display

**Files:**
- Modify: `logs/templates/logs/movements.html:36-38` (CSS), `logs/templates/logs/movements.html:110-121` (table rows)

- [ ] **Step 1: Add phantom row CSS**

In `movements.html`, after the `.net-units` rule (line ~38), add:

```css
.row-phantom > td { background: #faf5ff; border-left: 4px solid #8b5cf6; }
.row-phantom:hover > td { background: #f3e8ff; }
.shade-val { color: #8b5cf6; font-size: 10px; margin-left: 3px; font-weight: 600; }
```

- [ ] **Step 2: Add phantom class to row and shade display in Units cell**

Change the `<tr>` tag (line ~111) to include `row-phantom` when shade is non-zero. The movement classes should still apply when present:

```html
<tr class="{% if log.shade %}row-phantom{% endif %} {% if log.movement_group %}{% if log.movement_balanced %}movement-balanced{% else %}movement-mismatch{% endif %}{% endif %}">
```

In the Units `<td>` (line ~114), add the shade display after the existing net-units span:

```html
<td style="text-align:right;" class="units-cell {% if log.param_diff > 0 %}diff-pos{% elif log.param_diff < 0 %}diff-neg{% else %}diff-zero{% endif %}">{% if log.param_diff > 0 %}+{% endif %}{{ log.param_diff }}{% if log.bundle_qty > 1 %}<span class="raw-diff">({% if log.units > 0 %}+{% endif %}{{ log.units }})</span>{% endif %}{% if log.movement_group and not log.movement_balanced %}<span class="net-units">net:{{ log.movement_net_units }}</span>{% endif %}{% if log.shade %}<span class="shade-val">real:{% if log.real_diff > 0 %}+{% endif %}{{ log.real_diff }}</span>{% endif %}</td>
```

- [ ] **Step 3: Verify in browser**

Open Movements view, find a date range with phantom logs. Confirm:
- Phantom rows have violet styling
- Movement group coloring (green/red) still appears when applicable
- Shade value shown after net-units when both apply

- [ ] **Step 4: Commit**

```bash
git add logs/templates/logs/movements.html
git commit -m "Add phantom quantity highlighting to movements template"
```

---

### Task 5: Create send_phantom_report management command

**Files:**
- Create: `logs/management/commands/send_phantom_report.py`

- [ ] **Step 1: Create the command file**

Create `logs/management/commands/send_phantom_report.py`:

```python
import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.db.models import F

from logs.models import Product, SoStockedLog
from logs.sostocked import TYPE_LABELS

logger = logging.getLogger(__name__)

PACIFIC = timezone(timedelta(hours=-7))
EET = timezone(timedelta(hours=2))


def _to_eet(dt_str):
    """Convert a Pacific (UTC-7) datetime string to EET (UTC+2)."""
    if not dt_str:
        return ''
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=PACIFIC)
        return dt.astimezone(EET).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return dt_str


class Command(BaseCommand):
    help = 'Send daily email report of phantom quantity logs (param_diff != real_diff)'

    def handle(self, *args, **options):
        recipients = settings.REPORT_RECIPIENTS
        if not recipients:
            self.stderr.write('REPORT_RECIPIENTS not configured, skipping.')
            return

        self.stdout.write('Querying local DB for phantom logs in last 24h...')
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')
        qs = SoStockedLog.objects.filter(
            created_at__gte=cutoff_str,
        ).exclude(
            param_diff=F('real_diff'),
        ).order_by('-created_at')

        logs = []
        for row in qs:
            shade = (row.param_diff or 0) - (row.real_diff or 0)
            logs.append({
                'asin': row.asin,
                'created_at': row.created_at,
                'type_id': row.type_id,
                'type_label': TYPE_LABELS.get(row.type_id, str(row.type_id)),
                'param_diff': row.param_diff,
                'real_diff': row.real_diff,
                'shade': shade,
                'old_qty': row.old_qty,
                'new_qty': row.new_qty,
                'product_name': row.product_name,
                'vendor_name': row.vendor_name,
                'user_name': row.user_name,
                'description': row.description,
                'order_shipment_id': row.order_shipment_id,
            })

        self.stdout.write(f'Found {len(logs)} phantom quantity logs.')

        if not logs:
            self.stdout.write('No phantom logs to report, skipping email.')
            return

        # Look up bundle_qty
        unique_asins = list({l['asin'] for l in logs if l['asin']})
        bundle_map = {}
        if unique_asins:
            try:
                products = Product.objects.filter(asin__in=unique_asins).values('asin', 'bundle_qty')
                bundle_map = {p['asin']: p['bundle_qty'] or 1 for p in products}
            except Exception as e:
                logger.error('Failed to query bundle_qty: %s', e)

        for log in logs:
            bq = bundle_map.get(log['asin'], 1)
            log['bundle_qty'] = bq
            log['units'] = (log['param_diff'] or 0) * bq

        # Calculate summary
        total_shade_pos = sum(l['shade'] for l in logs if l['shade'] > 0)
        total_shade_neg = sum(l['shade'] for l in logs if l['shade'] < 0)

        # Build CSV
        buf = io.BytesIO()
        buf.write(b'\xef\xbb\xbf')
        text_wrapper = io.TextIOWrapper(buf, encoding='utf-8', newline='')
        writer = csv.writer(text_wrapper)
        writer.writerow([
            'Date (EET)', 'ASIN', 'Type', 'param_diff', 'real_diff', 'shade',
            'Bundle', 'Units', 'Qty Change', 'Product', 'Warehouse', 'User', 'Description',
        ])
        for l in logs:
            old_q = l.get('old_qty')
            new_q = l.get('new_qty')
            qty_change = f'{old_q} -> {new_q}' if old_q is not None and new_q is not None else ''
            writer.writerow([
                _to_eet(l.get('created_at', '')),
                l.get('asin', ''),
                l.get('type_label', ''),
                l.get('param_diff', 0),
                l.get('real_diff', 0),
                l.get('shade', 0),
                l.get('bundle_qty', 1),
                l.get('units', 0),
                qty_change,
                l.get('product_name', ''),
                l.get('vendor_name', ''),
                l.get('user_name', ''),
                l.get('description', ''),
            ])

        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        filename = f'phantom_qty_{today}.csv'

        body = f'{len(logs)} phantom quantity logs detected in the last 24 hours.'
        body += f'\nTotal phantom units: +{total_shade_pos} / {total_shade_neg}.'

        email = EmailMessage(
            subject=f'Phantom Quantity Alert — {today}',
            body=body,
            from_email=settings.EMAIL_HOST_USER,
            to=recipients,
        )
        text_wrapper.flush()
        email.attach(filename, buf.getvalue(), 'text/csv')
        email.send()

        self.stdout.write(self.style.SUCCESS(
            f'Phantom report sent to {", ".join(recipients)} ({len(logs)} rows).'
        ))
```

- [ ] **Step 2: Verify command runs locally**

Run: `python manage.py send_phantom_report`

Expected: Either "No phantom logs to report" (if DB is empty/no phantoms) or sends email. No crash.

- [ ] **Step 3: Commit**

```bash
git add logs/management/commands/send_phantom_report.py
git commit -m "Add send_phantom_report management command for daily phantom alerts"
```

---

### Task 6: Wire phantom report into worker schedule

**Files:**
- Modify: `worker.py:35-40` (add run function), `worker.py:66-68` (add to daily schedule)

- [ ] **Step 1: Add run_phantom_report function and call it at report time**

In `worker.py`, after the `run_report()` function (line ~40), add:

```python
def run_phantom_report():
    logger.info('Running send_phantom_report...')
    try:
        call_command('send_phantom_report')
    except Exception:
        logger.exception('send_phantom_report failed')
```

In the daily report check block (line ~67-68), add the phantom report call after `run_report()`:

```python
        if now.hour >= REPORT_HOUR_UTC and last_report_date != now.date():
            run_report()
            run_phantom_report()
            last_report_date = now.date()
```

- [ ] **Step 2: Commit**

```bash
git add worker.py
git commit -m "Schedule phantom report alongside daily movements report in worker"
```

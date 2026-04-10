# Phantom Quantity Detection — Design Spec

**Date:** 2026-04-10
**Context:** SoStocked logs have two diff fields: `param_diff` (what the system tracked) and `real_diff` (actual inventory change). When these diverge, phantom quantity exists — units added or removed that don't correspond to real inventory. `new_qty - old_qty == real_diff` holds in 100% of observed cases.

## Detection Logic

Every log gets a computed field:

```python
shade = param_diff - real_diff
```

- `shade == 0` — normal, no annotation
- `shade != 0, real_diff != 0` — partial phantom (real change + extra phantom units)
- `shade != 0, real_diff == 0` — pure phantom (no real change, old_qty == new_qty == 0)

No model changes or migrations needed. `param_diff` and `real_diff` are already stored in `SoStockedLog`.

## UI Annotation

### Explorer view (`logs/views.py:explorer`, `explorer.html`)

Each log dict gains:
- `shade`: `param_diff - real_diff` (int)

Template changes in the Units cell: when `shade != 0`, show `real_diff` in gray text next to the main `param_diff` value.

Row styling: phantom rows get a violet left-border and tint:
```css
.row-phantom > td { background: #faf5ff; border-left: 4px solid #8b5cf6; }
```

### Movements view (`logs/views.py:movements`, `movements.html`)

Same annotation: `shade` field added to each log dict, same template rendering of gray `real_diff` and violet row highlight when `shade != 0`.

## Email Notification

### New command: `send_phantom_report`

File: `logs/management/commands/send_phantom_report.py`

**Query:** Last 24h, `param_diff != real_diff`:
```python
cutoff = datetime.now(timezone.utc) - timedelta(days=1)
qs = SoStockedLog.objects.filter(created_at__gte=cutoff_str).exclude(param_diff=F('real_diff'))
```

**CSV columns:** Date (EET), ASIN, Type, param_diff, real_diff, shade, Bundle, Units, Qty Change, Product, Warehouse, User, Description

**Email body:** Summary line:
> "12 phantom quantity logs detected in the last 24 hours. Total phantom units: +45 / -120."

**No phantoms detected:** Skip email entirely (same pattern as existing `send_daily_report`).

### Worker scheduling

In `worker.py`, add `run_phantom_report()` that calls `send_phantom_report`. Run at 4:00 AM UTC alongside the existing daily report.

## Files Modified

1. `logs/views.py` — Add `shade` to log dicts in both `explorer()` and `movements()`
2. `logs/templates/logs/explorer.html` — Shade display in Units cell, `.row-phantom` CSS and row class
3. `logs/templates/logs/movements.html` — Same shade display and row styling
4. `logs/management/commands/send_phantom_report.py` — New file
5. `worker.py` — Add `run_phantom_report()` call at report time

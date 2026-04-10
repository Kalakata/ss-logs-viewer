import csv
import io
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .models import Product, SoStockedLog
from .sostocked import TYPE_LABELS

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


def _export_csv(qs):
    """Export queryset as CSV download."""
    buf = io.BytesIO()
    buf.write(b'\xef\xbb\xbf')  # BOM for Excel Cyrillic support
    wrapper = io.TextIOWrapper(buf, encoding='utf-8', newline='')
    writer = csv.writer(wrapper)
    writer.writerow(['Date', 'ASIN', 'Type', 'Diff', 'Real Diff', 'Old Qty', 'New Qty', 'Product', 'Warehouse', 'User', 'Description'])
    for row in qs.iterator():
        writer.writerow([
            row.created_at,
            row.asin,
            TYPE_LABELS.get(row.type_id, str(row.type_id)),
            row.param_diff,
            row.real_diff,
            row.old_qty if row.old_qty is not None else '',
            row.new_qty if row.new_qty is not None else '',
            row.product_name,
            row.vendor_name,
            row.user_name,
            row.description,
        ])
    wrapper.flush()
    response = HttpResponse(buf.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="ss-logs-export.csv"'
    return response


def explorer(request):
    # --- Parse filters from query params ---
    q = request.GET.get('q', '').strip()
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    type_filter = request.GET.get('type', '')
    user_filter = request.GET.get('user', '').strip()
    page_num = request.GET.get('page', '1')

    try:
        page_num = int(page_num)
    except ValueError:
        page_num = 1

    # Default date range: last 7 days (in Pacific, matching stored timestamps)
    PACIFIC = timezone(timedelta(hours=-7))
    if not date_from and not date_to:
        default_from = datetime.now(PACIFIC) - timedelta(days=7)
        date_from = default_from.strftime('%Y-%m-%dT00:00')
        date_to = datetime.now(PACIFIC).strftime('%Y-%m-%dT23:59')

    # --- Build queryset ---
    qs = SoStockedLog.objects.all()

    if date_from:
        qs = qs.filter(created_at__gte=date_from.replace('T', ' '))
    if date_to:
        to_val = date_to.replace('T', ' ')
        if len(to_val) <= 10:
            to_val += ' 23:59:59'
        qs = qs.filter(created_at__lte=to_val)

    if type_filter:
        try:
            qs = qs.filter(type_id=int(type_filter))
        except ValueError:
            pass

    if user_filter:
        qs = qs.filter(user_name__icontains=user_filter)

    if q:
        qs = qs.filter(
            Q(asin__icontains=q)
            | Q(product_name__icontains=q)
            | Q(user_name__icontains=q)
            | Q(description__icontains=q)
        )

    qs = qs.order_by('-created_at')

    # --- CSV export ---
    if request.GET.get('export') == 'csv':
        return _export_csv(qs)

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

    # Get distinct user names for the filter dropdown
    user_names = list(
        SoStockedLog.objects.exclude(user_name='')
        .values_list('user_name', flat=True)
        .distinct()
        .order_by('user_name')
    )

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
            'shade': (row.param_diff or 0) - (row.real_diff or 0),
        })

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
    if user_filter:
        filter_params.append(f'user={user_filter}')
    filter_qs = '&'.join(filter_params)

    return render(request, 'logs/explorer.html', {
        'logs': logs,
        'page_obj': page_obj,
        'type_labels': TYPE_LABELS,
        'user_names': user_names,
        'filter_qs': filter_qs,
        'f_q': q,
        'f_from': date_from,
        'f_to': date_to,
        'f_type': type_filter,
        'f_user': user_filter,
    })


def movements(request):
    """Dedicated view for manual inventory changes (type 14000) with movement grouping."""
    q = request.GET.get('q', '').strip()
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    user_filter = request.GET.get('user', '').strip()
    page_num = request.GET.get('page', '1')

    try:
        page_num = int(page_num)
    except ValueError:
        page_num = 1

    PACIFIC = timezone(timedelta(hours=-7))
    if not date_from and not date_to:
        default_from = datetime.now(PACIFIC) - timedelta(days=7)
        date_from = default_from.strftime('%Y-%m-%dT00:00')
        date_to = datetime.now(PACIFIC).strftime('%Y-%m-%dT23:59')

    qs = SoStockedLog.objects.filter(type_id=14000)

    if date_from:
        qs = qs.filter(created_at__gte=date_from.replace('T', ' '))
    if date_to:
        to_val = date_to.replace('T', ' ')
        if len(to_val) <= 10:
            to_val += ' 23:59:59'
        qs = qs.filter(created_at__lte=to_val)

    if user_filter:
        qs = qs.filter(user_name__icontains=user_filter)

    if q:
        qs = qs.filter(
            Q(asin__icontains=q)
            | Q(product_name__icontains=q)
            | Q(user_name__icontains=q)
            | Q(description__icontains=q)
        )

    qs = qs.order_by('-created_at')

    # --- CSV export ---
    if request.GET.get('export') == 'csv':
        return _export_csv(qs)

    # --- Movement detection on FULL filtered queryset (not page-scoped) ---
    all_rows = list(qs.values_list('ss_id', 'created_at', 'asin', 'param_diff'))
    by_timestamp = defaultdict(list)
    for ss_id, created_at, asin, param_diff in all_rows:
        by_timestamp[created_at].append((ss_id, asin, param_diff))

    movement_ss_ids = {}
    group_id = 0
    group_meta = {}
    for ts, entries in by_timestamp.items():
        asins = set(e[1] for e in entries)
        if len(asins) < 2:
            continue
        group_id += 1
        for ss_id, asin, param_diff in entries:
            movement_ss_ids[ss_id] = group_id
        group_meta[group_id] = {'timestamp': ts, 'entries': entries}

    # --- Paginate ---
    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(page_num)

    # --- Build log dicts ---
    rows = list(page_obj.object_list)
    unique_asins = list({r.asin for r in rows})
    all_movement_asins = set()
    for gid, meta in group_meta.items():
        for ss_id, asin, param_diff in meta['entries']:
            all_movement_asins.add(asin)
    all_asins_needed = list(set(unique_asins) | all_movement_asins)

    bundle_map = {}
    if all_asins_needed:
        try:
            products = Product.objects.filter(asin__in=all_asins_needed).values('asin', 'bundle_qty')
            bundle_map = {p['asin']: p['bundle_qty'] or 1 for p in products}
        except Exception as e:
            logger.error("Failed to query Product bundle_qty: %s", e)

    # Calculate balance for each movement group
    for gid, meta in group_meta.items():
        total_units = 0
        for ss_id, asin, param_diff in meta['entries']:
            bq = bundle_map.get(asin, 1)
            total_units += (param_diff or 0) * bq
        meta['balanced'] = (total_units == 0)
        meta['net_units'] = total_units

    logs = []
    for row in rows:
        bq = bundle_map.get(row.asin, 1)
        gid = movement_ss_ids.get(row.ss_id)
        meta = group_meta.get(gid, {})
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

    movement_count = len(group_meta)
    mismatch_count = sum(1 for m in group_meta.values() if not m['balanced'])

    # Get distinct user names for the filter dropdown
    user_names = list(
        SoStockedLog.objects.filter(type_id=14000).exclude(user_name='')
        .values_list('user_name', flat=True)
        .distinct()
        .order_by('user_name')
    )

    filter_params = []
    if q:
        filter_params.append(f'q={q}')
    if date_from:
        filter_params.append(f'from={date_from}')
    if date_to:
        filter_params.append(f'to={date_to}')
    if user_filter:
        filter_params.append(f'user={user_filter}')
    filter_qs = '&'.join(filter_params)

    return render(request, 'logs/movements.html', {
        'logs': logs,
        'page_obj': page_obj,
        'movement_count': movement_count,
        'mismatch_count': mismatch_count,
        'user_names': user_names,
        'filter_qs': filter_qs,
        'f_q': q,
        'f_from': date_from,
        'f_to': date_to,
        'f_user': user_filter,
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


@require_GET
def debug_types(request):
    """Diagnostic: fetch from API and report type_id distribution + save analysis."""
    import json
    from collections import Counter
    from .sostocked import fetch_all_logs_by_period
    days = int(request.GET.get('days', 7))
    try:
        logs = fetch_all_logs_by_period(days)
        counter = Counter(l.get('type_id', 0) for l in logs)

        # Check how many have valid IDs (needed for DB save)
        no_id = [l for l in logs if not l.get('id')]
        no_id_types = Counter(l.get('type_id', 0) for l in no_id)

        # Check type 14000 specifically
        t14000 = [l for l in logs if l.get('type_id') == 14000]
        t14000_no_id = [l for l in t14000 if not l.get('id')]
        t14000_sample = t14000[0] if t14000 else None

        # Check DB state
        db_total = SoStockedLog.objects.count()
        db_14000 = SoStockedLog.objects.filter(type_id=14000).count()

        # Try to save ONE type 14000 record and report result
        save_test = None
        if t14000_sample:
            l = t14000_sample
            try:
                obj = SoStockedLog(
                    ss_id=l.get('id'),
                    asin=l.get('filter_asin', ''),
                    area_name=l.get('area_name', ''),
                    created_at=l.get('created_at', ''),
                    order_number=l.get('order_number', ''),
                    param_diff=l.get('param_diff', 0),
                    real_diff=l.get('real_diff', 0),
                    old_qty=l.get('old_qty'),
                    new_qty=l.get('new_qty'),
                    user_name=l.get('user_name', ''),
                    description=l.get('description', ''),
                    vendor_name=l.get('vendor_name', ''),
                    product_name=l.get('product_name', ''),
                    order_shipment_id=str(l.get('order_shipment_id', '')),
                    type_id=l.get('type_id', 0),
                )
                obj.save()
                save_test = {'status': 'SUCCESS', 'saved_id': obj.ss_id}
            except Exception as save_err:
                save_test = {'status': 'FAILED', 'error': str(save_err), 'data': {
                    'ss_id': l.get('id'), 'asin': l.get('filter_asin'),
                    'param_diff': l.get('param_diff'), 'real_diff': l.get('real_diff'),
                    'type_id': l.get('type_id'),
                    'order_shipment_id': repr(l.get('order_shipment_id')),
                    'description_len': len(l.get('description', '')),
                    'product_name_len': len(l.get('product_name', '')),
                }}

        db_14000 = SoStockedLog.objects.filter(type_id=14000).count()

        result = {
            'api_total': len(logs),
            'days': days,
            'records_without_id': len(no_id),
            'type_14000': {
                'api_count': len(t14000),
                'without_id': len(t14000_no_id),
                'sample_keys': list(t14000_sample.keys()) if t14000_sample else [],
                'sample_id': t14000_sample.get('id') if t14000_sample else None,
                'sample_asin': t14000_sample.get('filter_asin') if t14000_sample else None,
                'sample_raw': {k: repr(v) for k, v in t14000_sample.items()} if t14000_sample else {},
            },
            'save_test': save_test,
            'db': {
                'total': SoStockedLog.objects.count(),
                'type_14000': db_14000,
            },
        }
        return HttpResponse(json.dumps(result, indent=2), content_type='application/json')
    except Exception as e:
        import traceback
        return HttpResponse(json.dumps({'error': str(e), 'trace': traceback.format_exc()}), content_type='application/json', status=500)

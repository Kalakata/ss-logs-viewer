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

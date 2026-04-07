import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

from django.core.management import call_command
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .models import ProductGroup, Product, Barcode, SoStockedLog
from .sostocked import TYPE_LABELS


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
    for group_logs in movement_groups.values():
        total_units = sum(l['units'] for l in group_logs)
        for l in group_logs:
            l['movement_balanced'] = (total_units == 0)
            l['movement_net_units'] = total_units


def index(request):
    return render(request, 'logs/index.html')


PAGE_SIZE = 30


def search_groups(request):
    q = request.GET.get('q', '').strip()
    page = int(request.GET.get('page', 1))
    if len(q) < 2:
        return JsonResponse({'results': [], 'has_next': False, 'page': 1})

    offset = (page - 1) * PAGE_SIZE

    # Find group IDs matching by barcode
    barcode_group_ids = list(
        Barcode.objects
        .filter(code__icontains=q)
        .values_list('product__product_group_id', flat=True)
        .distinct()[:30]
    )

    qs = (
        ProductGroup.objects
        .filter(Q(name__icontains=q) | Q(id__in=barcode_group_ids))
        .annotate(product_count=Count('products'))
        .order_by('-product_count', 'name')
    )
    total = qs.count()
    groups = qs[offset:offset + PAGE_SIZE]
    results = [
        {
            'id': g.id,
            'name': g.name,
            'product_count': g.product_count,
        }
        for g in groups
    ]
    return JsonResponse({
        'results': results,
        'page': page,
        'has_next': offset + PAGE_SIZE < total,
        'total': total,
    })


def group_logs(request, group_id):
    group = get_object_or_404(ProductGroup, pk=group_id)
    products = Product.objects.filter(product_group=group).order_by('asin')
    asin_list = [p.asin for p in products if p.asin]
    bundle_map = {p.asin: p.bundle_qty or 1 for p in products if p.asin}

    logs = []
    error = None
    if asin_list:
        try:
            qs = SoStockedLog.objects.filter(asin__in=asin_list).order_by('-created_at')
            for row in qs:
                log = {
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
                    'movement_group': None,
                }
                bq = bundle_map.get(row.asin, 1)
                log['bundle_qty'] = bq
                log['units'] = (row.param_diff or 0) * bq
                logs.append(log)

            _apply_movement_detection(logs)
            _apply_movement_balance(logs, bundle_map)

            logs.sort(key=lambda x: (x.get('created_at', ''), x.get('units', 0)), reverse=True)
        except Exception as e:
            error = str(e)

    movement_count = len(set(
        l['movement_group'] for l in logs if l.get('movement_group')
    ))

    event_types = sorted(
        {(l['type_id'], l['type_label']) for l in logs},
        key=lambda x: x[1],
    )

    log_data = [
        {
            'a': l['filter_asin'],
            't': l['created_at'],
            'd': l['param_diff'],
            'oq': l['old_qty'],
            'nq': l['new_qty'],
            'ti': l['type_id'],
            'mg': l.get('movement_group'),
            'mb': l.get('movement_balanced'),
        }
        for l in logs
    ]

    return render(request, 'logs/group_logs.html', {
        'group': group,
        'products': products,
        'asin_list': asin_list,
        'logs': logs,
        'error': error,
        'movement_count': movement_count,
        'event_types': event_types,
        'log_data': log_data,
        'bundle_map': bundle_map,
    })


PERIOD_CHOICES = [1, 3, 7, 14, 30, 60, 90]


def movements(request):
    days_param = request.GET.get('days')
    if days_param is None:
        return render(request, 'logs/movements.html', {
            'logs': [],
            'error': None,
            'days': None,
            'period_choices': PERIOD_CHOICES,
            'movement_count': 0,
        })

    try:
        days = int(days_param)
    except ValueError:
        days = 60
    if days not in PERIOD_CHOICES:
        days = 60

    logs = []
    error = None
    try:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')

        qs = SoStockedLog.objects.filter(
            type_id=14000,
            created_at__gte=cutoff_str,
        ).order_by('-created_at')

        unique_asins = list(qs.values_list('asin', flat=True).distinct())
        bundle_map = {}
        if unique_asins:
            try:
                products = Product.objects.filter(asin__in=unique_asins).values('asin', 'bundle_qty')
                bundle_map = {p['asin']: p['bundle_qty'] or 1 for p in products}
            except Exception as e:
                logger.error("Failed to query Product bundle_qty: %s", e)

        for row in qs:
            bq = bundle_map.get(row.asin, 1)
            log = {
                'filter_asin': row.asin,
                'area_name': row.area_name,
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
            }
            logs.append(log)

        _apply_movement_detection(logs)
        _apply_movement_balance(logs, bundle_map)

        logs.sort(key=lambda x: (x.get('created_at', ''), x.get('units', 0)), reverse=True)
    except Exception as e:
        error = str(e)

    movement_count = len(set(
        l['movement_group'] for l in logs if l.get('movement_group')
    ))

    return render(request, 'logs/movements.html', {
        'logs': logs,
        'error': error,
        'days': days,
        'period_choices': PERIOD_CHOICES,
        'movement_count': movement_count,
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

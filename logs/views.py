from collections import defaultdict

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Q

from .models import ProductGroup, Product, Barcode
from .sostocked import fetch_logs_for_asins, TYPE_LABELS


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
            logs = fetch_logs_for_asins(asin_list)
            for log in logs:
                bq = bundle_map.get(log['filter_asin'], 1)
                log['bundle_qty'] = bq
                log['units'] = (log['param_diff'] or 0) * bq

            # Check if movement groups balance in single units
            movement_groups = defaultdict(list)
            for log in logs:
                if log.get('movement_group'):
                    movement_groups[log['movement_group']].append(log)
            for group_logs in movement_groups.values():
                total_units = sum(l['units'] for l in group_logs)
                for l in group_logs:
                    l['movement_balanced'] = (total_units == 0)
                    l['movement_net_units'] = total_units

            # Re-sort: created_at DESC, negative units last within same timestamp
            logs.sort(key=lambda x: (x.get('created_at', ''), x.get('units', 0)), reverse=True)
        except Exception as e:
            error = str(e)

    movement_count = len(set(
        l['movement_group'] for l in logs if l.get('movement_group')
    ))

    # Collect distinct event types present in the data
    event_types = sorted(
        {(l['type_id'], l['type_label']) for l in logs},
        key=lambda x: x[1],
    )

    # Compact log data for JS chart/panels
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
    })

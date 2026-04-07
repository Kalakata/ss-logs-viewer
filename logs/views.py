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
    filter_qs = '&'.join(filter_params)

    return render(request, 'logs/explorer.html', {
        'logs': logs,
        'page_obj': page_obj,
        'type_labels': TYPE_LABELS,
        'filter_qs': filter_qs,
        'f_q': q,
        'f_from': date_from,
        'f_to': date_to,
        'f_type': type_filter,
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

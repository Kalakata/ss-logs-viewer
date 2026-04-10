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

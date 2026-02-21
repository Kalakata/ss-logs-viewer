import csv
import io
import logging
from datetime import datetime, timezone

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand

from logs.models import Product
from logs.sostocked import fetch_all_logs_by_period

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send daily CSV report of manual inventory changes (type_id=14000)'

    def handle(self, *args, **options):
        recipients = settings.REPORT_RECIPIENTS
        if not recipients:
            self.stderr.write('REPORT_RECIPIENTS not configured, skipping.')
            return

        self.stdout.write('Fetching last 1 day of logs...')
        all_logs = fetch_all_logs_by_period(1)
        logs = [l for l in all_logs if l['type_id'] == 14000]
        self.stdout.write(f'Found {len(logs)} manual inventory changes.')

        if not logs:
            self.stdout.write('No movements to report, skipping email.')
            return

        # Look up bundle_qty
        unique_asins = list({l['filter_asin'] for l in logs if l['filter_asin']})
        bundle_map = {}
        if unique_asins:
            try:
                products = Product.objects.filter(asin__in=unique_asins).values('asin', 'bundle_qty')
                bundle_map = {p['asin']: p['bundle_qty'] or 1 for p in products}
            except Exception as e:
                logger.error('Failed to query bundle_qty: %s', e)

        for log in logs:
            bq = bundle_map.get(log['filter_asin'], 1)
            log['bundle_qty'] = bq
            log['units'] = (log['param_diff'] or 0) * bq

        # Sort by date descending
        logs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Build CSV
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Date', 'ASIN', 'Diff', 'Units', 'Qty Change', 'Product', 'Warehouse', 'User'])
        for l in logs:
            old_q = l.get('old_qty')
            new_q = l.get('new_qty')
            qty_change = f'{old_q} -> {new_q}' if old_q is not None and new_q is not None else ''
            writer.writerow([
                l.get('created_at', ''),
                l.get('filter_asin', ''),
                l.get('param_diff', 0),
                l.get('units', 0),
                qty_change,
                l.get('product_name', ''),
                l.get('description', ''),
                l.get('user_name', ''),
            ])

        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        filename = f'movements_{today}.csv'

        email = EmailMessage(
            subject=f'Daily Movements Report — {today}',
            body=f'{len(logs)} manual inventory changes in the last 24 hours.',
            from_email=settings.EMAIL_HOST_USER,
            to=recipients,
        )
        email.attach(filename, buf.getvalue(), 'text/csv')
        email.send()

        self.stdout.write(self.style.SUCCESS(f'Report sent to {", ".join(recipients)} ({len(logs)} rows).'))

import csv
import io
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand

from logs.models import Product
from logs.sostocked import fetch_all_logs_by_period

logger = logging.getLogger(__name__)

EET = timezone(timedelta(hours=2))


def _to_eet(dt_str):
    """Convert a UTC datetime string to EET (UTC+2)."""
    if not dt_str:
        return ''
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        # If no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(EET).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return dt_str


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

        # Detect movement groups (same timestamp, 2+ ASINs) and check balance
        by_timestamp = defaultdict(list)
        for log in logs:
            by_timestamp[log['created_at']].append(log)

        for ts, group in by_timestamp.items():
            asins_involved = {l['filter_asin'] for l in group}
            if len(asins_involved) < 2:
                for l in group:
                    l['mismatch'] = ''
                continue
            total_units = sum(l['units'] for l in group)
            balanced = total_units == 0
            for l in group:
                l['mismatch'] = '' if balanced else 'MISMATCH'

        # Sort by date descending
        logs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        mismatch_count = sum(1 for l in logs if l.get('mismatch') == 'MISMATCH')

        # Build CSV (utf-8-sig adds BOM so Excel recognises Cyrillic)
        buf = io.BytesIO()
        buf.write(b'\xef\xbb\xbf')
        text_wrapper = io.TextIOWrapper(buf, encoding='utf-8', newline='')
        writer = csv.writer(text_wrapper)
        writer.writerow(['Date (EET)', 'ASIN', 'Bundle', 'Diff', 'Units', 'Qty Change', 'Product', 'Country', 'Warehouse', 'User', 'Description', 'Mismatch'])
        for l in logs:
            old_q = l.get('old_qty')
            new_q = l.get('new_qty')
            qty_change = f'{old_q} -> {new_q}' if old_q is not None and new_q is not None else ''
            writer.writerow([
                _to_eet(l.get('created_at', '')),
                l.get('filter_asin', ''),
                l.get('bundle_qty', 1),
                l.get('param_diff', 0),
                l.get('units', 0),
                qty_change,
                l.get('product_name', ''),
                l.get('area_name', ''),
                l.get('vendor_name', ''),
                l.get('user_name', ''),
                l.get('description', ''),
                l.get('mismatch', ''),
            ])

        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        filename = f'movements_{today}.csv'

        body = f'{len(logs)} manual inventory changes in the last 24 hours.'
        if mismatch_count:
            body += f'\n{mismatch_count} rows with MISMATCH (units don\'t balance).'

        email = EmailMessage(
            subject=f'Daily Movements Report — {today}',
            body=body,
            from_email=settings.EMAIL_HOST_USER,
            to=recipients,
        )
        text_wrapper.flush()
        email.attach(filename, buf.getvalue(), 'text/csv')
        email.send()

        self.stdout.write(self.style.SUCCESS(f'Report sent to {", ".join(recipients)} ({len(logs)} rows, {mismatch_count} mismatches).'))

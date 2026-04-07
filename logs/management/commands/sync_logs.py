import logging
from django.core.management.base import BaseCommand
from logs.models import SoStockedLog
from logs.sostocked import fetch_all_logs_by_period, TYPE_LABELS

logger = logging.getLogger(__name__)


def _save_logs(api_logs):
    """Insert new log entries, skip duplicates. Returns count of new entries."""
    if not api_logs:
        return 0

    # Get existing ss_ids to skip
    incoming_ids = [l['id'] for l in api_logs if l.get('id')]
    existing_ids = set(
        SoStockedLog.objects.filter(ss_id__in=incoming_ids)
        .values_list('ss_id', flat=True)
    )

    new_entries = []
    for l in api_logs:
        ss_id = l.get('id')
        if not ss_id or ss_id in existing_ids:
            continue
        new_entries.append(SoStockedLog(
            ss_id=ss_id,
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
        ))

    if new_entries:
        SoStockedLog.objects.bulk_create(new_entries, ignore_conflicts=True)

    return len(new_entries)


class Command(BaseCommand):
    help = 'Sync SoStocked logs to local database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=1,
            help='Number of days to fetch (default: 1, use 90 for backfill)',
        )

    def handle(self, *args, **options):
        days = options['days']
        self.stdout.write(f'Fetching logs for the last {days} day(s)...')

        try:
            api_logs = fetch_all_logs_by_period(days)
        except Exception as e:
            self.stderr.write(f'API fetch failed: {e}')
            return

        self.stdout.write(f'API returned {len(api_logs)} entries.')
        new_count = _save_logs(api_logs)
        total = SoStockedLog.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'Saved {new_count} new entries. Total in DB: {total}.'
        ))

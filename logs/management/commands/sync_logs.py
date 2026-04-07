import logging
from django.core.management.base import BaseCommand
from logs.models import SoStockedLog
from logs.sostocked import fetch_all_logs_by_period, TYPE_LABELS

logger = logging.getLogger(__name__)


def _save_logs(api_logs):
    """Insert new log entries, skip duplicates. Returns count of new entries."""
    if not api_logs:
        return 0

    # Deduplicate API records by ss_id (parallel page fetching can return duplicates)
    seen_ids = set()
    unique_logs = []
    for l in api_logs:
        ss_id = l.get('id')
        if not ss_id or ss_id in seen_ids:
            continue
        seen_ids.add(ss_id)
        unique_logs.append(l)
    dupes = len(api_logs) - len(unique_logs)
    logger.info("_save_logs: %d api_logs, %d unique, %d duplicates removed",
                len(api_logs), len(unique_logs), dupes)

    # Get existing ss_ids to skip — batch to avoid SQLite variable limits
    incoming_ids = [l['id'] for l in unique_logs]
    existing_ids = set()
    batch_size = 900
    for i in range(0, len(incoming_ids), batch_size):
        batch = incoming_ids[i:i + batch_size]
        existing_ids.update(
            SoStockedLog.objects.filter(ss_id__in=batch)
            .values_list('ss_id', flat=True)
        )
    logger.info("_save_logs: %d existing ids found", len(existing_ids))

    new_entries = []
    for l in unique_logs:
        ss_id = l['id']
        if ss_id in existing_ids:
            continue
        new_entries.append(SoStockedLog(
            ss_id=ss_id,
            asin=l.get('filter_asin') or '',
            area_name=l.get('area_name') or '',
            created_at=l.get('created_at') or '',
            order_number=l.get('order_number') or '',
            param_diff=l.get('param_diff') or 0,
            real_diff=l.get('real_diff') or 0,
            old_qty=l.get('old_qty'),
            new_qty=l.get('new_qty'),
            user_name=l.get('user_name') or '',
            description=l.get('description') or '',
            vendor_name=l.get('vendor_name') or '',
            product_name=l.get('product_name') or '',
            order_shipment_id=str(l.get('order_shipment_id') or ''),
            type_id=l.get('type_id') or 0,
        ))

    if new_entries:
        from collections import Counter
        type_dist = Counter(e.type_id for e in new_entries)
        logger.info("_save_logs: %d new entries to save. Types: %s",
                     len(new_entries),
                     {TYPE_LABELS.get(t, str(t)): c for t, c in type_dist.most_common(10)})
        SoStockedLog.objects.bulk_create(new_entries, batch_size=500, ignore_conflicts=True)
        saved_count = SoStockedLog.objects.count()
        logger.info("_save_logs: bulk_create done. DB total now: %d", saved_count)

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

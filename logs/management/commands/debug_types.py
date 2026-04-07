"""Diagnostic: fetch logs from API for N days and report type_id distribution."""
import json
from collections import Counter
from django.core.management.base import BaseCommand
from logs.sostocked import fetch_all_logs_by_period, TYPE_LABELS


class Command(BaseCommand):
    help = 'Fetch logs from SoStocked API and report type_id distribution'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **options):
        days = options['days']
        self.stdout.write(f'Fetching logs for {days} days...')
        logs = fetch_all_logs_by_period(days)
        self.stdout.write(f'Total records: {len(logs)}')

        counter = Counter(l.get('type_id', 0) for l in logs)
        self.stdout.write(f'\nType distribution:')
        for type_id, count in counter.most_common():
            label = TYPE_LABELS.get(type_id, f'UNMAPPED({type_id})')
            self.stdout.write(f'  {type_id:>6} ({label:>20}): {count}')

        if 14000 in counter:
            self.stdout.write(self.style.SUCCESS(f'\n✓ type 14000 found: {counter[14000]} records'))
        else:
            self.stdout.write(self.style.ERROR(f'\n✗ type 14000 NOT found in {len(logs)} records'))

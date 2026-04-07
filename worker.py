"""
Worker process that runs:
  - sync_logs every hour (fetches last 1 day of SoStocked logs)
  - send_daily_report at 4:00 AM UTC (6:00 AM EET)

Run as: python worker.py
"""
import os
import time
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ss_logs_viewer.settings')

import django
django.setup()

from django.core.management import call_command

REPORT_HOUR_UTC = 4  # 4:00 AM UTC = 6:00 AM EET
SYNC_INTERVAL = 3600  # 1 hour in seconds


def run_sync():
    logger.info('Running sync_logs...')
    try:
        call_command('sync_logs', '--days', '1')
    except Exception:
        logger.exception('sync_logs failed')


def run_report():
    logger.info('Running send_daily_report...')
    try:
        call_command('send_daily_report')
    except Exception:
        logger.exception('send_daily_report failed')


def main():
    logger.info('Worker started. Sync every %ds, report daily at %02d:00 UTC.', SYNC_INTERVAL, REPORT_HOUR_UTC)

    # On first run with empty DB, do a full backfill
    from logs.models import SoStockedLog
    if SoStockedLog.objects.count() == 0:
        logger.info('Empty DB detected, running backfill (3 days)...')
        try:
            call_command('sync_logs', '--days', '3')
        except Exception:
            logger.exception('Backfill failed')
    else:
        run_sync()

    last_report_date = None

    while True:
        time.sleep(SYNC_INTERVAL)

        run_sync()

        # Check if it's time for the daily report
        now = datetime.now(timezone.utc)
        if now.hour >= REPORT_HOUR_UTC and last_report_date != now.date():
            run_report()
            last_report_date = now.date()


if __name__ == '__main__':
    main()

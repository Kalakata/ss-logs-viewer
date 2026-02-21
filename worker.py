"""
Worker process that sends the daily movements report at 4:00 AM UTC (6:00 AM EET).
Run as: python worker.py
"""
import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ss_logs_viewer.settings')

import django
django.setup()

from django.core.management import call_command

TARGET_HOUR_UTC = 4  # 4:00 AM UTC = 6:00 AM EET


def seconds_until_next_run():
    now = datetime.now(timezone.utc)
    target = now.replace(hour=TARGET_HOUR_UTC, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main():
    logger.info('Worker started. Report scheduled daily at %02d:00 UTC.', TARGET_HOUR_UTC)
    while True:
        wait = seconds_until_next_run()
        logger.info('Next report in %.0f seconds (%.1f hours).', wait, wait / 3600)
        time.sleep(wait)
        logger.info('Running send_daily_report...')
        try:
            call_command('send_daily_report')
        except Exception:
            logger.exception('send_daily_report failed')


if __name__ == '__main__':
    main()

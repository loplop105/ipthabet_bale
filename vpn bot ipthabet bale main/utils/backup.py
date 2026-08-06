"""
زمان‌بندی پشتیبان‌گیری خودکار
"""
import threading
import logging
from database import backup_database

logger = logging.getLogger(__name__)

BACKUP_INTERVAL_HOURS = 6


def start_backup_scheduler():
    """شروع زمان‌بندی بکاپ در thread جداگانه"""
    def _run():
        while True:
            threading.Event().wait(BACKUP_INTERVAL_HOURS * 3600)
            backup_database()

    t = threading.Thread(target=_run, daemon=True, name="BackupScheduler")
    t.start()
    logger.info(f"Backup scheduler started (every {BACKUP_INTERVAL_HOURS}h).")

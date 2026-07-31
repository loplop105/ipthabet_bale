"""
مانیتورینگ سلامت پنل و هشدار به ادمین
"""
import threading
import logging
from datetime import datetime
from config import Config
from pasarguard import health_check
from bale_api import BaleAPI
from database import get_db, db_transaction

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 5
ALERT_THRESHOLD = 3  # تعداد خطای متوالی قبل از هشدار

_consecutive_failures = 0
_alert_sent = False


def _run_health_monitor():
    global _consecutive_failures, _alert_sent

    while True:
        threading.Event().wait(CHECK_INTERVAL_MINUTES * 60)
        result = health_check()

        # ثبت در دیتابیس
        try:
            with db_transaction() as conn:
                conn.execute(
                    'INSERT INTO health_logs (status, response_time_ms, error_message) VALUES (?, ?, ?)',
                    (result["status"], result.get("response_time_ms", 0), result.get("error", ""))
                )
        except Exception:
            pass

        if result["status"] == "down":
            _consecutive_failures += 1
            logger.warning(f"Panel health check FAILED ({_consecutive_failures}x): {result.get('error')}")

            if _consecutive_failures >= ALERT_THRESHOLD and not _alert_sent:
                BaleAPI.send_message(
                    Config.ADMIN_CHAT_ID,
                    f"🚨 <b>هشدار: پنل PasarGuard از دسترس خارج شد!</b>\n\n"
                    f"❌ تعداد خطاهای متوالی: {_consecutive_failures}\n"
                    f"⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    f"📝 خطا: {result.get('error', 'نامشخص')}"
                )
                _alert_sent = True
        else:
            if _alert_sent:
                BaleAPI.send_message(
                    Config.ADMIN_CHAT_ID,
                    f"✅ <b>پنل PasarGuard مجدداً در دسترس قرار گرفت.</b>\n"
                    f"⏱ زمان پاسخ: {result.get('response_time_ms', 0)}ms"
                )
            _consecutive_failures = 0
            _alert_sent = False


def start_health_monitor():
    t = threading.Thread(target=_run_health_monitor, daemon=True, name="HealthMonitor")
    t.start()
    logger.info(f"Health monitor started (interval: {CHECK_INTERVAL_MINUTES}min).")

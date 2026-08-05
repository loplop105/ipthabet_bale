"""
مانیتور انقضای اشتراک‌ها - هشدار به کاربر و غیرفعال‌سازی سرویس منقضی
"""
import threading
import logging
from datetime import datetime, timedelta
from config import Config
from bale_api import BaleAPI
from database import (
    get_db, db_transaction, get_expiring_subscriptions,
    expire_subscription, get_user
)
from pasarguard import disable_user

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 60  # بررسی هر ۱ ساعت
WARNING_DAYS = 3  # هشدار ۳ روز قبل از انقضا

# جلوگیری از هشدار تکراری برای یک اشتراک
_notified_subscriptions = set()


def _check_expirations():
    """بررسی اشتراک‌های نزدیک به انقضا و منقضی"""
    now = datetime.now()
    now_iso = now.isoformat()

    # ─── ۱. غیرفعال‌سازی اشتراک‌های منقضی ───
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT * FROM subscriptions 
                   WHERE status = "active" AND expire_at < ?
                   ORDER BY expire_at ASC''',
                (now_iso,)
            )
            expired_subs = cursor.fetchall()

        for sub in expired_subs:
            # غیرفعال در دیتابیس
            expire_subscription(sub['id'])
            # غیرفعال در پنل
            if sub['pg_username']:
                try:
                    disable_user(sub['pg_username'])
                    logger.info(f"Subscription #{sub['id']} ({sub['pg_username']}) disabled in panel.")
                except Exception as e:
                    logger.warning(f"Failed to disable {sub['pg_username']} in panel: {e}")

            # اطلاع به کاربر
            try:
                BaleAPI.send_message(
                    sub['user_id'],
                    f"⏰ <b>اشتراک شما منقضی شد!</b>\n\n"
                    f"اگر مایل به تمدید هستید، از بخش <b>حساب من</b> اقدام کنید."
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {sub['user_id']} about expiry: {e}")

        if expired_subs:
            logger.info(f"Expired {len(expired_subs)} subscriptions.")

    except Exception as e:
        logger.exception(f"Expiry check failed: {e}")

    # ─── ۲. هشدار به کاربران نزدیک به انقضا ───
    try:
        expiring = get_expiring_subscriptions(days_left=WARNING_DAYS)
        for sub in expiring:
            if sub['id'] in _notified_subscriptions:
                continue

            try:
                expire_dt = datetime.fromisoformat(sub['expire_at'])
                days_left = (expire_dt - now).days
                if days_left < 0:
                    continue

                user = get_user(sub['user_id'])
                username = f"@{user['username']}" if user and user['username'] else "کاربر عزیز"

                BaleAPI.send_message(
                    sub['user_id'],
                    f"⚠️ <b>اشتراک شما به زودی منقضی می‌شود!</b>\n\n"
                    f"{username} عزیز،\n"
                    f"📊 حجم: <b>{sub['volume_gb']} گیگابایت</b>\n"
                    f"⏰ زمان باقی‌مانده: <b>{days_left} روز</b>\n\n"
                    f"برای تمدید از دکمه <b>حساب من</b> در منوی اصلی استفاده کنید."
                )
                _notified_subscriptions.add(sub['id'])
                logger.info(f"Expiry warning sent to user {sub['user_id']} ({days_left} days left).")

            except Exception as e:
                logger.warning(f"Expiry warning failed for sub #{sub['id']}: {e}")

    except Exception as e:
        logger.exception(f"Expiry warning check failed: {e}")


def _run_subscription_monitor():
    """حلقه اصلی مانیتور"""
    while True:
        threading.Event().wait(CHECK_INTERVAL_MINUTES * 60)
        _check_expirations()


def start_subscription_monitor():
    """شروع مانیتور در thread جداگانه"""
    t = threading.Thread(target=_run_subscription_monitor, daemon=True, name="SubscriptionMonitor")
    t.start()
    logger.info(f"Subscription monitor started (interval: {CHECK_INTERVAL_MINUTES}min).")
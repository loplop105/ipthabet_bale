"""
تنظیمات مرتبط با دیتابیس
"""
import os
from dotenv import load_dotenv

load_dotenv()


class DatabaseConfig:
    # ─── مسیر فایل دیتابیس ───
    DB_FILE: str = os.getenv("DB_FILE", "vpn_bot.db")

    # ─── مسیر فایل دیتابیس هدیه ───
    GIFT_DB_FILE: str = os.getenv("GIFT_DB_FILE", "vpn_bot_gifts.db")

    # ─── SQLite Pragmas ───
    CONNECT_TIMEOUT: int = int(os.getenv("DB_CONNECT_TIMEOUT", "30"))
    BUSY_TIMEOUT: int = int(os.getenv("DB_BUSY_TIMEOUT", "5000"))

    # ─── بکاپ ───
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "./backups")
    BACKUP_RETENTION_DAYS: int = int(os.getenv("DB_BACKUP_RETENTION_DAYS", "7"))

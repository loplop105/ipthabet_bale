"""
تنظیمات مرکزی ربات - بارگذاری از متغیرهای محیطی
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ─── Bale Bot ───
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BASE_URL: str = f"https://tapi.bale.ai/bot{BOT_TOKEN}"
    ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))

    # ─── Payment ───
    CARD_NUMBER: str = os.getenv("CARD_NUMBER", "")
    CARD_HOLDER: str = os.getenv("CARD_HOLDER", "")
    PRICE_PER_GB: int = int(os.getenv("PRICE_PER_GB", "5000"))

    # ─── PasarGuard Panel ───
    PASARGUARD_URL: str = os.getenv("PASARGUARD_URL", "")
    PASARGUARD_API_KEY: str = os.getenv("PASARGUARD_API_KEY", "")

    # ─── Logging ───
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ─── Validation ───
    MAX_VOLUME_GB: int = int(os.getenv("MAX_VOLUME_GB", "500"))
    MIN_VOLUME_GB: int = int(os.getenv("MIN_VOLUME_GB", "1"))

    # ─── Rate Limiting ───
    RATE_LIMIT_SECONDS: float = float(os.getenv("RATE_LIMIT_SECONDS", "2"))

    # ─── Timeouts ───
    CONNECT_TIMEOUT: int = 5
    READ_TIMEOUT: int = 30
    API_TIMEOUT: tuple = (CONNECT_TIMEOUT, READ_TIMEOUT)

    # ─── Retry ───
    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 1.5  # seconds multiplier

    # ─── Category Display Names ───
    CATEGORY_NAMES: dict = {
        "VIP": "💎 VIP",
        "Economic": "💡 اقتصادی",
        "Dedicated": "🔒 اختصاصی",
        "Trade": "📈 ترید",
    }

    @classmethod
    def validate(cls):
        """بررسی وجود تنظیمات حیاتی"""
        required = ["BOT_TOKEN", "PASARGUARD_URL", "PASARGUARD_API_KEY", "ADMIN_CHAT_ID"]
        missing = [k for k in required if not getattr(cls, k)]
        if missing:
            raise EnvironmentError(
                f"تنظیمات ضروری زیر در .env موجود نیست: {', '.join(missing)}"
            )

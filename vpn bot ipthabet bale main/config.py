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
    # امکان چند ادمین (با کاما جدا کنید)
    ADMIN_CHAT_IDS: list = [int(x.strip()) for x in os.getenv("ADMIN_CHAT_IDS", str(ADMIN_CHAT_ID)).split(",") if x.strip()]

    # ─── Payment ───
    CARD_NUMBER: str = os.getenv("CARD_NUMBER", "")
    CARD_HOLDER: str = os.getenv("CARD_HOLDER", "")
    PRICE_PER_GB: int = int(os.getenv("PRICE_PER_GB", "5000"))  # قیمت پیش‌فرض (یکسان)

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

    # ─── Subscription ───
    DEFAULT_SUBSCRIPTION_DAYS: int = int(os.getenv("DEFAULT_SUBSCRIPTION_DAYS", "60"))
    GIFT_VOLUME_GB: float = float(os.getenv("GIFT_VOLUME_GB", "0.25"))
    GIFT_DAYS: int = int(os.getenv("GIFT_DAYS", "7"))

    # ─── Category Display Names ───
    CATEGORY_NAMES: dict = {
        "VIP": "💎 وی‌آی‌پی",
        "Economic": "💡 اقتصادی",
        "Dedicated": "🔒 اختصاصی",
        "Trade": "📈 ترید",
    }

    # ─── قیمت‌های مستقل هر دسته (تومان/گیگ) ───
    CATEGORY_PRICES: dict = {
        "VIP": 8000,
        "Economic": 5000,
        "Dedicated": 12000,
        "Trade": 10000,
    }

    # توضیحات کوتاه هر دسته برای نمایش در منو
    CATEGORY_DESCRIPTIONS: dict = {
        "VIP": "سرعت بالا + پایداری",
        "Economic": "اقتصادی و به‌صرفه",
        "Dedicated": "IP اختصاصی ویژه",
        "Trade": "اتصال پایدار برای ترید",
    }

    @classmethod
    def get_price_per_gb(cls, category: str = None, fallback: int = None) -> int:
        """قیمت هر گیگ برای یک دسته خاص"""
        if category and category in cls.CATEGORY_PRICES:
            return cls.CATEGORY_PRICES[category]
        return fallback or cls.PRICE_PER_GB

    @classmethod
    def validate(cls):
        """بررسی وجود تنظیمات حیاتی"""
        required = ["BOT_TOKEN", "PASARGUARD_URL", "PASARGUARD_API_KEY", "ADMIN_CHAT_ID"]
        missing = [k for k in required if not getattr(cls, k)]
        if missing:
            raise EnvironmentError(
                f"تنظیمات ضروری زیر در .env موجود نیست: {', '.join(missing)}"
            )
"""
Rate Limiter مبتنی بر حافظه (سریع‌تر از DB برای بررسی‌های مکرر)
"""
import time
import threading
from config import Config


class RateLimiter:
    def __init__(self, min_interval: float = None):
        self._min_interval = min_interval or Config.RATE_LIMIT_SECONDS
        self._last_request: dict = {}
        self._lock = threading.Lock()

    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        with self._lock:
            last = self._last_request.get(user_id, 0)
            if now - last < self._min_interval:
                return False
            self._last_request[user_id] = now
            return True

    def cleanup(self, max_age: float = 3600):
        """حذف ورودی‌های قدیمی"""
        now = time.time()
        with self._lock:
            expired = [uid for uid, t in self._last_request.items() if now - t > max_age]
            for uid in expired:
                del self._last_request[uid]


# Singleton
rate_limiter = RateLimiter()

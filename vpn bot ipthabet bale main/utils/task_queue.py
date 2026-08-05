"""
صف وظایف آسنکرون - اجرای عملیات سنگین (پنل، QR، ایمیل) در thread جداگانه
تا Long Polling ربات هرگز بلاک نشود.
"""
import queue
import threading
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class TaskQueue:
    """صف وظایف پس‌زمینه با Worker Thread"""

    def __init__(self, max_workers: int = 3, max_queue_size: int = 100):
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._workers: list = []
        self._max_workers = max_workers
        self._stop_event = threading.Event()

    def start(self):
        """شروع workerها"""
        for i in range(self._max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"TaskWorker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)
        logger.info(f"TaskQueue started with {self._max_workers} workers.")

    def stop(self, timeout: float = 5.0):
        """توقف graceful - اجازه می‌دهد وظایف در حال اجرا تمام شوند"""
        self._stop_event.set()
        # آیتم‌های sentinel برای آزاد کردن workerها
        for _ in range(self._max_workers):
            try:
                self._queue.put(None, timeout=1)
            except queue.Full:
                break
        for t in self._workers:
            t.join(timeout=timeout)

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> bool:
        """ارسال وظیفه به صف. برگشتی: True اگر موفق بود"""
        try:
            self._queue.put((fn, args, kwargs), block=False)
            return True
        except queue.Full:
            logger.warning("Task queue is full. Task dropped.")
            return False

    def _worker_loop(self):
        """حلقه اصلی worker"""
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            if task is None:  # sentinel برای توقف
                break

            fn, args, kwargs = task
            try:
                fn(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Task failed: {getattr(fn, '__name__', 'unknown')}: {e}")
            finally:
                self._queue.task_done()


# ─── Singleton ───
task_queue = TaskQueue()
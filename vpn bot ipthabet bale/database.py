"""
مدیریت دیتابیس SQLite با WAL mode و پشتیبانی از Transaction
"""
import sqlite3
import json
import logging
import shutil
import os
from datetime import datetime
from contextlib import contextmanager
from config import Config

logger = logging.getLogger(__name__)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(Config.DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def db_transaction():
    """Context manager برای تراکنش‌های اتمیک"""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            has_claimed_gift INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            referral_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            volume_gb INTEGER,
            amount INTEGER,
            config_code TEXT,
            pg_username TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS user_states (
            user_id INTEGER PRIMARY KEY,
            state TEXT,
            data TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS discount_codes (
            code TEXT PRIMARY KEY,
            discount_type TEXT DEFAULT 'percent',
            value INTEGER,
            max_uses INTEGER DEFAULT 1,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS rate_limits (
            user_id INTEGER PRIMARY KEY,
            last_request TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS health_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            response_time_ms INTEGER,
            error_message TEXT
        )''')
    logger.info("Database initialized successfully.")


# ─── User Functions ───

def register_user(user_id: int, username: str = None, referred_by: int = None):
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute(
                'INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)',
                (user_id, username, referred_by)
            )
            # افزایش شمارنده referral
            if referred_by:
                cursor.execute(
                    'UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?',
                    (referred_by,)
                )


def get_user(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()


# ─── State Functions ───

def set_user_state(user_id: int, state: str, data: dict = None):
    data_str = json.dumps(data) if data else None
    with db_transaction() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO user_states (user_id, state, data, updated_at) VALUES (?, ?, ?, ?)',
            (user_id, state, data_str, datetime.now().isoformat())
        )


def get_user_state(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT state, data FROM user_states WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            data = json.loads(row['data']) if row['data'] else {}
            return row['state'], data
    return None, {}


def clear_user_state(user_id: int):
    with db_transaction() as conn:
        conn.execute('DELETE FROM user_states WHERE user_id = ?', (user_id,))


# ─── Order Functions ───

def has_pending_order(user_id: int) -> bool:
    """بررسی وجود سفارش در انتظار - جلوگیری از سفارش تکراری"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id FROM orders WHERE user_id = ? AND status = "pending" LIMIT 1',
            (user_id,)
        )
        return cursor.fetchone() is not None


def create_order(user_id: int, category: str, volume_gb: int, amount: int) -> int:
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO orders (user_id, category, volume_gb, amount, status) VALUES (?, ?, ?, ?, ?)',
            (user_id, category, volume_gb, amount, 'pending')
        )
        return cursor.lastrowid


def get_order(order_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        return cursor.fetchone()


def get_completed_orders(user_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT id, category, volume_gb, amount, config_code, pg_username, created_at 
               FROM orders WHERE user_id = ? AND status = "completed" 
               ORDER BY created_at ASC''',
            (user_id,)
        )
        return cursor.fetchall()


def update_order_status(order_id: int, status: str, config_code: str = None, pg_username: str = None):
    with db_transaction() as conn:
        if config_code and pg_username:
            conn.execute(
                'UPDATE orders SET status = ?, config_code = ?, pg_username = ? WHERE id = ?',
                (status, config_code, pg_username, order_id)
            )
        else:
            conn.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))


def update_order_amount(order_id: int, new_amount: int):
    with db_transaction() as conn:
        conn.execute('UPDATE orders SET amount = ? WHERE id = ?', (new_amount, order_id))


# ─── Discount Code Functions ───

def apply_discount_code(code: str, order_id: int) -> dict:
    """
    اعمال کد تخفیف با تراکنش اتمیک - Rollback خودکار در صورت خطا
    """
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM discount_codes WHERE code = ? AND is_active = 1', (code,))
        disc = cursor.fetchone()

        cursor.execute(
            'SELECT id, category, volume_gb, amount FROM orders WHERE id = ? AND status = "pending"',
            (order_id,)
        )
        order = cursor.fetchone()

        if not order:
            return {"success": False, "error": "سفارش یافت نشد یا منقضی شده است."}

        base_amount = order['volume_gb'] * Config.PRICE_PER_GB
        if order['amount'] < base_amount:
            return {"success": False, "error": "روی این سفارش قبلاً کد تخفیف اعمال شده است."}

        if not disc or disc['used_count'] >= disc['max_uses']:
            return {"success": False, "error": "کد تخفیف نامعتبر یا منقضی شده است."}

        # محاسبه تخفیف
        if disc['discount_type'] == 'percent':
            discount_amount = int(base_amount * disc['value'] / 100)
        else:
            discount_amount = disc['value']

        new_amount = max(0, base_amount - discount_amount)

        # هر دو عملیات در یک تراکنش - اگر هر کدام fail شود، rollback می‌شود
        cursor.execute('UPDATE orders SET amount = ? WHERE id = ?', (new_amount, order_id))
        cursor.execute('UPDATE discount_codes SET used_count = used_count + 1 WHERE code = ?', (code,))

        return {
            "success": True,
            "new_amount": new_amount,
            "discount_amount": discount_amount,
            "order": order,
            "code": code,
        }


def create_discount_code(code: str, value: int, disc_type: str = 'percent', max_uses: int = 1) -> bool:
    try:
        with db_transaction() as conn:
            conn.execute(
                'INSERT INTO discount_codes (code, discount_type, value, max_uses) VALUES (?, ?, ?, ?)',
                (code, disc_type, value, max_uses)
            )
        return True
    except sqlite3.IntegrityError:
        return False


# ─── Rate Limit Functions ───

def check_rate_limit(user_id: int) -> bool:
    """بررسی rate limit - True یعنی مجاز است"""
    from datetime import datetime, timedelta
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT last_request FROM rate_limits WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        now = datetime.now()

        if row:
            last = datetime.fromisoformat(row['last_request'])
            if (now - last).total_seconds() < Config.RATE_LIMIT_SECONDS:
                return False

        conn.execute(
            'INSERT OR REPLACE INTO rate_limits (user_id, last_request) VALUES (?, ?)',
            (user_id, now.isoformat())
        )
        return True


# ─── Backup ───

def backup_database():
    """پشتیبان‌گیری خودکار از دیتابیس"""
    os.makedirs(Config.BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(Config.BACKUP_DIR, f"vpn_bot_{timestamp}.db")
    try:
        shutil.copy2(Config.DB_FILE, backup_path)
        logger.info(f"Database backed up to: {backup_path}")
        # حذف بکاپ‌های قدیمی (نگهداری ۷ روز)
        _cleanup_old_backups(days=7)
        return backup_path
    except Exception as e:
        logger.exception(f"Backup failed: {e}")
        return None


def _cleanup_old_backups(days: int = 7):
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)
    try:
        for f in os.listdir(Config.BACKUP_DIR):
            fpath = os.path.join(Config.BACKUP_DIR, f)
            if os.path.isfile(fpath) and f.endswith('.db'):
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if mtime < cutoff:
                    os.remove(fpath)
                    logger.info(f"Old backup removed: {f}")
    except Exception as e:
        logger.exception(f"Backup cleanup error: {e}")

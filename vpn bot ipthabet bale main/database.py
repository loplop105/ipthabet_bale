"""
مدیریت دیتابیس SQLite با WAL mode و پشتیبانی از Transaction
"""
import sqlite3
import json
import logging
import shutil
import os
from datetime import datetime, timedelta
from contextlib import contextmanager
from db_config import DatabaseConfig
from config import Config

logger = logging.getLogger(__name__)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DatabaseConfig.DB_FILE, timeout=DatabaseConfig.CONNECT_TIMEOUT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={DatabaseConfig.BUSY_TIMEOUT}")
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
            renewal_of INTEGER DEFAULT NULL,
            order_type TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # افزودن ستون‌های جدید به دیتابیس‌های قدیمی
        try:
            cursor.execute('ALTER TABLE orders ADD COLUMN renewal_of INTEGER DEFAULT NULL')
        except sqlite3.OperationalError:
            pass  # ستون از قبل وجود دارد
        try:
            cursor.execute('ALTER TABLE orders ADD COLUMN order_type TEXT DEFAULT "new"')
        except sqlite3.OperationalError:
            pass  # ستون از قبل وجود دارد
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
        # ─── جدول اشتراک‌ها (subscriptions) ───
        cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id INTEGER,
            category TEXT NOT NULL,
            volume_gb INTEGER NOT NULL,
            pg_username TEXT NOT NULL,
            config_code TEXT NOT NULL,
            status TEXT DEFAULT 'active',  -- active / expired / disabled
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expire_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions (user_id, status)'
        )
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_subscriptions_expire ON subscriptions (status, expire_at)'
        )
        # ─── جدول تنظیمات ادمین و لاگ‌ها ───
        cursor.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def get_pending_order(user_id: int):
    """دریافت سفارش معلق کاربر"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM orders WHERE user_id = ? AND status = "pending" LIMIT 1',
            (user_id,)
        )
        return cursor.fetchone()


def cancel_pending_order(user_id: int) -> bool:
    """لغو سفارش معلق کاربر"""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM orders WHERE user_id = ? AND status = "pending"',
            (user_id,)
        )
        return cursor.rowcount > 0


def cancel_order(order_id: int) -> bool:
    """لغو یک سفارش مشخص (فقط در حالت pending)"""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM orders WHERE id = ? AND status = "pending"',
            (order_id,)
        )
        return cursor.rowcount > 0


def create_order(user_id: int, category: str, volume_gb: int, amount: int,
                 renewal_of: int = None, order_type: str = 'new') -> int:
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO orders (user_id, category, volume_gb, amount, status, renewal_of, order_type) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user_id, category, volume_gb, amount, 'pending', renewal_of, order_type)
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


# ─── Subscription Functions ───

def create_subscription(user_id: int, order_id: int, category: str, volume_gb: int,
                        pg_username: str, config_code: str, days: int = None) -> int:
    """ثبت اشتراک جدید برای کاربر (بعد از تایید سفارش)"""
    days = days or Config.DEFAULT_SUBSCRIPTION_DAYS
    expire_at = datetime.now() + timedelta(days=days)
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO subscriptions 
               (user_id, order_id, category, volume_gb, pg_username, config_code, status, expire_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?)''',
            (user_id, order_id, category, volume_gb, pg_username, config_code, expire_at.isoformat())
        )
        return cursor.lastrowid


def extend_subscription(subscription_id: int, extra_days: int = None) -> bool:
    """تمدید اشتراک فعال (به‌جای ساخت سرویس جدید در پنل)"""
    extra_days = extra_days or Config.DEFAULT_SUBSCRIPTION_DAYS
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM subscriptions WHERE id = ?', (subscription_id,))
        sub = cursor.fetchone()
        if not sub:
            return False

        now = datetime.now()
        if sub['expire_at'] and datetime.fromisoformat(sub['expire_at']) > now:
            # هنوز فعال است → به expire_at فعلی اضافه کن
            new_expire = datetime.fromisoformat(sub['expire_at']) + timedelta(days=extra_days)
        else:
            # منقضی شده → از الان شروع کن
            new_expire = now + timedelta(days=extra_days)

        conn.execute(
            'UPDATE subscriptions SET expire_at = ?, status = "active" WHERE id = ?',
            (new_expire.isoformat(), subscription_id)
        )
        return True


def get_active_subscriptions(user_id: int):
    """دریافت اشتراک‌های فعال کاربر"""
    now = datetime.now().isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT * FROM subscriptions 
               WHERE user_id = ? AND status = "active" AND expire_at > ?
               ORDER BY expire_at ASC''',
            (user_id, now)
        )
        return cursor.fetchall()


def get_all_subscriptions(user_id: int):
    """دریافت همه اشتراک‌های کاربر (فعال + منقضی)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT * FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC''',
            (user_id,)
        )
        return cursor.fetchall()


def get_expiring_subscriptions(days_left: int = 3):
    """دریافت اشتراک‌هایی که به انقضا نزدیک هستند"""
    now = datetime.now()
    warning_time = (now + timedelta(days=days_left)).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT * FROM subscriptions 
               WHERE status = "active" AND expire_at BETWEEN ? AND ?
               ORDER BY expire_at ASC''',
            (now.isoformat(), warning_time)
        )
        return cursor.fetchall()


def expire_subscription(subscription_id: int):
    """غیرفعال کردن اشتراک منقضی"""
    with db_transaction() as conn:
        conn.execute(
            'UPDATE subscriptions SET status = "expired" WHERE id = ?',
            (subscription_id,)
        )


def get_latest_subscription(user_id: int):
    """دریافت آخرین اشتراک کاربر برای تمدید"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT * FROM subscriptions WHERE user_id = ? 
               ORDER BY created_at DESC LIMIT 1''',
            (user_id,)
        )
        return cursor.fetchone()


def get_subscription_by_id(subscription_id: int):
    """دریافت اشتراک با شناسه مشخص"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM subscriptions WHERE id = ?',
            (subscription_id,)
        )
        return cursor.fetchone()


def extend_subscription_volume(subscription_id: int, extra_gb: int) -> bool:
    """افزایش حجم اشتراک (به حجم فعلی اضافه می‌کند)"""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM subscriptions WHERE id = ?', (subscription_id,))
        sub = cursor.fetchone()
        if not sub:
            return False
        new_volume = sub['volume_gb'] + extra_gb
        conn.execute(
            'UPDATE subscriptions SET volume_gb = ? WHERE id = ?',
            (new_volume, subscription_id)
        )
        return True


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

        # قیمت پایه بر اساس دسته‌بندی واقعی، نه فقط PRICE_PER_GB
        base_amount = order['volume_gb'] * Config.get_price_per_gb(order['category'], Config.PRICE_PER_GB)
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


# ─── Admin Stats Functions ───

def get_admin_stats() -> dict:
    """آمار فروش و کاربران برای ادمین"""
    with get_db() as conn:
        cursor = conn.cursor()
        stats = {}

        cursor.execute('SELECT COUNT(*) as c FROM users')
        stats['total_users'] = cursor.fetchone()['c']

        cursor.execute('SELECT COUNT(*) as c FROM orders WHERE status = "completed"')
        stats['total_sales'] = cursor.fetchone()['c']

        cursor.execute('SELECT COALESCE(SUM(amount), 0) as s FROM orders WHERE status = "completed"')
        stats['total_revenue'] = cursor.fetchone()['s']

        cursor.execute('SELECT COUNT(*) as c FROM orders WHERE status = "pending"')
        stats['pending_orders'] = cursor.fetchone()['c']

        cursor.execute('SELECT COUNT(*) as c FROM subscriptions WHERE status = "active"')
        stats['active_subscriptions'] = cursor.fetchone()['c']

        # فروش امروز
        today_start = datetime.now().strftime('%Y-%m-%d') + " 00:00:00"
        cursor.execute(
            'SELECT COALESCE(SUM(amount), 0) as s FROM orders WHERE status = "completed" AND created_at >= ?',
            (today_start,)
        )
        stats['today_revenue'] = cursor.fetchone()['s']

        # فروش این هفته
        week_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'SELECT COALESCE(SUM(amount), 0) as s FROM orders WHERE status = "completed" AND created_at >= ?',
            (week_start,)
        )
        stats['week_revenue'] = cursor.fetchone()['s']

        return stats


def get_pending_orders(limit: int = 20):
    """لیست سفارشات در انتظار تایید"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''SELECT o.*, u.username FROM orders o 
               LEFT JOIN users u ON o.user_id = u.user_id 
               WHERE o.status = "pending" 
               ORDER BY o.created_at DESC LIMIT ?''',
            (limit,)
        )
        return cursor.fetchall()


def log_admin_action(admin_id: int, action: str, details: str = ""):
    """ثبت عملیات ادمین"""
    try:
        with db_transaction() as conn:
            conn.execute(
                'INSERT INTO admin_logs (admin_id, action, details) VALUES (?, ?, ?)',
                (admin_id, action, details)
            )
    except Exception as e:
        logger.exception(f"admin log failed: {e}")


# ─── Backup ───

def backup_database():
    """پشتیبان‌گیری خودکار از دیتابیس"""
    os.makedirs(DatabaseConfig.BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(DatabaseConfig.BACKUP_DIR, f"vpn_bot_{timestamp}.db")
    try:
        shutil.copy2(DatabaseConfig.DB_FILE, backup_path)
        logger.info(f"Database backed up to: {backup_path}")
        _cleanup_old_backups()
        return backup_path
    except Exception as e:
        logger.exception(f"Backup failed: {e}")
        return None


def _cleanup_old_backups():
    cutoff = datetime.now() - timedelta(days=DatabaseConfig.BACKUP_RETENTION_DAYS)
    try:
        for f in os.listdir(DatabaseConfig.BACKUP_DIR):
            fpath = os.path.join(DatabaseConfig.BACKUP_DIR, f)
            if os.path.isfile(fpath) and f.endswith('.db'):
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
                if mtime < cutoff:
                    os.remove(fpath)
                    logger.info(f"Old backup removed: {f}")
    except Exception as e:
        logger.exception(f"Backup cleanup error: {e}")
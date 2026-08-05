"""
ماژول ارتباط با پنل PasarGuard - شکسته‌شده به توابع مجزا
"""
import uuid
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import Config

logger = logging.getLogger(__name__)

# ─── Session با Retry ───
_session: requests.Session = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        retry_strategy = Retry(
            total=Config.MAX_RETRIES,
            backoff_factor=Config.RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "PATCH"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=5, pool_maxsize=10)
        _session.mount("https://", adapter)
        _session.headers.update({
            "X-Api-Key": Config.PASARGUARD_API_KEY,
            "Content-Type": "application/json",
        })
    return _session


# ─── توابع مجزا ───

def find_standard_group_id() -> int:
    """یافتن شناسه گروه Standard"""
    session = _get_session()
    endpoints = ["/api/group", "/api/groups", "/api/admin/groups", "/api/v1/group"]

    for ep in endpoints:
        try:
            url = f"{Config.PASARGUARD_URL}{ep}"
            res = session.get(url, timeout=Config.API_TIMEOUT)
            if res.status_code != 200:
                continue
            data = res.json()
            groups_list = []
            if isinstance(data, list):
                groups_list = data
            elif isinstance(data, dict):
                groups_list = data.get("items", data.get("groups", data.get("data", [])))
            if isinstance(groups_list, dict):
                groups_list = list(groups_list.values())

            for g in groups_list:
                if isinstance(g, dict) and g.get("name", "").lower() == "standard":
                    return g.get("id")
        except Exception as e:
            logger.debug(f"find_group endpoint {ep} failed: {e}")
            continue

    logger.warning("Standard group not found, using default ID=2")
    return 2


def generate_pg_username(prefix: str = "usr") -> str:
    """تولید نام کاربری تصادفی غیرقابل حدس"""
    short_uuid = uuid.uuid4().hex[:12]
    return f"{prefix}_{short_uuid}"


def create_panel_user(username: str, data_limit_bytes: int, expire_timestamp: int, group_id: int) -> dict:
    """ساخت کاربر در پنل - با fallback"""
    session = _get_session()
    url = f"{Config.PASARGUARD_URL}/api/user"
    payload = {
        "username": username,
        "data_limit": data_limit_bytes,
        "expire": expire_timestamp,
        "status": "active",
        "group_ids": [group_id],
    }

    res = session.post(url, json=payload, timeout=Config.API_TIMEOUT)

    if res.status_code not in [200, 201]:
        # Fallback: بدون group_ids
        payload.pop("group_ids", None)
        res = session.post(url, json=payload, timeout=Config.API_TIMEOUT)
        if res.status_code not in [200, 201]:
            raise RuntimeError(f"Create user failed ({res.status_code}): {res.text}")

    try:
        return res.json()
    except Exception:
        return {}


def assign_user_to_group(username: str, group_id: int, numeric_id: int = None):
    """اختصاص کاربر به گروه"""
    session = _get_session()
    url = f"{Config.PASARGUARD_URL}/api/user/{username}"

    try:
        res = session.get(url, timeout=Config.API_TIMEOUT)
        if res.status_code == 200:
            current_groups = res.json().get("group_ids", [])
            if group_id in current_groups:
                return  # قبلاً اختصاص یافته
    except Exception:
        pass

    # تلاش برای PUT
    try:
        res = session.put(url, json={"group_ids": [group_id]}, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            return
    except Exception:
        pass

    # Fallback: bulk add
    if numeric_id:
        try:
            bulk_url = f"{Config.PASARGUARD_URL}/api/groups/bulk/add"
            session.post(bulk_url, json={"group_ids": [group_id], "users": [numeric_id]}, timeout=Config.API_TIMEOUT)
        except Exception as e:
            logger.exception(f"Bulk group assign failed: {e}")


def get_subscription_url(username: str) -> str | None:
    """دریافت لینک اشتراک کاربر"""
    session = _get_session()

    # روش ۱: از اطلاعات کاربر
    try:
        url = f"{Config.PASARGUARD_URL}/api/user/{username}"
        res = session.get(url, timeout=Config.API_TIMEOUT)
        if res.status_code == 200:
            data = res.json()
            sub_url = data.get("subscription_url") or data.get("sub_url")
            if sub_url:
                return sub_url
            links = data.get("links", {})
            if isinstance(links, dict):
                sub_url = links.get("v2ray") or links.get("subscription_url")
            elif isinstance(links, str):
                sub_url = links
            if sub_url:
                return sub_url
    except Exception as e:
        logger.debug(f"get_sub from user data failed: {e}")

    # روش ۲: endpoint لینک‌ها
    try:
        links_url = f"{Config.PASARGUARD_URL}/api/user/{username}/links"
        res = session.get(links_url, timeout=Config.API_TIMEOUT)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                return data.get("v2ray") or data.get("subscription_url") or data.get("sub_url")
            elif isinstance(data, list) and data:
                return data[0] if isinstance(data[0], str) else data[0].get("link")
    except Exception as e:
        logger.debug(f"get_sub from links endpoint failed: {e}")

    return None


def check_username_exists(username: str) -> bool:
    """بررسی وجود کاربر"""
    session = _get_session()
    try:
        url = f"{Config.PASARGUARD_URL}/api/user/{username}"
        res = session.get(url, timeout=Config.API_TIMEOUT)
        return res.status_code == 200
    except Exception:
        return False


# ─── توابع مدیریت سرویس (تمدید، تغییر حجم، وضعیت) ───

def get_user_info(username: str) -> dict | None:
    """دریافت اطلاعات کامل کاربر از پنل (حجم مصرفی، وضعیت، انقضا)"""
    session = _get_session()
    try:
        url = f"{Config.PASARGUARD_URL}/api/user/{username}"
        res = session.get(url, timeout=Config.API_TIMEOUT)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.debug(f"get_user_info failed for {username}: {e}")
    return None


def get_user_usage(username: str) -> dict:
    """دریافت حجم مصرفی کاربر"""
    info = get_user_info(username)
    if not info:
        return {"used_bytes": 0, "data_limit_bytes": 0, "used_gb": 0.0, "limit_gb": 0}

    used = int(info.get("used_traffic", info.get("used_bytes", 0)) or 0)
    limit = int(info.get("data_limit", info.get("data_limit_bytes", 0)) or 0)
    return {
        "used_bytes": used,
        "data_limit_bytes": limit,
        "used_gb": round(used / (1024**3), 2),
        "limit_gb": round(limit / (1024**3), 2) if limit else 0,
    }


def _parse_expire_to_timestamp(expire_value) -> int:
    """تبدیل expire به timestamp عددی - پشتیبانی از string و int"""
    if not expire_value:
        return 0
    if isinstance(expire_value, (int, float)):
        return int(expire_value)
    # string → تلاش برای parse
    try:
        # فرمت ISO: "2026-10-04T01:13:00" یا "2026-10-04 01:13"
        from datetime import datetime
        s = str(expire_value).strip()
        # حذف Z و تبدیل به datetime
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp())
    except Exception:
        try:
            # فرمت عددی به صورت string: "1770000000"
            return int(str(expire_value))
        except Exception:
            return 0


def update_user_expiry(username: str, days: int) -> bool:
    """تمدید زمان انقضای کاربر در پنل - به expire فعلی اضافه می‌کند"""
    session = _get_session()
    url = f"{Config.PASARGUARD_URL}/api/user/{username}"
    now = int(time.time())
    new_expire = now + (days * 86400)

    # ─── ۱. دریافت اطلاعات فعلی کاربر ───
    info = get_user_info(username)
    if info:
        current_expire = _parse_expire_to_timestamp(info.get("expire", 0))
        # اگر هنوز فعال است → به expire فعلی اضافه کن
        if current_expire > now:
            new_expire = current_expire + (days * 86400)
            logger.info(f"Extending expiry from {current_expire} + {days}d = {new_expire}")

    # ─── ۲. روش اول: PUT کامل — همه فیلدهای موجود + expire جدید ───
    # (برخی پنل‌ها PUT جزئی را reject می‌کنند)
    # مهم: data_limit فعلی هم ارسال می‌شود تا حجم از بین نرود
    if info and isinstance(info, dict):
        # حذف فیلدهای محاسباتی/سیستمی که نباید ارسال شوند
        exclude_keys = {"id", "created_at", "links", "subscription_url", "proxies", "inbounds", "online_at", "last_online_at"}
        payload = {k: v for k, v in info.items() if k not in exclude_keys}
        payload["expire"] = new_expire
        # اطمینان از حفظ حجم فعلی (data_limit و data_limit_bytes)
        current_limit = info.get("data_limit", info.get("data_limit_bytes", 0)) or 0
        payload["data_limit"] = current_limit
        payload["data_limit_bytes"] = current_limit
        try:
            res = session.put(url, json=payload, timeout=Config.API_TIMEOUT)
            if res.status_code in [200, 201]:
                logger.info(f"User {username} expiry updated via full PUT. New expire: {new_expire}")
                return True
        except Exception as e:
            logger.debug(f"update_user_expiry full PUT failed: {e}")

    # ─── ۳. روش دوم: PUT فقط expire + حفظ data_limit ───
    try:
        current_limit = 0
        if info and isinstance(info, dict):
            current_limit = info.get("data_limit", info.get("data_limit_bytes", 0)) or 0
        res = session.put(url, json={"expire": new_expire, "data_limit": current_limit, "data_limit_bytes": current_limit}, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            logger.info(f"User {username} expiry updated via minimal PUT. New expire: {new_expire}")
            return True
    except Exception as e:
        logger.debug(f"update_user_expiry minimal PUT failed: {e}")

    # ─── ۴. روش سوم: PATCH ───
    try:
        res = session.patch(url, json={"expire": new_expire}, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            logger.info(f"User {username} expiry updated via PATCH. New expire: {new_expire}")
            return True
    except Exception as e:
        logger.debug(f"update_user_expiry PATCH failed: {e}")

    logger.warning(f"update_user_expiry failed for {username}")
    return False


def update_user_data_limit(username: str, volume_gb: float) -> bool:
    """افزایش/کاهش حجم کاربر در پنل"""
    session = _get_session()
    data_limit_bytes = int(volume_gb * 1024 * 1024 * 1024)

    try:
        url = f"{Config.PASARGUARD_URL}/api/user/{username}"
        res = session.put(url, json={"data_limit": data_limit_bytes}, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            return True
    except Exception as e:
        logger.debug(f"update_user_data_limit PUT failed: {e}")

    try:
        url = f"{Config.PASARGUARD_URL}/api/user/{username}"
        res = session.patch(url, json={"data_limit": data_limit_bytes}, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            return True
    except Exception as e:
        logger.debug(f"update_user_data_limit PATCH failed: {e}")

    logger.warning(f"update_user_data_limit failed for {username}")
    return False


def _verify_data_limit(username: str, expected_limit: int) -> bool:
    """بررسی اینکه حجم کاربر در پنل واقعاً تغییر کرده است"""
    info = get_user_info(username)
    if not info:
        return False
    actual = int(info.get("data_limit", info.get("data_limit_bytes", 0)) or 0)
    return actual == expected_limit


def add_user_volume(username: str, extra_gb: float) -> bool:
    """افزایش حجم کاربر در پنل - به حجم فعلی اضافه می‌کند"""
    session = _get_session()
    url = f"{Config.PASARGUARD_URL}/api/user/{username}"

    # ۱. دریافت حجم فعلی
    info = get_user_info(username)
    if not info:
        logger.warning(f"add_user_volume: user {username} not found")
        return False

    current_limit = int(info.get("data_limit", info.get("data_limit_bytes", 0)) or 0)
    extra_bytes = int(extra_gb * 1024 * 1024 * 1024)
    new_limit = current_limit + extra_bytes
    logger.info(f"Adding {extra_gb}GB to {username}: {current_limit} -> {new_limit}")

    # ۲. روش اول: PUT کامل — همه فیلدها + data_limit و data_limit_bytes
    exclude_keys = {"id", "created_at", "links", "subscription_url", "proxies", "inbounds", "online_at", "last_online_at"}
    payload = {k: v for k, v in info.items() if k not in exclude_keys}
    payload["data_limit"] = new_limit
    payload["data_limit_bytes"] = new_limit
    try:
        res = session.put(url, json=payload, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            if _verify_data_limit(username, new_limit):
                logger.info(f"User {username} volume verified after full PUT. New limit: {new_limit}")
                return True
            else:
                logger.warning(f"Full PUT returned OK but volume not changed for {username}. Trying next method...")
    except Exception as e:
        logger.debug(f"add_user_volume full PUT failed: {e}")

    # ۳. روش دوم: PUT فقط data_limit + data_limit_bytes
    try:
        res = session.put(url, json={"data_limit": new_limit, "data_limit_bytes": new_limit}, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            if _verify_data_limit(username, new_limit):
                logger.info(f"User {username} volume verified after minimal PUT. New limit: {new_limit}")
                return True
            else:
                logger.warning(f"Minimal PUT returned OK but volume not changed for {username}. Trying PATCH...")
    except Exception as e:
        logger.debug(f"add_user_volume minimal PUT failed: {e}")

    # ۴. روش سوم: PATCH
    try:
        res = session.patch(url, json={"data_limit": new_limit, "data_limit_bytes": new_limit}, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            if _verify_data_limit(username, new_limit):
                logger.info(f"User {username} volume verified after PATCH. New limit: {new_limit}")
                return True
            else:
                logger.warning(f"PATCH returned OK but volume not changed for {username}.")
    except Exception as e:
        logger.debug(f"add_user_volume PATCH failed: {e}")

    logger.warning(f"add_user_volume failed for {username}")
    return False


def disable_user(username: str) -> bool:
    """غیرفعال کردن کاربر (برای انقضای سرویس)"""
    session = _get_session()
    try:
        url = f"{Config.PASARGUARD_URL}/api/user/{username}"
        res = session.put(url, json={"status": "disabled"}, timeout=Config.API_TIMEOUT)
        if res.status_code in [200, 201]:
            return True
    except Exception as e:
        logger.debug(f"disable_user failed: {e}")
    return False


# ─── تابع اصلی (ارکستراتور) ───

def create_pasarguard_user(volume_gb: float, days: int = 60, prefix: str = "usr") -> tuple:
    """
    ساخت کاربر کامل در پنل PasarGuard
    Returns: (subscription_url, error_message)
    """
    try:
        # ۱. تولید username یکتا
        username = generate_pg_username(prefix)
        # بررسی عدم تکرار
        for _ in range(3):
            if not check_username_exists(username):
                break
            username = generate_pg_username(prefix)

        # ۲. محاسبات
        data_limit_bytes = int(volume_gb * 1024 * 1024 * 1024)
        expire_timestamp = int(time.time()) + (days * 86400) if days > 0 else 0

        # ۳. یافتن گروه
        group_id = find_standard_group_id()

        # ۴. ساخت کاربر
        user_data = create_panel_user(username, data_limit_bytes, expire_timestamp, group_id)
        numeric_id = user_data.get("id")

        # ۵. اختصاص به گروه
        assign_user_to_group(username, group_id, numeric_id)

        # ۶. دریافت لینک اشتراک
        sub_url = get_subscription_url(username)

        if sub_url:
            return sub_url, None, username
        else:
            return None, "کاربر ساخته شد اما لینک اشتراک یافت نشد.", username

    except Exception as e:
        logger.exception(f"create_pasarguard_user failed: {e}")
        return None, f"خطای ارتباط با سرور پنل: {e}", None


def health_check() -> dict:
    """بررسی سلامت پنل"""
    session = _get_session()
    start = time.time()
    try:
        url = f"{Config.PASARGUARD_URL}/api/user"
        res = session.get(url, timeout=Config.API_TIMEOUT)
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "status": "healthy" if res.status_code in [200, 401, 403] else "degraded",
            "response_time_ms": elapsed_ms,
            "status_code": res.status_code,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "status": "down",
            "response_time_ms": elapsed_ms,
            "error": str(e),
        }
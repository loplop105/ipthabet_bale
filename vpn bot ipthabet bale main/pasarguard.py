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
            allowed_methods=["GET", "POST", "PUT"],
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

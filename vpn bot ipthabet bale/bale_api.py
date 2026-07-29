"""
کلاس ارتباط با API بله - با Session و Retry
"""
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import Config

logger = logging.getLogger(__name__)


class BaleAPI:
    _session: requests.Session = None

    @classmethod
    def _get_session(cls) -> requests.Session:
        if cls._session is None:
            cls._session = requests.Session()
            retry_strategy = Retry(
                total=Config.MAX_RETRIES,
                backoff_factor=Config.RETRY_BACKOFF,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST"],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
            cls._session.mount("https://", adapter)
            cls._session.mount("http://", adapter)
        return cls._session

    @classmethod
    def send_message(cls, chat_id, text, reply_markup=None, parse_mode="HTML"):
        url = f"{Config.BASE_URL}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            return cls._get_session().post(url, json=payload, timeout=Config.API_TIMEOUT).json()
        except Exception as e:
            logger.exception(f"send_message failed: {e}")
            return None

    @classmethod
    def send_photo(cls, chat_id, photo, caption=None, reply_markup=None, parse_mode="HTML"):
        url = f"{Config.BASE_URL}/sendPhoto"
        payload = {"chat_id": chat_id, "photo": photo}
        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            return cls._get_session().post(url, json=payload, timeout=Config.API_TIMEOUT).json()
        except Exception as e:
            logger.exception(f"send_photo failed: {e}")
            return None

    @classmethod
    def send_photo_file(cls, chat_id, photo_file, caption=None, reply_markup=None, parse_mode="HTML"):
        url = f"{Config.BASE_URL}/sendPhoto"
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        files = {'photo': photo_file}
        try:
            return cls._get_session().post(url, data=data, files=files, timeout=Config.API_TIMEOUT).json()
        except Exception as e:
            logger.exception(f"send_photo_file failed: {e}")
            return None

    @classmethod
    def edit_message_text(cls, chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
        url = f"{Config.BASE_URL}/editMessageText"
        payload = {
            "chat_id": chat_id, "message_id": message_id,
            "text": text, "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            return cls._get_session().post(url, json=payload, timeout=Config.API_TIMEOUT).json()
        except Exception as e:
            logger.exception(f"edit_message_text failed: {e}")
            return None

    @classmethod
    def edit_message_caption(cls, chat_id, message_id, caption, reply_markup=None, parse_mode="HTML"):
        url = f"{Config.BASE_URL}/editMessageCaption"
        payload = {
            "chat_id": chat_id, "message_id": message_id,
            "caption": caption, "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            return cls._get_session().post(url, json=payload, timeout=Config.API_TIMEOUT).json()
        except Exception as e:
            logger.exception(f"edit_message_caption failed: {e}")
            return None

    @classmethod
    def answer_callback_query(cls, callback_query_id, text=""):
        url = f"{Config.BASE_URL}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id, "text": text}
        try:
            return cls._get_session().post(url, json=payload, timeout=(5, 10)).json()
        except Exception as e:
            logger.exception(f"answer_callback_query failed: {e}")
            return None

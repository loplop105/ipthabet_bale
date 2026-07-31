"""
هندلرهای مدیریتی
"""
import logging
from config import Config
from bale_api import BaleAPI
from database import create_discount_code, get_order, update_order_status
from pasarguard import create_pasarguard_user
from utils.qr import generate_qr_code
from utils.markdown import escape_md
from handlers.menu import after_approval_keyboard

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """بررسی احراز هویت ادمین"""
    return user_id == Config.ADMIN_CHAT_ID


def handle_addcode(chat_id: int, text: str):
    """ساخت کد تخفیف - فقط ادمین"""
    parts = text.split()
    if len(parts) >= 3:
        code = parts[1].upper()
        try:
            value = int(parts[2])
        except ValueError:
            BaleAPI.send_message(chat_id, "❌ مقدار تخفیف باید عدد باشد.")
            return
        disc_type = parts[3] if len(parts) > 3 and parts[3] in ['percent', 'fixed'] else 'percent'
        max_uses = int(parts[4]) if len(parts) > 4 else 1

        success = create_discount_code(code, value, disc_type, max_uses)
        if success:
            BaleAPI.send_message(
                chat_id,
                f"✅ کد تخفیف <code>{code}</code> ساخته شد.\n"
                f"نوع: {disc_type} | مقدار: {value} | ظرفیت: {max_uses}"
            )
        else:
            BaleAPI.send_message(chat_id, "⚠️ این کد قبلاً ثبت شده است.")
    else:
        BaleAPI.send_message(
            chat_id,
            "❌ فرمت صحیح:\n/addcode CODE VALUE [percent/fixed] [max_uses]\nمثال: /addcode OFF20 20 percent 10"
        )


def handle_admin_approve(chat_id: int, message_id: int, order_id: int, cb_user_id: int, cb_id: str = ""):
    """تایید سفارش - فقط ادمین"""
    # ─── احراز هویت ───
    if not is_admin(cb_user_id):
        if cb_id:
            BaleAPI.answer_callback_query(cb_id, "⛔ دسترسی غیرمجاز", show_alert=True)
        logger.warning(f"Unauthorized admin_approve attempt by user {cb_user_id}")
        return

    order = get_order(order_id)
    if not order:
        BaleAPI.send_message(chat_id, "❌ سفارش یافت نشد.")
        return
    if order['status'] == 'completed':
        BaleAPI.send_message(chat_id, "⚠️ این سفارش قبلاً تایید شده است.")
        return

    # ساخت کاربر در پنل
    sub_url, error, pg_username = create_pasarguard_user(
        volume_gb=order['volume_gb'], days=60, prefix="usr"
    )

    if sub_url:
        update_order_status(order_id, "completed", config_code=sub_url, pg_username=pg_username)

        category_display = Config.CATEGORY_NAMES.get(order['category'], order['category'])
        user_msg = (
            f"🎉 **پرداخت شما تایید شد!**\n\n"
            f"📂 دسته‌بندی: **{escape_md(category_display)}**\n"
            f"📊 حجم: **{order['volume_gb']} گیگابایت**\n\n"
            f"🔗 **لینک اشتراک اختصاصی شما:**\n"
            f"[🔌 اتصال به سرویس]({sub_url})\n\n"
            f"📊 **[مدیریت و مشاهده حجم]({sub_url})**\n\n"
            f"📱 *برای اتصال سریع‌تر، QR Code زیر را اسکن کنید:*"
        )

        qr_img = generate_qr_code(sub_url)
        BaleAPI.send_photo_file(
            order['user_id'], qr_img, caption=user_msg,
            reply_markup=after_approval_keyboard(), parse_mode="Markdown"
        )

        status_text = f"✅ سفارش شماره {order_id} تایید و در پنل ساخته شد.\n🏷 Username: <code>{pg_username}</code>"
        res = BaleAPI.edit_message_caption(chat_id, message_id, status_text)
        if not res or not res.get("ok"):
            BaleAPI.edit_message_text(chat_id, message_id, status_text)
    else:
        BaleAPI.send_message(chat_id, f"❌ خطا در ساخت کاربر:\n<code>{escape_md(error)}</code>")


def handle_admin_reject(chat_id: int, message_id: int, order_id: int, cb_user_id: int, cb_id: str = ""):
    """رد سفارش - فقط ادمین"""
    if not is_admin(cb_user_id):
        if cb_id:
            BaleAPI.answer_callback_query(cb_id, "⛔ دسترسی غیرمجاز", show_alert=True)
        logger.warning(f"Unauthorized admin_reject attempt by user {cb_user_id}")
        return

    order = get_order(order_id)
    if order and order['status'] == 'pending':
        update_order_status(order_id, "rejected")
        BaleAPI.send_message(order['user_id'], "❌ سفارش شما توسط مدیریت رد شد.")
        status_text = f"❌ سفارش شماره {order_id} رد شد."
        res = BaleAPI.edit_message_caption(chat_id, message_id, status_text)
        if not res or not res.get("ok"):
            BaleAPI.edit_message_text(chat_id, message_id, status_text)

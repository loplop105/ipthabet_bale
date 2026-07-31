"""
هندلرهای پرداخت و کد تخفیف
"""
import logging
from config import Config
from bale_api import BaleAPI
from database import (
    apply_discount_code, get_order, set_user_state,
    clear_user_state, has_pending_order, create_order
)
from utils.markdown import escape_md
from handlers.menu import payment_methods_keyboard, back_button_keyboard

logger = logging.getLogger(__name__)


def handle_discount_input(user_id: int, chat_id: int, text: str, data: dict):
    """پردازش کد تخفیف ورودی"""
    order_id = data.get('order_id')
    clear_user_state(user_id)

    if not text or not text.strip():
        BaleAPI.send_message(chat_id, "⚠️ لطفاً کد تخفیف را ارسال کنید.")
        return

    code = text.strip().upper()
    result = apply_discount_code(code, order_id)

    if result["success"]:
        order = result["order"]
        category_display = Config.CATEGORY_NAMES.get(order['category'], order['category'])
        invoice_text = (
            f"🧾 <b>پیش‌فاکتور بروزرسانی شد</b>\n\n"
            f"📂 دسته‌بندی: <b>{escape_md(category_display)}</b>\n"
            f"📊 حجم: <b>{order['volume_gb']} گیگابایت</b>\n"
            f"🎟 کد تخفیف: <b>{escape_md(code)}</b>\n"
            f"💸 تخفیف: <b>{result['discount_amount']:,} تومان</b>\n"
            f"💰 مبلغ نهایی: <b>{result['new_amount']:,} تومان</b>\n\n"
            "لطفاً روش پرداخت را انتخاب کنید:"
        )
        BaleAPI.send_message(chat_id, invoice_text, payment_methods_keyboard(order_id))
    else:
        BaleAPI.send_message(chat_id, f"❌ {result['error']}")


def handle_receipt(user_id: int, chat_id: int, msg: dict, data: dict):
    """پردازش فیش واریزی"""
    order_id = data.get('order_id')
    clear_user_state(user_id)

    BaleAPI.send_message(
        chat_id,
        "✅ فیش واریز شما ثبت شد.\nپس از بررسی مدیریت، لینک اشتراک ارسال خواهد شد."
    )

    order = get_order(order_id)
    if not order:
        return

    username = msg.get('from', {}).get('username', 'ندارد')
    user_caption = msg.get('caption', msg.get('text', '')) or "بدون توضیح"
    cat_display = Config.CATEGORY_NAMES.get(order['category'], order['category'])

    admin_text = (
        f"🔔 <b>سفارش جدید نیاز به تایید دارد</b>\n\n"
        f"👤 کاربر: {user_id} (@{escape_md(username)})\n"
        f"🔢 کد سفارش: {order_id}\n"
        f"📂 دسته‌بندی: <b>{escape_md(cat_display)}</b>\n"
        f"📊 حجم: <b>{order['volume_gb']} گیگابایت</b>\n"
        f"💰 مبلغ: <b>{order['amount']:,} تومان</b>\n"
        f"📝 توضیحات: {escape_md(user_caption)}"
    )

    from handlers.menu import admin_order_keyboard

    if 'photo' in msg and msg['photo']:
        photo_file_id = msg['photo'][-1]['file_id']
        BaleAPI.send_photo(
            Config.ADMIN_CHAT_ID, photo_file_id,
            caption=admin_text, reply_markup=admin_order_keyboard(order_id)
        )
    else:
        BaleAPI.send_message(
            Config.ADMIN_CHAT_ID, admin_text,
            reply_markup=admin_order_keyboard(order_id)
        )

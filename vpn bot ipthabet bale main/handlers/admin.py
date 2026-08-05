"""
هندلرهای مدیریتی
"""
import logging
from config import Config
from bale_api import BaleAPI
from database import (
    create_discount_code, get_order, update_order_status,
    create_subscription, extend_subscription, get_admin_stats,
    get_pending_orders, log_admin_action
)
from pasarguard import create_pasarguard_user, update_user_expiry, add_user_volume
from utils.qr import generate_qr_code
from utils.markdown import escape_md
from handlers.menu import after_approval_keyboard

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """بررسی احراز هویت ادمین"""
    return user_id in Config.ADMIN_CHAT_IDS


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


def handle_admin_stats(chat_id: int):
    """نمایش آمار فروش و کاربران"""
    stats = get_admin_stats()
    text = (
        f"📊 <b>داشبورد مدیریت</b>\n\n"
        f"👥 کل کاربران: <b>{stats['total_users']}</b>\n"
        f"🛒 فروش موفق: <b>{stats['total_sales']}</b>\n"
        f"💵 درآمد کل: <b>{stats['total_revenue']:,} تومان</b>\n"
        f"💰 درآمد امروز: <b>{stats['today_revenue']:,} تومان</b>\n"
        f"📈 درآمد ۷ روز اخیر: <b>{stats['week_revenue']:,} تومان</b>\n"
        f"⏳ سفارشات در انتظار: <b>{stats['pending_orders']}</b>\n"
        f"✅ اشتراک‌های فعال: <b>{stats['active_subscriptions']}</b>"
    )
    BaleAPI.send_message(chat_id, text)


def handle_admin_pending(chat_id: int):
    """لیست سفارشات در انتظار تایید"""
    orders = get_pending_orders(limit=10)
    if not orders:
        BaleAPI.send_message(chat_id, "✅ هیچ سفارش در انتظاری نیست.")
        return

    text = f"📋 <b>سفارشات در انتظار تایید:</b> ({len(orders)})\n\n"
    for o in orders:
        cat = Config.CATEGORY_NAMES.get(o['category'], o['category'])
        username = o['username'] or o['user_id']
        text += (
            f"#{o['id']} | <b>{escape_md(username)}</b>\n"
            f"   {cat} | {o['volume_gb']} گیگ | {o['amount']:,} ت\n\n"
        )
    BaleAPI.send_message(chat_id, text)


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

    order_type_val = dict(order).get('order_type', 'new')
    is_renewal = order['renewal_of'] is not None and order['renewal_of'] > 0

    if order_type_val == 'add_volume':
        # ═══ افزایش حجم اشتراک ═══
        from database import get_subscription_by_id, extend_subscription_volume
        sub = get_subscription_by_id(order['renewal_of'])
        if not sub:
            BaleAPI.send_message(chat_id, "❌ اشتراک برای افزایش حجم یافت نشد.")
            return

        # افزایش حجم در دیتابیس
        vol_updated = extend_subscription_volume(order['renewal_of'], order['volume_gb'])
        if not vol_updated:
            BaleAPI.send_message(chat_id, "❌ خطا در افزایش حجم اشتراک.")
            return

        # افزایش حجم در پنل
        if sub['pg_username']:
            add_user_volume(sub['pg_username'], order['volume_gb'])

        update_order_status(order_id, "completed")

        # اطلاع به کاربر
        cat_display = Config.CATEGORY_NAMES.get(order['category'], order['category'])
        user_msg = (
            f"📈 <b>حجم اشتراک شما افزایش یافت!</b>\n\n"
            f"📂 دسته‌بندی: <b>{escape_md(cat_display)}</b>\n"
            f"➕ حجم اضافه: <b>{order['volume_gb']} گیگابایت</b>\n"
            f"📊 حجم جدید: <b>{sub['volume_gb'] + order['volume_gb']} گیگابایت</b>\n\n"
            f"🎉 از پروفایل خود می‌توانید وضعیت اشتراک را ببینید."
        )
        BaleAPI.send_message(
            order['user_id'], user_msg,
            after_approval_keyboard()
        )

        # پاسخ به ادمین
        status_text = f"✅ سفارش #{order_id} تایید و حجم اشتراک افزایش یافت."
        log_admin_action(cb_user_id, "add_volume_approve", f"order={order_id}, user={order['user_id']}")
        res = BaleAPI.edit_message_caption(chat_id, message_id, status_text)
        if not res or not res.get("ok"):
            BaleAPI.edit_message_text(chat_id, message_id, status_text)

    elif is_renewal:
        # ═══ تمدید اشتراک موجود ═══
        sub_updated = extend_subscription(order['renewal_of'], Config.DEFAULT_SUBSCRIPTION_DAYS)
        if not sub_updated:
            BaleAPI.send_message(chat_id, "❌ اشتراک برای تمدید یافت نشد.")
            return

        # تلاش برای تمدید در پنل (در صورت موجود بودن pg_username)
        from database import get_subscription_by_id
        sub = get_subscription_by_id(order['renewal_of'])
        if sub and sub['pg_username']:
            update_user_expiry(sub['pg_username'], Config.DEFAULT_SUBSCRIPTION_DAYS)

        update_order_status(order_id, "completed")

        # اطلاع به کاربر
        cat_display = Config.CATEGORY_NAMES.get(order['category'], order['category'])
        user_msg = (
            f"✅ <b>اشتراک شما تمدید شد!</b>\n\n"
            f"📂 دسته‌بندی: <b>{escape_md(cat_display)}</b>\n"
            f"📊 حجم: <b>{order['volume_gb']} گیگابایت</b>\n"
            f"⏱ مدت: <b>{Config.DEFAULT_SUBSCRIPTION_DAYS} روز</b>\n\n"
            f"🎉 از پروفایل خود می‌توانید وضعیت اشتراک را ببینید."
        )
        BaleAPI.send_message(
            order['user_id'], user_msg,
            after_approval_keyboard()
        )

        # پاسخ به ادمین
        status_text = f"✅ سفارش #{order_id} تایید و اشتراک تمدید شد."
        log_admin_action(cb_user_id, "renew_approve", f"order={order_id}, user={order['user_id']}")
        res = BaleAPI.edit_message_caption(chat_id, message_id, status_text)
        if not res or not res.get("ok"):
            BaleAPI.edit_message_text(chat_id, message_id, status_text)

    else:
        # ═══ خرید جدید ═══
        # ساخت کاربر در پنل
        sub_url, error, pg_username = create_pasarguard_user(
            volume_gb=order['volume_gb'], days=Config.DEFAULT_SUBSCRIPTION_DAYS, prefix="usr"
        )

        if sub_url:
            update_order_status(order_id, "completed", config_code=sub_url, pg_username=pg_username)
            # ثبت اشتراک در دیتابیس
            create_subscription(
                user_id=order['user_id'],
                order_id=order_id,
                category=order['category'],
                volume_gb=order['volume_gb'],
                pg_username=pg_username,
                config_code=sub_url,
                days=Config.DEFAULT_SUBSCRIPTION_DAYS
            )

            category_display = Config.CATEGORY_NAMES.get(order['category'], order['category'])
            user_msg = (
                f"🎉 **پرداخت شما تایید شد!**\n\n"
                f"📂 دسته‌بندی: **{escape_md(category_display)}**\n"
                f"📊 حجم: **{order['volume_gb']} گیگابایت**\n"
                f"⏱ مدت: **{Config.DEFAULT_SUBSCRIPTION_DAYS} روزه**\n\n"
                f"🔗 [🔌 اتصال به سرویس]({sub_url})\n"
                f"📊 [مدیریت و مشاهده حجم]({sub_url})\n\n"
                f"📱 *QR Code زیر را اسکن کنید:*"
            )

            qr_img = generate_qr_code(sub_url)
            BaleAPI.send_photo_file(
                order['user_id'], qr_img, caption=user_msg,
                reply_markup=after_approval_keyboard(), parse_mode="Markdown"
            )

            status_text = f"✅ سفارش شماره {order_id} تایید و در پنل ساخته شد.\n🏷 Username: <code>{pg_username}</code>"
            log_admin_action(cb_user_id, "order_approve", f"order={order_id}, user={order['user_id']}")
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
        log_admin_action(cb_user_id, "order_reject", f"order={order_id}")
        res = BaleAPI.edit_message_caption(chat_id, message_id, status_text)
        if not res or not res.get("ok"):
            BaleAPI.edit_message_text(chat_id, message_id, status_text)
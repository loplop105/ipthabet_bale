"""
هندلر پروفایل کاربر
"""
from config import Config
from bale_api import BaleAPI
from database import get_user, get_completed_orders
from utils.markdown import escape_md
from handlers.menu import profile_keyboard


def handle_profile(chat_id: int, message_id: int, user_id: int):
    user = get_user(user_id)
    orders = get_completed_orders(user_id)
    orders_count = len(orders)

    RTL = "\u200f"

    profile_text = (
        f"{RTL}👤 **حساب کاربری شما**\n\n"
        f"{RTL}🆔 شناسه: `{user_id}`\n"
        f"{RTL}🛒 خریدهای موفق: **{orders_count}**\n"
        f"{RTL}👥 زیرمجموعه‌ها: **{user['referral_count'] if user else 0}**\n"
        f"{RTL}📅 عضویت: **{user['created_at'][:10] if user and user['created_at'] else 'نامشخص'}**\n"
    )

    if orders:
        profile_text += f"\n━━━━━━━━━━━━━━━\n{RTL}🎁 **سرویس‌های فعال:**\n"
        for idx, order in enumerate(orders, 1):
            cat = Config.CATEGORY_NAMES.get(order['category'], order['category'])
            date_str = order['created_at'][:10] if order['created_at'] else "—"
            pg_user = order['pg_username'] or f"usr_{user_id}_{order['id']}"

            profile_text += f"\n{RTL}🛍️ **خرید شماره {idx}**\n\n"
            profile_text += f"{RTL}📂 دسته‌بندی: {cat} | 📊 حجم: {order['volume_gb']} گیگ\n"
            profile_text += f"{RTL}📅 تاریخ خرید: {date_str}\n"
            profile_text += f"{RTL}🏷️ نام کانفیگ: `{pg_user}`\n\n"
            if order['config_code']:
                profile_text += f"{RTL}🔗 [🔌 اتصال به سرویس]({order['config_code']})\n"
                profile_text += f"{RTL}📊 [مدیریت و مشاهده حجم]({order['config_code']})\n"
    else:
        profile_text += f"\n{RTL}💡 هنوز خریدی ثبت نکرده‌اید."

    # جلوگیری از پیام خیلی بلند
    if len(profile_text) > 4000:
        profile_text = (
            f"{RTL}👤 **حساب کاربری**\n\n"
            f"{RTL}🆔 `{user_id}`\n"
            f"{RTL}🛒 خریدها: **{orders_count}**\n\n"
            f"{RTL}⚠️ برای دریافت لینک‌ها به پشتیبانی پیام دهید."
        )

    BaleAPI.edit_message_text(chat_id, message_id, profile_text, profile_keyboard(), parse_mode="Markdown")

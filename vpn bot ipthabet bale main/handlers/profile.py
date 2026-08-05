"""
هندلر پروفایل کاربر - با نمایش اشتراک فعال و تاریخ انقضا
"""
from datetime import datetime
from config import Config
from bale_api import BaleAPI
from database import get_user, get_active_subscriptions, get_all_subscriptions, get_latest_subscription
from utils.markdown import escape_md
from handlers.menu import profile_keyboard, renew_keyboard


def _format_date(date_str: str) -> str:
    """فرمت‌بندی تاریخ خوانا"""
    if not date_str:
        return "—"
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10]


def handle_profile(chat_id: int, message_id: int, user_id: int):
    user = get_user(user_id)
    active_subs = get_active_subscriptions(user_id)
    all_subs = get_all_subscriptions(user_id)

    RTL = "\u200f"

    profile_text = (
        f"{RTL}👤 **حساب کاربری**\n"
        f"{RTL}————————————\n"
        f"{RTL}🆔 شناسه: `{user_id}`\n"
        f"{RTL}👥 زیرمجموعه‌ها: **{user['referral_count'] if user else 0}**\n"
        f"{RTL}📅 عضویت: **{_format_date(user['created_at']) if user else '—'}**\n"
    )

    if active_subs:
        profile_text += f"\n{RTL}━━━━━━━━━━━━━━━━\n{RTL}✅ **اشتراک فعال:**\n"
        for sub in active_subs:
            cat = Config.CATEGORY_NAMES.get(sub['category'], sub['category'])
            expire = _format_date(sub['expire_at'])
            # محاسبه روزهای باقی‌مانده
            try:
                expire_dt = datetime.fromisoformat(sub['expire_at'])
                days_left = (expire_dt - datetime.now()).days
                if days_left <= 3:
                    days_txt = f"⛔️ {days_left} روز مانده!"
                elif days_left <= 7:
                    days_txt = f"⚠️ {days_left} روز مانده"
                else:
                    days_txt = f"{days_left} روز"
            except Exception:
                days_txt = "—"

            profile_text += (
                f"{RTL}\n"
                f"{RTL}📂 {cat} | 📊 {sub['volume_gb']} گیگ\n"
                f"{RTL}⏰ انقضا: **{expire}** ({days_txt})\n"
                f"{RTL}🔗 [🔌 اتصال به سرویس]({sub['config_code']})\n"
                f"{RTL}📊 [مدیریت و مشاهده حجم]({sub['config_code']})\n"
            )
    else:
        profile_text += f"\n{RTL}💡 اشتراک فعالی ندارید."
        if all_subs:
            profile_text += f"\n{RTL}برای تمدید اشتراک قبلی، از دکمه زیر استفاده کنید."

    # جلوگیری از پیام خیلی بلند
    if len(profile_text) > 4000:
        profile_text = (
            f"{RTL}👤 **حساب کاربری**\n\n"
            f"{RTL}🆔 `{user_id}`\n"
            f"{RTL}✅ اشتراک‌های فعال: **{len(active_subs)}**\n\n"
            f"{RTL}⚠️ برای جزئیات بیشتر به پشتیبانی پیام دهید."
        )

    has_sub = len(active_subs) > 0
    BaleAPI.edit_message_text(chat_id, message_id, profile_text, profile_keyboard(has_subscription=has_sub), parse_mode="Markdown")


def handle_renew(chat_id: int, message_id: int, user_id: int):
    """نمایش گزینه تمدید اشتراک"""
    sub = get_latest_subscription(user_id)
    if not sub:
        BaleAPI.edit_message_text(
            chat_id, message_id,
            "❌ اشتراکی برای تمدید یافت نشد.\nابتدا یک اشتراک خریداری کنید.",
            profile_keyboard(has_subscription=False)
        )
        return

    cat = Config.CATEGORY_NAMES.get(sub['category'], sub['category'])
    price = Config.get_price_per_gb(sub['category'], Config.PRICE_PER_GB)
    renew_amount = sub['volume_gb'] * price

    text = (
        f"🔄 <b>تمدید اشتراک</b>\n\n"
        f"📂 دسته‌بندی: <b>{escape_md(cat)}</b>\n"
        f"📊 حجم: <b>{sub['volume_gb']} گیگابایت</b>\n"
        f"💰 هزینه تمدید {Config.DEFAULT_SUBSCRIPTION_DAYS} روزه: <b>{renew_amount:,} تومان</b>\n\n"
        "پس از تایید، زمان اشتراک شما تمدید خواهد شد."
    )
    BaleAPI.edit_message_text(chat_id, message_id, text, renew_keyboard(sub['id']))


def handle_renew_confirm(chat_id: int, message_id: int, user_id: int, subscription_id: int):
    """ایجاد سفارش تمدید - کاربر فیش می‌فرستد و ادمین تایید می‌کند"""
    from database import create_order, get_latest_subscription
    sub = get_latest_subscription(user_id)
    if not sub or sub['id'] != subscription_id:
        BaleAPI.edit_message_text(
            chat_id, message_id,
            "❌ اشتراک یافت نشد. لطفاً دوباره تلاش کنید.",
            back_to_profile_keyboard()
        )
        return

    price = Config.get_price_per_gb(sub['category'], Config.PRICE_PER_GB)
    renew_amount = sub['volume_gb'] * price
    order_id = create_order(user_id, sub['category'], sub['volume_gb'], renew_amount, renewal_of=subscription_id)

    from handlers.menu import payment_methods_keyboard
    text = (
        f"🧾 <b>پیش‌فاکتور تمدید</b>\n\n"
        f"📂 دسته‌بندی: <b>{escape_md(Config.CATEGORY_NAMES.get(sub['category'], sub['category']))}</b>\n"
        f"📊 حجم: <b>{sub['volume_gb']} گیگابایت</b>\n"
        f"⏱ مدت: <b>{Config.DEFAULT_SUBSCRIPTION_DAYS} روزه</b>\n"
        f"💰 مبلغ: <b>{renew_amount:,} تومان</b>\n\n"
        "روش پرداخت را انتخاب کنید:"
    )
    BaleAPI.edit_message_text(chat_id, message_id, text, payment_methods_keyboard(order_id))


def handle_add_volume(chat_id: int, message_id: int, user_id: int):
    """نمایش گزینه‌های افزایش حجم"""
    from database import get_latest_subscription
    from handlers.menu import add_volume_keyboard

    sub = get_latest_subscription(user_id)
    if not sub:
        BaleAPI.edit_message_text(
            chat_id, message_id,
            "❌ اشتراک فعالی برای افزایش حجم یافت نشد.\nابتدا یک اشتراک خریداری کنید.",
            profile_keyboard(has_subscription=False)
        )
        return

    cat = Config.CATEGORY_NAMES.get(sub['category'], sub['category'])
    price = Config.get_price_per_gb(sub['category'], Config.PRICE_PER_GB)

    text = (
        f"📈 <b>افزایش حجم اشتراک</b>\n\n"
        f"📂 دسته‌بندی: <b>{escape_md(cat)}</b>\n"
        f"📊 حجم فعلی: <b>{sub['volume_gb']} گیگابایت</b>\n"
        f"💰 نرخ: <b>{price:,} تومان/گیگ</b>\n\n"
        "مقدار حجم اضافه را انتخاب کنید:"
    )
    BaleAPI.edit_message_text(chat_id, message_id, text, add_volume_keyboard(sub['id']))


def handle_add_volume_custom(chat_id: int, message_id: int, user_id: int, subscription_id: int):
    """مرحله اول: دریافت حجم دلخواه (عدد)"""
    from database import get_subscription_by_id
    from handlers.menu import back_button_keyboard

    sub = get_subscription_by_id(subscription_id)
    if not sub:
        BaleAPI.edit_message_text(
            chat_id, message_id,
            "❌ اشتراک یافت نشد.",
            back_button_keyboard("menu_profile")
        )
        return

    price = Config.get_price_per_gb(sub['category'], Config.PRICE_PER_GB)
    set_user_state(user_id, "AWAITING_ADD_VOLUME", {"subscription_id": subscription_id})

    text = (
        f"✏️ <b>افزایش حجم دلخواه</b>\n\n"
        f"📂 دسته‌بندی: <b>{escape_md(Config.CATEGORY_NAMES.get(sub['category'], sub['category']))}</b>\n"
        f"📊 حجم فعلی: <b>{sub['volume_gb']} گیگابایت</b>\n"
        f"💰 نرخ: <b>{price:,} تومان/گیگ</b>\n"
        f"📏 محدوده: <b>{Config.MIN_VOLUME_GB} تا {Config.MAX_VOLUME_GB} گیگ</b>\n\n"
        "مقدار حجم اضافه (عدد) را ارسال کنید:"
    )
    BaleAPI.edit_message_text(chat_id, message_id, text, back_button_keyboard("menu_profile"))


def handle_add_volume_confirm(chat_id: int, message_id: int, user_id: int, subscription_id: int, volume: int):
    """مرحله دوم: تایید نهایی و ایجاد سفارش افزایش حجم"""
    from database import get_subscription_by_id, create_order
    from handlers.menu import confirm_volume_keyboard, payment_methods_keyboard

    sub = get_subscription_by_id(subscription_id)
    if not sub:
        BaleAPI.edit_message_text(
            chat_id, message_id,
            "❌ اشتراک یافت نشد.",
            back_to_profile_keyboard()
        )
        return

    price = Config.get_price_per_gb(sub['category'], Config.PRICE_PER_GB)
    amount = volume * price

    # نمایش تایید نهایی (دو مرحله‌ای)
    text = (
        f"🧾 <b>تایید افزایش حجم</b>\n\n"
        f"📂 دسته‌بندی: <b>{escape_md(Config.CATEGORY_NAMES.get(sub['category'], sub['category']))}</b>\n"
        f"📊 حجم فعلی: <b>{sub['volume_gb']} گیگابایت</b>\n"
        f"➕ حجم اضافه: <b>{volume} گیگابایت</b>\n"
        f"📊 حجم نهایی: <b>{sub['volume_gb'] + volume} گیگابایت</b>\n"
        f"💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
        "آیا تایید می‌کنید؟"
    )
    BaleAPI.edit_message_text(chat_id, message_id, text, confirm_volume_keyboard(subscription_id, volume))


def handle_add_volume_final(chat_id: int, message_id: int, user_id: int, subscription_id: int, volume: int):
    """ایجاد سفارش نهایی افزایش حجم"""
    from database import get_subscription_by_id, create_order
    from handlers.menu import payment_methods_keyboard

    sub = get_subscription_by_id(subscription_id)
    if not sub:
        BaleAPI.edit_message_text(
            chat_id, message_id,
            "❌ اشتراک یافت نشد.",
            back_to_profile_keyboard()
        )
        return

    price = Config.get_price_per_gb(sub['category'], Config.PRICE_PER_GB)
    amount = volume * price
    order_id = create_order(
        user_id, sub['category'], volume, amount,
        renewal_of=subscription_id, order_type='add_volume'
    )

    text = (
        f"🧾 <b>پیش‌فاکتور افزایش حجم</b>\n\n"
        f"📂 دسته‌بندی: <b>{escape_md(Config.CATEGORY_NAMES.get(sub['category'], sub['category']))}</b>\n"
        f"➕ حجم اضافه: <b>{volume} گیگابایت</b>\n"
        f"💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
        "روش پرداخت را انتخاب کنید:"
    )
    BaleAPI.edit_message_text(chat_id, message_id, text, payment_methods_keyboard(order_id))


def back_to_profile_keyboard():
    from handlers.menu import back_button_keyboard
    return back_button_keyboard("menu_profile")

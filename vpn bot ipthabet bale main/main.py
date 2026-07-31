"""
ربات فروش اشتراک VPN - نسخه بهینه‌شده
"""
import time
import logging
from config import Config
from database import (
    init_db, register_user, get_user_state, set_user_state,
    clear_user_state, has_pending_order, create_order, get_user,
    check_rate_limit, backup_database, get_pending_order, cancel_pending_order
)
from bale_api import BaleAPI
from pasarguard import create_pasarguard_user
from utils.qr import generate_qr_code
from utils.markdown import escape_md
from utils.rate_limiter import rate_limiter
from utils.backup import start_backup_scheduler
from monitors.health_check import start_health_monitor
from handlers.menu import (
    main_menu_keyboard, categories_keyboard, volumes_keyboard,
    payment_methods_keyboard, guides_keyboard, guide_download_keyboard,
    after_approval_keyboard, back_button_keyboard, pending_order_keyboard
)
from handlers.admin import handle_addcode, handle_admin_approve, handle_admin_reject, is_admin
from handlers.payment import handle_discount_input, handle_receipt
from handlers.profile import handle_profile

# ─── Logging Setup ───
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# پردازش پیام‌های متنی
# ═══════════════════════════════════════════

def handle_text_message(msg: dict):
    chat_id = msg['chat']['id']
    text = msg.get('text', '')
    user_id = msg['from']['id']
    username = msg['from'].get('username', 'ندارد')

    # ─── Rate Limit ───
    if not rate_limiter.is_allowed(user_id):
        BaleAPI.send_message(chat_id, "⏳ لطفاً کمی صبر کنید و دوباره تلاش کنید.")
        return

    # ─── ثبت کاربر + پردازش Referral ───
    referred_by = None
    if text and '/start' in text and 'ref_' in text:
        try:
            ref_id = int(text.split('ref_')[1].split()[0])
            if ref_id != user_id:
                referred_by = ref_id
        except (ValueError, IndexError):
            pass

    register_user(user_id, username, referred_by)
    state, data = get_user_state(user_id)

    # ─── دستور ساخت کد تخفیف (فقط ادمین) ───
    if user_id == Config.ADMIN_CHAT_ID and text.startswith('/addcode'):
        handle_addcode(chat_id, text)
        return

    # ─── /start ───
    if text and text.startswith('/start'):
        clear_user_state(user_id)
        welcome = (
            f"سلام {escape_md(msg['from'].get('first_name', ''))} عزیز! 👋\n\n"
            "به ربات فروش اشتراک خوش آمدید.\n"
            "لطفاً از دکمه‌های زیر استفاده کنید:"
        )
        if referred_by:
            welcome += "\n\n🎉 شما از طریق لینک زیرمجموعه وارد شدید!"
        BaleAPI.send_message(chat_id, welcome, main_menu_keyboard())
        return

    # ─── حجم دلخواه ───
    if state == "AWAITING_CUSTOM_VOLUME":
        if text and text.isdigit():
            volume = int(text)
            # ─── Validation ───
            if volume < Config.MIN_VOLUME_GB or volume > Config.MAX_VOLUME_GB:
                BaleAPI.send_message(
                    chat_id,
                    f"⚠️ حجم باید بین {Config.MIN_VOLUME_GB} تا {Config.MAX_VOLUME_GB} گیگابایت باشد."
                )
                return

            category = data.get('category')
            category_display = Config.CATEGORY_NAMES.get(category, category)
            amount = volume * Config.PRICE_PER_GB

            # ─── جلوگیری از سفارش تکراری ───
            if has_pending_order(user_id):
                pending = get_pending_order(user_id)
                if pending:
                    cat_name = Config.CATEGORY_NAMES.get(pending['category'], pending['category'])
                    pending_text = (
                        f"⚠️ <b>شما یک سفارش معلق دارید!</b>\n\n"
                        f"📂 دسته‌بندی: <b>{escape_md(cat_name)}</b>\n"
                        f"📊 حجم: <b>{pending['volume_gb']} گیگابایت</b>\n"
                        f"💰 مبلغ: <b>{pending['amount']:,} تومان</b>\n\n"
                        "آیا مایل به لغو سفارش قبلی و ادامه خرید جدید هستید؟"
                    )
                    set_user_state(user_id, "AWAITING_CANCEL_AND_CONTINUE", {
                        "category": category, "volume": volume,
                        "amount": amount, "pending_id": pending['id']
                    })
                    BaleAPI.send_message(chat_id, pending_text, pending_order_keyboard(pending['id']))
                else:
                    BaleAPI.send_message(chat_id, "⚠️ شما یک سفارش در انتظار دارید.", pending_order_keyboard(0))
                return

            order_id = create_order(user_id, category, volume, amount)
            clear_user_state(user_id)

            invoice_text = (
                f"🧾 <b>پیش‌فاکتور خرید اشتراک</b>\n\n"
                f"📂 دسته‌بندی: <b>{escape_md(category_display)}</b>\n"
                f"📊 حجم: <b>{volume} گیگابایت</b>\n"
                f"⏱ مدت: <b>۶۰ روزه</b>\n"
                f"💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
                "روش پرداخت را انتخاب کنید:"
            )
            BaleAPI.send_message(chat_id, invoice_text, payment_methods_keyboard(order_id))
        else:
            BaleAPI.send_message(chat_id, "⚠️ لطفاً فقط یک عدد معتبر وارد کنید:")
        return

    # ─── کد تخفیف ───
    if state == "AWAITING_DISCOUNT_CODE":
        handle_discount_input(user_id, chat_id, text, data)
        return

    # ─── فیش واریز ───
    if state == "AWAITING_RECEIPT":
        handle_receipt(user_id, chat_id, msg, data)
        return

    BaleAPI.send_message(chat_id, "لطفاً از دکمه‌های منو استفاده کنید:", main_menu_keyboard())


# ═══════════════════════════════════════════
# پردازش Callback Query
# ═══════════════════════════════════════════

def handle_callback_query(cb: dict):
    cb_id = cb['id']
    chat_id = cb['message']['chat']['id']
    message_id = cb['message']['message_id']
    data = cb['data']
    user_id = cb['from']['id']

    # ─── Rate Limit ───
    if not rate_limiter.is_allowed(user_id):
        BaleAPI.answer_callback_query(cb_id, "⏳ کمی صبر کنید...")
        return

    BaleAPI.answer_callback_query(cb_id)

    # ─── منوی اصلی ───
    if data == "menu_main":
        clear_user_state(user_id)
        BaleAPI.edit_message_text(chat_id, message_id, "🤖 منوی اصلی ربات:", main_menu_keyboard())

    # ─── هدیه رایگان ───
    elif data == "menu_gift":
        user = get_user(user_id)
        if user and user['has_claimed_gift'] == 1:
            BaleAPI.edit_message_text(chat_id, message_id, "⚠️ شما قبلاً هدیه خود را دریافت کرده‌اید!", back_button_keyboard())
        else:
            BaleAPI.edit_message_text(chat_id, message_id, "⏳ در حال ساخت سرویس هدیه...")
            sub_url, error, pg_username = create_pasarguard_user(volume_gb=0.25, days=7, prefix="gift")

            if sub_url:
                from database import db_transaction
                with db_transaction() as conn:
                    conn.execute('UPDATE users SET has_claimed_gift = 1 WHERE user_id = ?', (user_id,))

                msg_text = (
                    f"🎉 **هدیه رایگان فعال شد!**\n\n"
                    f"📊 حجم: **۲۵۰ مگابایت**\n"
                    f"⏱ مدت: **۷ روزه**\n\n"
                    f"🔗 [🔌 اتصال به سرویس]({sub_url})\n"
                    f"📊 [مدیریت و مشاهده حجم]({sub_url})\n\n"
                    f"📱 *QR Code زیر را اسکن کنید:*"
                )
                qr_img = generate_qr_code(sub_url)
                BaleAPI.send_photo_file(chat_id, qr_img, caption=msg_text, reply_markup=after_approval_keyboard(), parse_mode="Markdown")
                BaleAPI.edit_message_text(chat_id, message_id, "✅ سرویس هدیه در پیام جدید ارسال شد.", back_button_keyboard())
            else:
                BaleAPI.edit_message_text(chat_id, message_id, f"❌ خطا:\n`{escape_md(error)}`", back_button_keyboard(), parse_mode="Markdown")

    # ─── خرید ───
    elif data == "menu_buy":
        BaleAPI.edit_message_text(chat_id, message_id, "📁 دسته‌بندی مورد نظر را انتخاب کنید:", categories_keyboard())

    elif data.startswith("cat_"):
        category = data.split("_")[1]
        category_display = Config.CATEGORY_NAMES.get(category, category)
        text = (
            f"📊 دسته‌بندی: <b>{escape_md(category_display)}</b>\n"
            "⏱ تمامی پلن‌ها <b>۶۰ روزه</b> هستند.\n\n"
            "حجم مورد نظر را انتخاب کنید:"
        )
        BaleAPI.edit_message_text(chat_id, message_id, text, volumes_keyboard(category))

    elif data.startswith("vol_"):
        parts = data.split("_")
        category, vol_type = parts[1], parts[2]
        category_display = Config.CATEGORY_NAMES.get(category, category)

        if vol_type == "custom":
            set_user_state(user_id, "AWAITING_CUSTOM_VOLUME", {"category": category})
            text = (
                f"✏️ دسته‌بندی: <b>{escape_md(category_display)}</b>\n"
                f"💰 نرخ: <b>{Config.PRICE_PER_GB:,} تومان/گیگ</b>\n"
                f"📏 محدوده: <b>{Config.MIN_VOLUME_GB} تا {Config.MAX_VOLUME_GB} گیگ</b>\n\n"
                "حجم درخواستی (عدد) را ارسال کنید:"
            )
            BaleAPI.edit_message_text(chat_id, message_id, text, back_button_keyboard("menu_buy"))
        else:
            volume = int(vol_type)
            amount = volume * Config.PRICE_PER_GB

            # جلوگیری از سفارش تکراری
            if has_pending_order(user_id):
                pending = get_pending_order(user_id)
                if pending:
                    cat_name = Config.CATEGORY_NAMES.get(pending['category'], pending['category'])
                    pending_text = (
                        f"⚠️ <b>شما یک سفارش معلق دارید!</b>\n\n"
                        f"📂 دسته‌بندی: <b>{escape_md(cat_name)}</b>\n"
                        f"📊 حجم: <b>{pending['volume_gb']} گیگابایت</b>\n"
                        f"💰 مبلغ: <b>{pending['amount']:,} تومان</b>\n\n"
                        "آیا مایل به لغو سفارش قبلی و ادامه خرید جدید هستید؟"
                    )
                    set_user_state(user_id, "AWAITING_CANCEL_AND_CONTINUE", {
                        "category": category, "volume": volume,
                        "amount": amount, "pending_id": pending['id']
                    })
                    BaleAPI.edit_message_text(chat_id, message_id, pending_text, pending_order_keyboard(pending['id']))
                else:
                    BaleAPI.edit_message_text(chat_id, message_id, "⚠️ شما یک سفارش در انتظار دارید.", pending_order_keyboard(0))
                return

            order_id = create_order(user_id, category, volume, amount)
            invoice_text = (
                f"🧾 <b>پیش‌فاکتور خرید</b>\n\n"
                f"📂 دسته‌بندی: <b>{escape_md(category_display)}</b>\n"
                f"📊 حجم: <b>{volume} گیگابایت</b>\n"
                f"⏱ مدت: <b>۶۰ روزه</b>\n"
                f"💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
                "روش پرداخت را انتخاب کنید:"
            )
            BaleAPI.edit_message_text(chat_id, message_id, invoice_text, payment_methods_keyboard(order_id))

    # ─── کد تخفیف ───
    elif data.startswith("apply_discount_"):
        order_id = int(data.split("_")[2])
        set_user_state(user_id, "AWAITING_DISCOUNT_CODE", {"order_id": order_id})
        BaleAPI.edit_message_text(chat_id, message_id, "🎟 کد تخفیف خود را ارسال کنید:", back_button_keyboard("menu_main"))

    # ─── پرداخت کارتی ───
    elif data.startswith("pay_card_"):
        order_id = data.split("_")[2]
        set_user_state(user_id, "AWAITING_RECEIPT", {"order_id": int(order_id)})
        card_text = (
            f"💳 <b>اطلاعات پرداخت</b>\n\n"
            f"شماره کارت:\n<code>{Config.CARD_NUMBER}</code>\n"
            f"به نام: <b>{escape_md(Config.CARD_HOLDER)}</b>\n\n"
            "پس از واریز، <b>عکس فیش یا کد پیگیری</b> را ارسال کنید."
        )
        BaleAPI.edit_message_text(chat_id, message_id, card_text, back_button_keyboard("menu_main"))

    # ─── تایید ادمین ───
    elif data.startswith("admin_approve_"):
        order_id = int(data.split("_")[2])
        handle_admin_approve(chat_id, message_id, order_id, user_id, cb_id)

    # ─── رد ادمین ───
    elif data.startswith("admin_reject_"):
        order_id = int(data.split("_")[2])
        handle_admin_reject(chat_id, message_id, order_id, user_id, cb_id)

    # ─── لغو سفارش معلق و ادامه خرید جدید ───
    elif data.startswith("cancel_pending_"):
        order_id = int(data.split("_")[2])
        state, state_data = get_user_state(user_id)

        pending = get_pending_order(user_id)
        if pending and pending['id'] == order_id:
            cancel_pending_order(user_id)

            if state == "AWAITING_CANCEL_AND_CONTINUE" and state_data:
                category = state_data['category']
                volume = state_data['volume']
                amount = state_data['amount']
                new_order_id = create_order(user_id, category, volume, amount)
                clear_user_state(user_id)

                category_display = Config.CATEGORY_NAMES.get(category, category)
                invoice_text = (
                    f"✅ سفارش قبلی لغو شد.\n\n"
                    f"🧾 <b>پیش‌فاکتور سفارش جدید</b>\n\n"
                    f"📂 دسته‌بندی: <b>{escape_md(category_display)}</b>\n"
                    f"📊 حجم: <b>{volume} گیگابایت</b>\n"
                    f"💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
                    "روش پرداخت را انتخاب کنید:"
                )
                BaleAPI.edit_message_text(chat_id, message_id, invoice_text, payment_methods_keyboard(new_order_id))
            else:
                clear_user_state(user_id)
                BaleAPI.edit_message_text(
                    chat_id, message_id,
                    "✅ سفارش معلق شما لغو شد.\n\nاکنون می‌توانید سفارش جدید ثبت کنید.",
                    categories_keyboard()
                )
        else:
            BaleAPI.edit_message_text(
                chat_id, message_id,
                "⚠️ سفارش معلقی یافت نشد یا قبلاً لغو/تکمیل شده است.",
                back_button_keyboard()
            )

    # ─── پروفایل ───
    elif data == "menu_profile":
        handle_profile(chat_id, message_id, user_id)

    # ─── راهنما ───
    elif data == "menu_help":
        BaleAPI.edit_message_text(chat_id, message_id, "📚 <b>آموزش و راهنما</b>\nسیستم‌عامل را انتخاب کنید:", guides_keyboard())

    elif data.startswith("guide_"):
        g_type = data.split("_")[1]
        guides = {
            "android": "📱 <b>راهنمای اندروید:</b>\n1. برنامه را دانلود و نصب کنید.\n2. لینک ساب‌سکرپشن را وارد نمایید.",
            "ios": "🍎 <b>راهنمای آیفون:</b>\n1. برنامه را از App Store نصب کنید.\n2. لینک اشتراک را اضافه کنید.",
            "pc": "💻 <b>راهنمای ویندوز/مک:</b>\n1. نرم‌افزار را دانلود و استخراج کنید.\n2. لینک ساب را وارد نمایید.",
            "trouble": "🛠 <b>رفع مشکل:</b>\nحالت پرواز را روشن-خاموش کرده و Subscription را بروزرسانی کنید.",
        }
        text = guides.get(g_type, "")
        keyboard = guide_download_keyboard(g_type)
        BaleAPI.edit_message_text(chat_id, message_id, text, keyboard)

    # ─── زیرمجموعه‌گیری ───
    elif data == "menu_referral":
        user = get_user(user_id)
        ref_count = user['referral_count'] if user else 0
        ref_link = f"https://ble.ir/bot?start=ref_{user_id}"
        text = (
            f"👥 <b>سیستم زیرمجموعه‌گیری</b>\n\n"
            f"🔗 لینک اختصاصی شما:\n<code>{ref_link}</code>\n\n"
            f"📊 تعداد زیرمجموعه‌ها: <b>{ref_count}</b>\n\n"
            f"💡 با هر زیرمجموعه جدید، یک کد تخفیف ۱۰٪ دریافت کنید!"
        )
        BaleAPI.edit_message_text(chat_id, message_id, text, back_button_keyboard())

    # ─── پشتیبانی ───
    elif data == "menu_support":
        BaleAPI.edit_message_text(
            chat_id, message_id,
            "🎧 <b>پشتیبانی</b>\n\n"
            "کارشناسان پشتیبانی آماده پاسخگویی به سوالات، بررسی مشکلات و پیگیری درخواست‌های شما هستند.\n\n"
            "⏰ ساعت پاسخگویی: ۹ صبح تا ۹ شب\n\n"
            "📩 @netbama",
            back_button_keyboard()
        )


# ═══════════════════════════════════════════
# اجرا (Long Polling)
# ═══════════════════════════════════════════

def main():
    # ─── اعتبارسنجی تنظیمات ───
    Config.validate()

    # ─── مقداردهی اولیه ───
    init_db()
    backup_database()  # بکاپ اولیه
    start_backup_scheduler()
    start_health_monitor()

    logger.info("🚀 Bot started successfully.")
    offset = 0

    while True:
        try:
            url = f"{Config.BASE_URL}/getUpdates?offset={offset}&timeout=20"
            res = BaleAPI._get_session().get(url, timeout=(5, 30)).json()

            if res.get("ok"):
                for update in res.get("result", []):
                    offset = update["update_id"] + 1
                    try:
                        if "message" in update:
                            handle_text_message(update["message"])
                        elif "callback_query" in update:
                            handle_callback_query(update["callback_query"])
                    except Exception as e:
                        logger.exception(f"Error processing update {update.get('update_id')}: {e}")

        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.exception(f"Error in polling loop: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()

"""
کیبوردها و منوهای ربات - طراحی مدرن و مینیمال
"""
from config import Config


def main_menu_keyboard():
    return {"inline_keyboard": [
        [{"text": "🛒 خرید اشتراک", "callback_data": "menu_buy"}],
        [{"text": "🎁 هدیه رایگان", "callback_data": "menu_gift"},
         {"text": "👤 حساب من", "callback_data": "menu_profile"}],
        [{"text": "👥 زیرمجموعه‌گیری", "callback_data": "menu_referral"},
         {"text": "📚 راهنما", "callback_data": "menu_help"}],
        [{"text": "🎧 پشتیبانی", "callback_data": "menu_support"}],
    ]}


def categories_keyboard():
    # ساخت کیبورد پویا بر اساس دسته‌بندی‌های تعریف‌شده
    cats = list(Config.CATEGORY_NAMES.keys())
    rows = []
    for i in range(0, len(cats), 2):
        row = []
        for cat in cats[i:i+2]:
            price = Config.get_price_per_gb(cat, Config.PRICE_PER_GB)
            row.append({"text": f"{Config.CATEGORY_NAMES[cat]} | {price:,} ت/گیگ", "callback_data": f"cat_{cat}"})
        rows.append(row)
    rows.append([{"text": "🔙", "callback_data": "menu_main"}])
    return {"inline_keyboard": rows}


def volumes_keyboard(category: str):
    price_per_gb = Config.get_price_per_gb(category, Config.PRICE_PER_GB)
    return {"inline_keyboard": [
        [
            {"text": "۵ گیگ", "callback_data": f"vol_{category}_5"},
            {"text": "۱۰ گیگ", "callback_data": f"vol_{category}_10"},
            {"text": "۲۰ گیگ", "callback_data": f"vol_{category}_20"},
        ],
        [
            {"text": "۳۰ گیگ", "callback_data": f"vol_{category}_30"},
            {"text": "۵۰ گیگ", "callback_data": f"vol_{category}_50"},
            {"text": "۱۰۰ گیگ", "callback_data": f"vol_{category}_100"},
        ],
        [{"text": f"✏️ حجم دلخواه ({price_per_gb:,} ت/گیگ)", "callback_data": f"vol_{category}_custom"}],
        [{"text": "🔙 دسته‌بندی‌ها", "callback_data": "menu_buy"},
         {"text": "🏠 منو", "callback_data": "menu_main"}],
    ]}


def payment_methods_keyboard(order_id: int):
    return {"inline_keyboard": [
        [{"text": "🟢 پرداخت کارت به کارت", "callback_data": f"pay_card_{order_id}"}],
        [{"text": "🎟 کد تخفیف دارم", "callback_data": f"apply_discount_{order_id}"}],
        [{"text": "❌ انصراف", "callback_data": "menu_main"}],
    ]}


def admin_order_keyboard(order_id: int):
    return {"inline_keyboard": [
        [{"text": "✅ تایید", "callback_data": f"admin_approve_{order_id}"},
         {"text": "❌ رد", "callback_data": f"admin_reject_{order_id}"}],
    ]}


def guides_keyboard():
    return {"inline_keyboard": [
        [{"text": "📱 اندروید", "callback_data": "guide_android"},
         {"text": "🍎 آیفون", "callback_data": "guide_ios"}],
        [{"text": "💻 ویندوز/مک", "callback_data": "guide_pc"},
         {"text": "🛠 رفع مشکل", "callback_data": "guide_trouble"}],
        [{"text": "🔙", "callback_data": "menu_main"}],
    ]}


def guide_download_keyboard(g_type: str):
    if g_type == "android":
        return {"inline_keyboard": [
            [{"text": "⬇️ v2rayNG", "url": "https://github.com/2dust/v2rayNG/releases"}],
            [{"text": "⬇️ Hiddify", "url": "https://github.com/hiddify/hiddify-app/releases/download/v4.1.1/Hiddify-Android-universal.apk"}],
            [{"text": "🔙", "callback_data": "menu_help"}],
        ]}
    elif g_type == "ios":
        return {"inline_keyboard": [
            [{"text": "⬇️ Hiddify", "url": "https://apps.apple.com/app/hiddify-proxy/id6473774447"}],
            [{"text": "⬇️ NPV Tunnel", "url": "https://apps.apple.com/us/app/npv-tunnel/id1629465476"}],
            [{"text": "🔙", "callback_data": "menu_help"}],
        ]}
    elif g_type == "pc":
        return {"inline_keyboard": [
            [{"text": "⬇️ v2rayN (ویندوز)", "url": "https://github.com/2dust/v2rayN/releases/download/7.24.3/v2rayN-windows-64-desktop.zip"}],
            [{"text": "⬇️ Hiddify (ویندوز)", "url": "https://github.com/hiddify/hiddify-app/releases/download/v4.1.1/Hiddify-Windows-Setup-x64.exe"}],
            [{"text": "🔙", "callback_data": "menu_help"}],
        ]}
    return back_button_keyboard("menu_help")


def after_approval_keyboard():
    return {"inline_keyboard": [
        [{"text": "👤 حساب من", "callback_data": "menu_profile"}],
        [{"text": "🏠 منوی اصلی", "callback_data": "menu_main"}],
    ]}


def profile_keyboard(has_subscription: bool = False):
    rows = []
    if has_subscription:
        rows.append([{"text": "🔄 تمدید اشتراک", "callback_data": "sub_renew"}])
        rows.append([{"text": "📈 افزایش حجم", "callback_data": "sub_add_volume"}])
    rows.append([{"text": "🛒 خرید جدید", "callback_data": "menu_buy"}])
    rows.append([{"text": "🔙", "callback_data": "menu_main"}])
    return {"inline_keyboard": rows}


def pending_order_keyboard(order_id: int):
    return {"inline_keyboard": [
        [{"text": "✅ پرداخت همین سفارش", "callback_data": f"pay_card_{order_id}"}],
        [{"text": "❌ لغو و سفارش جدید", "callback_data": f"pend_cancel_{order_id}"}],
        [{"text": "🏠 منو", "callback_data": "menu_main"}],
    ]}


def back_button_keyboard(target="menu_main"):
    return {"inline_keyboard": [[{"text": "🔙", "callback_data": target}]]}


def renew_keyboard(subscription_id: int):
    """کیبورد تمدید اشتراک"""
    return {"inline_keyboard": [
        [{"text": "🔁 تمدید ۶۰ روزه", "callback_data": f"renew_{subscription_id}"}],
        [{"text": "🏠 منوی اصلی", "callback_data": "menu_main"}],
    ]}


def add_volume_keyboard(subscription_id: int):
    """کیبورد افزایش حجم"""
    return {"inline_keyboard": [
        [{"text": "➕ ۵ گیگ", "callback_data": f"addvol_{subscription_id}_5"},
         {"text": "➕ ۱۰ گیگ", "callback_data": f"addvol_{subscription_id}_10"}],
        [{"text": "➕ ۲۰ گیگ", "callback_data": f"addvol_{subscription_id}_20"},
         {"text": "➕ ۵۰ گیگ", "callback_data": f"addvol_{subscription_id}_50"}],
        [{"text": "✏️ حجم دلخواه", "callback_data": f"addvol_{subscription_id}_custom"}],
        [{"text": "🔙", "callback_data": "menu_profile"}],
    ]}


def confirm_volume_keyboard(subscription_id: int, volume: int):
    """کیبورد تایید نهایی حجم دلخواه (دو مرحله‌ای)"""
    return {"inline_keyboard": [
        [{"text": "✅ تایید و ادامه", "callback_data": f"addvol_confirm_{subscription_id}_{volume}"}],
        [{"text": "✏️ تغییر حجم", "callback_data": f"addvol_{subscription_id}_custom"}],
        [{"text": "🔙", "callback_data": "menu_profile"}],
    ]}


def confirm_custom_volume_keyboard(volume: int):
    """کیبورد تایید نهایی حجم دلخواه برای خرید جدید (دو مرحله‌ای)"""
    return {"inline_keyboard": [
        [{"text": "✅ تایید و ادامه", "callback_data": f"confirm_custom_vol_{volume}"}],
        [{"text": "✏️ تغییر حجم", "callback_data": "menu_buy"}],
        [{"text": "🔙", "callback_data": "menu_main"}],
    ]}

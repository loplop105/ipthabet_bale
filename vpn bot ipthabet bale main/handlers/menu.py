"""
کیبوردها و منوهای ربات
"""


def main_menu_keyboard():
    return {"inline_keyboard": [
        [{"text": "🎁 هدیه رایگان (۲۵۰ مگ - ۷ روزه)", "callback_data": "menu_gift"}],
        [{"text": "🛒 خرید اشتراک", "callback_data": "menu_buy"}],
        [{"text": "👤 حساب کاربری من", "callback_data": "menu_profile"},
         {"text": "📚 آموزش و راهنما", "callback_data": "menu_help"}],
        [{"text": "👥 زیرمجموعه‌گیری", "callback_data": "menu_referral"},
         {"text": "🎧 پشتیبانی", "callback_data": "menu_support"}],
    ]}


def categories_keyboard():
    return {"inline_keyboard": [
        [{"text": "💎 VIP", "callback_data": "cat_VIP"},
         {"text": "💡 اقتصادی", "callback_data": "cat_Economic"}],
        [{"text": "🔒 اختصاصی", "callback_data": "cat_Dedicated"},
         {"text": "📈 ترید", "callback_data": "cat_Trade"}],
        [{"text": "🔙 بازگشت به منوی اصلی", "callback_data": "menu_main"}],
    ]}


def volumes_keyboard(category: str):
    return {"inline_keyboard": [
        [{"text": "۵ گیگ", "callback_data": f"vol_{category}_5"},
         {"text": "۱۰ گیگ", "callback_data": f"vol_{category}_10"},
         {"text": "۲۰ گیگ", "callback_data": f"vol_{category}_20"}],
        [{"text": "۳۰ گیگ", "callback_data": f"vol_{category}_30"},
         {"text": "۵۰ گیگ", "callback_data": f"vol_{category}_50"},
         {"text": "۱۰۰ گیگ", "callback_data": f"vol_{category}_100"}],
        [{"text": "✏️ حجم دلخواه (هر گیگ ۵,۰۰۰ تومان)", "callback_data": f"vol_{category}_custom"}],
        [{"text": "🔙 بازگشت به دسته‌بندی‌ها", "callback_data": "menu_buy"}],
    ]}


def payment_methods_keyboard(order_id: int):
    return {"inline_keyboard": [
        [{"text": "🟢 کارت به کارت (ارسال فیش)", "callback_data": f"pay_card_{order_id}"}],
        [{"text": "🎟 اعمال کد تخفیف", "callback_data": f"apply_discount_{order_id}"}],
        [{"text": "❌ انصراف از خرید", "callback_data": "menu_main"}],
        [{"text": "🔙 بازگشت به منوی اصلی", "callback_data": "menu_main"}],
    ]}


def admin_order_keyboard(order_id: int):
    return {"inline_keyboard": [
        [{"text": "✅ تایید و ساخت خودکار در پنل", "callback_data": f"admin_approve_{order_id}"},
         {"text": "❌ رد سفارش", "callback_data": f"admin_reject_{order_id}"}],
    ]}


def guides_keyboard():
    return {"inline_keyboard": [
        [{"text": "📱 راهنمای اندروید", "callback_data": "guide_android"},
         {"text": "🍎 راهنمای آیفون", "callback_data": "guide_ios"}],
        [{"text": "💻 راهنمای ویندوز/مک", "callback_data": "guide_pc"},
         {"text": "🛠 رفع مشکلات رایج", "callback_data": "guide_trouble"}],
        [{"text": "🔙 بازگشت به منوی اصلی", "callback_data": "menu_main"}],
    ]}


def guide_download_keyboard(g_type: str):
    if g_type == "android":
        return {"inline_keyboard": [
            [{"text": "⬇️ دانلود v2rayNG (گیت‌هاب)", "url": "https://github.com/2dust/v2rayNG/releases"}],
            [{"text": "⬇️ دانلود Hiddify (APK)", "url": "https://github.com/hiddify/hiddify-app/releases/download/v4.1.1/Hiddify-Android-universal.apk"}],
            [{"text": "🔙 بازگشت به راهنما", "callback_data": "menu_help"}],
        ]}
    elif g_type == "ios":
        return {"inline_keyboard": [
            [{"text": "⬇️ Hiddify (App Store)", "url": "https://apps.apple.com/app/hiddify-proxy/id6473774447"}],
            [{"text": "⬇️ NPV Tunnel (App Store)", "url": "https://apps.apple.com/us/app/npv-tunnel/id1629465476"}],
            [{"text": "🔙 بازگشت به راهنما", "callback_data": "menu_help"}],
        ]}
    elif g_type == "pc":
        return {"inline_keyboard": [
            [{"text": "⬇️ دانلود v2rayN (ویندوز)", "url": "https://github.com/2dust/v2rayN/releases/download/7.24.3/v2rayN-windows-64-desktop.zip"}],
            [{"text": "⬇️ دانلود Hiddify (ویندوز)", "url": "https://github.com/hiddify/hiddify-app/releases/download/v4.1.1/Hiddify-Windows-Setup-x64.exe"}],
            [{"text": "🔙 بازگشت به راهنما", "callback_data": "menu_help"}],
        ]}
    return back_button_keyboard("menu_help")


def after_approval_keyboard():
    return {"inline_keyboard": [
        [{"text": "👤 حساب کاربری من", "callback_data": "menu_profile"}],
        [{"text": "🏠 منوی اصلی", "callback_data": "menu_main"}],
    ]}


def profile_keyboard():
    return {"inline_keyboard": [
        [{"text": "🛒 خرید اشتراک جدید", "callback_data": "menu_buy"}],
        [{"text": "🔙 بازگشت", "callback_data": "menu_main"}],
    ]}


def pending_order_keyboard(order_id: int):
    return {"inline_keyboard": [
        [{"text": "📋 مشاهده سفارش معلق", "callback_data": f"view_pending_{order_id}"}],
        [{"text": "❌ لغو سفارش معلق و ثبت سفارش جدید", "callback_data": f"cancel_pending_{order_id}"}],
        [{"text": "🏠 منوی اصلی", "callback_data": "menu_main"}],
    ]}


def back_button_keyboard(target="menu_main"):
    return {"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": target}]]}

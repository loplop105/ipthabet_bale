"""
ابزارهای امن‌سازی Markdown
"""


def escape_md(text) -> str:
    """Escape تمام کاراکترهای خاص Markdown"""
    if not text:
        return ""
    special = [
        '_', '*', '[', ']', '(', ')', '~', '`', '>',
        '#', '+', '-', '=', '|', '{', '}', '.', '!'
    ]
    result = str(text)
    for char in special:
        result = result.replace(char, f'\\{char}')
    return result


def safe_user_text(text: str) -> str:
    """امن‌سازی متن ورودی کاربر برای استفاده در پیام‌های Markdown"""
    return escape_md(text)

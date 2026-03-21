"""
Dynamic Button Engine
Renders every button type in its correct UI position.
"""
import logging
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
)

from bot.database import SessionLocal, BotButton, WebAppButton

logger = logging.getLogger(__name__)

BUTTON_TYPE_DESCRIPTIONS = {
    "inline": {
        "label": "🔘 Inline Button",
        "desc": "زر شفاف داخل الرسالة بدون رابط أو أمر",
        "placement": "📍 يظهر داخل الرسالة كزر شفاف",
        "needs_data": False,
    },
    "url": {
        "label": "🔗 URL Button",
        "desc": "زر يفتح رابطاً خارجياً في المتصفح",
        "placement": "📍 يظهر أسفل الرسالة كـ Inline Keyboard",
        "needs_data": True,
        "data_prompt": "🔗 أرسل رابط URL (مثال: https://t.me/channel):",
    },
    "callback": {
        "label": "⚙️ Callback Button",
        "desc": "زر يُشغّل أمراً داخلياً في البوت",
        "placement": "📍 يظهر أسفل الرسالة كـ Inline Keyboard",
        "needs_data": True,
        "data_prompt": "⚙️ أرسل Callback Data (مثال: my_action):",
    },
    "webapp": {
        "label": "🌐 Web App Button (Inline)",
        "desc": "زر يفتح Mini App داخل تيليجرام — يظهر أسفل الرسالة",
        "placement": "📍 يظهر أسفل الرسالة — يفتح Mini App داخل تيليجرام",
        "needs_data": True,
        "data_prompt": "🌐 أرسل رابط Web App (يجب أن يبدأ بـ https://):",
    },
    "reply": {
        "label": "⌨️ Reply Keyboard Button",
        "desc": "زر يظهر كلوحة مفاتيح دائمة أسفل الشاشة — عند ضغطه يرد البوت برسالة مخصصة",
        "placement": "📍 يظهر كلوحة مفاتيح أسفل الشاشة",
        "needs_data": True,
        "data_prompt": "💬 أرسل نص الرسالة التي سيردّ بها البوت عند ضغط هذا الزر:",
    },
    "reply_webapp": {
        "label": "🌐 Web App Button (Keyboard)",
        "desc": "زر لوحة مفاتيح يفتح Mini App — يظهر أسفل الشاشة بشكل دائم",
        "placement": "📍 يظهر كلوحة مفاتيح أسفل الشاشة — يفتح Mini App (مثل Open في BotFather)",
        "needs_data": True,
        "data_prompt": "🌐 أرسل رابط Web App (يجب أن يبدأ بـ https://):",
    },
}

PLACEMENT_LABELS = {
    "inline": "💬 داخل الرسالة",
    "reply_keyboard": "⌨️ لوحة المفاتيح",
    "menu_button": "📱 شريط المدخلات (Menu Button)",
    "bot_menu": "📂 قائمة البوت",
}


def get_buttons_for_location(location: str):
    """
    Returns:
        inline_rows: list of InlineKeyboardButton rows
        reply_btns:  list of KeyboardButton for ReplyKeyboardMarkup
    """
    inline_rows = []
    reply_btns = []

    db = SessionLocal()
    try:
        btns = db.query(BotButton).filter_by(
            location=location, is_active=True
        ).order_by(BotButton.position).all()

        inline_webapps = db.query(WebAppButton).filter(
            WebAppButton.location == location,
            WebAppButton.is_active == True,
            WebAppButton.placement == "inline",
        ).order_by(WebAppButton.position).all()

        reply_webapps = db.query(WebAppButton).filter(
            WebAppButton.is_active == True,
            WebAppButton.placement == "reply_keyboard",
        ).order_by(WebAppButton.position).all()

        for btn in btns:
            btype = btn.button_type

            if btype == "url" and btn.data:
                inline_rows.append([InlineKeyboardButton(btn.label, url=btn.data)])

            elif btype == "webapp" and btn.data:
                try:
                    inline_rows.append([
                        InlineKeyboardButton(btn.label, web_app=WebAppInfo(url=btn.data))
                    ])
                except Exception as e:
                    logger.error(f"Invalid webapp URL button {btn.id}: {e}")
                    inline_rows.append([InlineKeyboardButton(btn.label, url=btn.data)])

            elif btype == "callback" and btn.data:
                inline_rows.append([
                    InlineKeyboardButton(btn.label, callback_data=btn.data)
                ])

            elif btype == "inline":
                inline_rows.append([
                    InlineKeyboardButton(btn.label, callback_data=f"btn_noop_{btn.id}")
                ])

            elif btype == "reply":
                reply_btns.append(KeyboardButton(btn.label))

            elif btype == "reply_webapp" and btn.data:
                try:
                    reply_btns.append(
                        KeyboardButton(btn.label, web_app=WebAppInfo(url=btn.data))
                    )
                except Exception as e:
                    logger.error(f"Invalid reply_webapp URL button {btn.id}: {e}")
                    reply_btns.append(KeyboardButton(btn.label))

        for wa in inline_webapps:
            try:
                inline_rows.append([
                    InlineKeyboardButton(wa.label, web_app=WebAppInfo(url=wa.url))
                ])
            except Exception as e:
                logger.error(f"Invalid webapp URL WebAppButton {wa.id}: {e}")

        for wa in reply_webapps:
            try:
                reply_btns.append(
                    KeyboardButton(wa.label, web_app=WebAppInfo(url=wa.url))
                )
            except Exception as e:
                logger.error(f"Invalid reply_webapp URL WebAppButton {wa.id}: {e}")
                reply_btns.append(KeyboardButton(wa.label))

    except Exception as e:
        logger.error(f"Error loading buttons for location={location}: {e}")
    finally:
        db.close()

    return inline_rows, reply_btns


def build_reply_markup(inline_rows, reply_btns, fallback_inline=None):
    """
    Smart markup builder — prioritises reply keyboard on the main message.

    Returns: (main_markup, extra_markup)
      - main_markup  → attach directly to the main message
      - extra_markup → send as a follow-up message ONLY when both types coexist
                       (never shows the ugly ⌨️ placeholder when unnecessary)

    Priority:
      • reply btns only   → ReplyKeyboard on main message
      • inline only       → InlineKeyboard on main message
      • both              → InlineKeyboard on main message + ReplyKeyboard as extra
      • neither           → fallback inline (if given) on main message, else None
    """
    main_markup = None
    extra_markup = None

    if reply_btns:
        # 2 buttons per row for a compact look
        rows = [reply_btns[i:i+2] for i in range(0, len(reply_btns), 2)]
        reply_kb = ReplyKeyboardMarkup(
            rows, resize_keyboard=True, one_time_keyboard=False
        )
        if inline_rows:
            # Both: inline on main message, reply keyboard as extra
            main_markup = InlineKeyboardMarkup(inline_rows)
            extra_markup = reply_kb
        else:
            # Only reply keyboard: attach to main message directly
            main_markup = reply_kb
    else:
        # No reply buttons: use inline or fallback
        if inline_rows:
            main_markup = InlineKeyboardMarkup(inline_rows)
        elif fallback_inline:
            main_markup = InlineKeyboardMarkup(fallback_inline)

    return main_markup, extra_markup


def get_reply_button_response(text: str) -> str | None:
    """
    Check if the given text matches an active reply keyboard button label.
    Returns the configured reply message (data) or None if no match.
    """
    db = SessionLocal()
    try:
        from bot.database import BotButton
        btn = db.query(BotButton).filter_by(
            button_type="reply", label=text, is_active=True
        ).first()
        if btn and btn.data:
            return btn.data
        # Also match without whitespace differences
        if not btn:
            all_reply = db.query(BotButton).filter_by(
                button_type="reply", is_active=True
            ).all()
            for b in all_reply:
                if b.label.strip() == text.strip() and b.data:
                    return b.data
        return None
    except Exception as e:
        logger.error(f"Error checking reply button response: {e}")
        return None
    finally:
        db.close()


async def apply_menu_button(bot, wa_label: str, wa_url: str):
    """Set the Telegram Menu Button via direct Bot API HTTP call."""
    import os, httpx
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/setMyMenuButton",
                json={
                    "menu_button": {
                        "type": "web_app",
                        "text": wa_label[:16],       # Telegram limit: 16 chars
                        "web_app": {"url": wa_url},
                    }
                }
            )
            data = r.json()
            if data.get("ok"):
                logger.info(f"Menu Button set: {wa_label}")
                return True
            else:
                logger.error(f"Menu Button API error: {data.get('description')}")
                return False
    except Exception as e:
        logger.error(f"Failed to set Menu Button: {e}")
        return False


async def remove_menu_button(bot):
    """Remove the Telegram Menu Button (reset to default commands menu)."""
    import os, httpx
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/setMyMenuButton",
                json={"menu_button": {"type": "default"}}
            )
            return r.json().get("ok", False)
    except Exception as e:
        logger.error(f"Failed to remove Menu Button: {e}")
        return False

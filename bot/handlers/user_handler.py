import logging
import os
import json

from telegram import CallbackQuery
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from bot.database import SessionLocal, SubscriptionChannel, User, UserStatus, BotLanguage, get_setting
from bot.locales import get_string
from bot.security import check_download_rate_limit
from bot.services import DownloadService
from bot.utils.button_engine import (
    build_reply_markup,
    get_buttons_for_location,
    get_reply_button_response,
)
from bot.utils.helpers import get_user_name
from bot.utils.platforms import detect_platform, get_platform_info, is_any_url

logger = logging.getLogger(__name__)

BOT_OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "0"))


# ─── helpers ──────────────────────────────────────────────────────────────────

def get_lang_setting(key: str, lang: str, default: str = "") -> str:
    """Get a DB setting with language fallback: {key}_{lang} → {key} → default."""
    val = get_setting(f"{key}_{lang}", "")
    if not val:
        val = get_setting(key, default)
    return val


def get_or_create_user(telegram_user, db):
    user = db.query(User).filter_by(telegram_id=telegram_user.id).first()
    if not user:
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code or "ar",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        db.commit()
    return user


def get_enabled_languages():
    """Return list of enabled BotLanguage rows ordered by position."""
    db = SessionLocal()
    try:
        langs = (
            db.query(BotLanguage)
            .filter_by(is_enabled=True)
            .order_by(BotLanguage.position)
            .all()
        )
        if not langs:
            return [type("L", (), {"code": "ar", "name": "العربية", "flag": "🇸🇦"})()]
        return langs
    finally:
        db.close()


def build_lang_keyboard(current_lang: str = "ar"):
    """Build inline keyboard from admin-enabled languages (2 per row)."""
    langs = get_enabled_languages()
    btns = []
    for lang in langs:
        label = f"{'✅ ' if lang.code == current_lang else ''}{lang.flag} {lang.name}"
        btns.append(InlineKeyboardButton(label, callback_data=f"lang_{lang.code}"))

    rows = [btns[i:i+2] for i in range(0, len(btns), 2)]
    return InlineKeyboardMarkup(rows)


async def _send_message(target, text: str, main_markup, extra_markup, context=None):
    """
    Unified sender: sends main message with main_markup.
    If extra_markup (reply keyboard) needs a separate message, sends it silently.
    """
    if isinstance(target, CallbackQuery):
        chat_id = target.message.chat_id
        await context.bot.send_message(chat_id, text, reply_markup=main_markup)
        if extra_markup:
            await context.bot.send_message(chat_id, "⌨️", reply_markup=extra_markup)
    else:
        await target.reply_text(text, reply_markup=main_markup)
        if extra_markup:
            await target.reply_text("⌨️", reply_markup=extra_markup)


async def check_subscriptions(user_id: int, bot) -> tuple[bool, list]:
    db = SessionLocal()
    try:
        channels = db.query(SubscriptionChannel).filter_by(
            is_active=True, is_backup=False
        ).all()

        if not channels:
            return True, []

        unsubscribed = []
        for ch in channels:
            if ch.chat_type == "bot":
                logger.warning("Skipping unsupported bot subscription target id=%s chat_id=%s", ch.id, ch.chat_id)
                continue
            try:
                member = await bot.get_chat_member(ch.chat_id, user_id)
                is_member = getattr(member, "is_member", None)
                if member.status in ("left", "kicked", "banned") or (member.status == "restricted" and is_member is False):
                    unsubscribed.append(ch)
            except Exception as e:
                logger.error(f"Error checking subscription for {ch.chat_id}: {e}")
                unsubscribed.append(ch)

        return len(unsubscribed) == 0, unsubscribed
    finally:
        db.close()


def build_subscription_keyboard(channels: list, lang: str) -> InlineKeyboardMarkup:
    keyboard = []
    for ch in channels:
        title = ch.title or f"قناة {ch.id}"
        link = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "#")
        keyboard.append([InlineKeyboardButton(f"📢 {title}", url=link)])

    try:
        extra_buttons = json.loads(get_setting("sub_buttons_json", "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        extra_buttons = []

    for button in extra_buttons:
        label = str((button or {}).get("label", "")).strip()
        url = str((button or {}).get("url", "")).strip()
        if label and url:
            keyboard.append([InlineKeyboardButton(label, url=url)])

    keyboard.append([InlineKeyboardButton(get_string("check_subscription", lang), callback_data="check_sub")])
    return InlineKeyboardMarkup(keyboard)


# ─── /start ───────────────────────────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = SessionLocal()
    try:
        db_user = get_or_create_user(user, db)

        if db_user.status == UserStatus.BANNED:
            await update.message.reply_text(get_string("banned", db_user.language_code))
            return

        lang = db_user.language_code or "ar"

        sub_enabled = get_setting("subscription_enabled", "true") == "true"
        if sub_enabled:
            is_subscribed, unsubscribed = await check_subscriptions(user.id, context.bot)
        else:
            is_subscribed = True
            unsubscribed = []

        if not is_subscribed:
            sub_msg = get_lang_setting("subscription_message", lang, get_string("subscribe_required", lang))
            welcome = get_string("welcome", lang, name=get_user_name(user))
            await update.message.reply_text(
                f"{welcome}\n\n{sub_msg}",
                reply_markup=build_subscription_keyboard(unsubscribed, lang)
            )
            return

        await _show_welcome(update, context, db_user, get_user_name(user), lang)
    finally:
        db.close()


async def _show_welcome(update, context, db_user, name: str, lang: str):
    bot_name = get_setting("bot_name", "SaveEliteBot")
    default_start = (
        get_string("welcome", lang, name=name) + "\n\n"
        + get_string("send_link", lang) + "\n\n"
        "/help - " + get_string("help_text", lang, bot_name=bot_name)[:40] + "...\n"
        "/lang - " + get_string("lang_select", lang)
    )
    start_msg = get_lang_setting("start_message", lang, default_start)
    start_msg = (
        start_msg
        .replace("{name}", name)
        .replace("{bot_name}", bot_name)
    )

    me = await context.bot.get_me()
    inline_rows, reply_btns = get_buttons_for_location("start")

    fallback = [[
        InlineKeyboardButton(
            get_string("add_to_chat", lang),
            url=f"https://t.me/{me.username}?startgroup=true"
        )
    ]]
    main_markup, extra_markup = build_reply_markup(
        inline_rows, reply_btns, fallback_inline=fallback
    )

    if not isinstance(update, CallbackQuery):
        await update.message.reply_text(start_msg, reply_markup=main_markup)
        if extra_markup:
            await update.message.reply_text("⌨️", reply_markup=extra_markup)
        return

    chat_id = update.message.chat_id
    await context.bot.send_message(chat_id, start_msg, reply_markup=main_markup)
    if extra_markup:
        await context.bot.send_message(chat_id, "⌨️", reply_markup=extra_markup)


# ─── /help ────────────────────────────────────────────────────────────────────

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(telegram_id=user.id).first()
        lang = db_user.language_code if db_user else "ar"
        bot_name = get_setting("bot_name", "SaveEliteBot")

        help_msg = get_lang_setting(
            "help_message", lang,
            get_string("help_text", lang, bot_name=bot_name)
        )
        help_msg = help_msg.replace("{bot_name}", bot_name)

        inline_rows, reply_btns = get_buttons_for_location("help")
        main_markup, extra_markup = build_reply_markup(inline_rows, reply_btns)
        await update.message.reply_text(help_msg, reply_markup=main_markup)
        if extra_markup:
            await update.message.reply_text("⌨️", reply_markup=extra_markup)
    finally:
        db.close()


# ─── /lang ────────────────────────────────────────────────────────────────────

async def lang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(telegram_id=user.id).first()
        lang = db_user.language_code if db_user else "ar"
    finally:
        db.close()

    enabled = get_enabled_languages()
    if len(enabled) <= 1:
        await update.message.reply_text(
            "🌍 البوت يدعم لغة واحدة فقط حالياً.\n"
            "يمكن للمسؤول تفعيل المزيد من اللغات من لوحة التحكم."
        )
        return

    await update.message.reply_text(
        get_string("lang_select", lang),
        reply_markup=build_lang_keyboard(lang)
    )


# ─── callbacks ────────────────────────────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    db = SessionLocal()

    try:
        db_user = db.query(User).filter_by(telegram_id=user.id).first()
        if not db_user:
            db_user = get_or_create_user(user, db)
        lang = db_user.language_code or "ar"

        if data.startswith("btn_noop_"):
            return

        if data == "check_sub":
            is_subscribed, unsubscribed = await check_subscriptions(user.id, context.bot)
            if is_subscribed:
                await query.edit_message_reply_markup(reply_markup=None)
                name = get_user_name(user)
                await _show_welcome(query, context, db_user, name, lang)
            else:
                await query.answer(get_string("not_subscribed", lang), show_alert=True)
                await query.edit_message_reply_markup(reply_markup=build_subscription_keyboard(unsubscribed, lang))

        elif data.startswith("lang_"):
            new_lang = data[len("lang_"):]

            lang_obj = db.query(BotLanguage).filter_by(code=new_lang, is_enabled=True).first()
            if not lang_obj:
                await query.answer("⚠️ هذه اللغة غير مفعّلة حالياً", show_alert=True)
                return

            db_user.language_code = new_lang
            db.commit()

            confirm_text = get_string("lang_changed", new_lang)
            await query.answer(confirm_text, show_alert=True)

            try:
                await query.edit_message_text(
                    text=get_string("lang_select", new_lang),
                    reply_markup=build_lang_keyboard(new_lang)
                )
            except Exception:
                pass

    finally:
        db.close()


# ─── message handler ──────────────────────────────────────────────────────────

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text

    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(telegram_id=user.id).first()
        if not db_user:
            db_user = get_or_create_user(user, db)

        if db_user.status == UserStatus.BANNED:
            await update.message.reply_text(get_string("banned", db_user.language_code))
            return

        lang = db_user.language_code or "ar"
        bot_name = get_setting("bot_name", "SaveEliteBot")

        reply_response = get_reply_button_response(text)
        if reply_response:
            formatted = (
                reply_response
                .replace("{name}", get_user_name(user))
                .replace("{bot_name}", bot_name)
                .replace("{lang}", lang)
            )
            await update.message.reply_text(formatted)
            return

        sub_enabled = get_setting("subscription_enabled", "true") == "true"
        if sub_enabled:
            is_subscribed, unsubscribed = await check_subscriptions(user.id, context.bot)
            if not is_subscribed:
                await update.message.reply_text(
                    get_lang_setting("subscription_message", lang, get_string("subscribe_required", lang)),
                    reply_markup=build_subscription_keyboard(unsubscribed, lang)
                )
                return

        if not is_any_url(text):
            return

        detected_url, platform = detect_platform(text)

        if not detected_url or not platform:
            unsup_msg = get_lang_setting(
                "unsupported_platform_msg", lang,
                get_lang_setting("unsupported_message", lang, get_string("unsupported", lang))
            )
            await update.message.reply_text(unsup_msg)
            return

        platform_info = get_platform_info(platform)
        platform_name = platform_info.get("name", platform.title())
        enabled_key = platform_info.get("db_key", f"{platform}_enabled")

        if get_setting(enabled_key, "true") != "true":
            disabled_msg = get_lang_setting(
                f"{platform}_disabled_msg", lang,
                get_setting("disabled_platform_generic_msg", f"عذراً، {platform_name} غير مفعل حالياً في البوت.")
            )
            await update.message.reply_text(disabled_msg)
            return

        allowed, retry_after = check_download_rate_limit(db_user.id, is_admin=bool(db_user.is_admin))
        if not allowed:
            rate_limit_message = get_lang_setting(
                "rate_limit_message",
                lang,
                "⚠️ الضغط مرتفع حالياً. يرجى الانتظار {seconds} ثانية قبل إرسال طلب جديد.",
            )
            await update.message.reply_text(rate_limit_message.replace("{seconds}", str(retry_after)))
            return

        wait_msg = await update.message.reply_text(
            get_lang_setting("downloading_message", lang, get_string("downloading", lang))
        )

        try:
            job_id = DownloadService.enqueue_download(
                user_id=db_user.id,
                chat_id=update.effective_chat.id,
                url=detected_url,
                platform=platform,
                lang=lang,
                status_message_id=wait_msg.message_id,
            )
            logger.info("Queued download job %s for user=%s platform=%s", job_id, db_user.id, platform)
            await wait_msg.edit_text(
                get_lang_setting(
                    "queued_message",
                    lang,
                    (
                        "📥 تم استلام طلبك ووضعه في قائمة المعالجة.\n"
                        f"🆔 رقم الطلب: {job_id}\n"
                        "⏳ سيتم تحديث هذه الرسالة عند بدء التنفيذ."
                    ),
                )
            )
        except Exception as exc:
            logger.exception("Failed to enqueue download job: %s", exc)
            await wait_msg.edit_text(get_lang_setting("error_message", lang, get_string("error", lang)))
    finally:
        db.close()

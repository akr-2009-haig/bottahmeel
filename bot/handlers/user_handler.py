import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram import CallbackQuery
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from bot.database import (
    SessionLocal, User, SubscriptionChannel, Download,
    UserStatus, BotLanguage, get_setting
)
from bot.locales import get_string
from bot.utils.helpers import cleanup_file, get_user_name
from bot.utils.platforms import detect_platform, download_media, is_any_url, get_platform_info
from bot.utils.button_engine import (
    get_buttons_for_location, build_reply_markup, get_reply_button_response
)

logger = logging.getLogger(__name__)

BOT_OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "0"))

ACTIVITY_MAP = {
    "upload_video": ChatAction.UPLOAD_VIDEO,
    "upload_photo": ChatAction.UPLOAD_PHOTO,
    "upload_document": ChatAction.UPLOAD_DOCUMENT,
    "typing": ChatAction.TYPING,
    "record_voice": ChatAction.RECORD_VOICE,
}


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
    If extra_markup (reply keyboard) needs a separate message, sends it silently
    — no ⌨️ placeholder when only one type exists.
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
            try:
                member = await bot.get_chat_member(ch.chat_id, user_id)
                if member.status in ("left", "kicked", "banned"):
                    unsubscribed.append(ch)
            except Exception as e:
                logger.error(f"Error checking subscription for {ch.chat_id}: {e}")
                unsubscribed.append(ch)

        return len(unsubscribed) == 0, unsubscribed
    finally:
        db.close()


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
            keyboard = []
            for ch in unsubscribed:
                title = ch.title or f"قناة {ch.id}"
                link = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "#")
                keyboard.append([InlineKeyboardButton(f"📢 {title}", url=link)])
            keyboard.append([InlineKeyboardButton(get_string("check_subscription", lang), callback_data="check_sub")])

            sub_msg = get_lang_setting("subscription_message", lang,
                                       get_string("subscribe_required", lang))
            welcome = get_string("welcome", lang, name=get_user_name(user))
            await update.message.reply_text(
                f"{welcome}\n\n{sub_msg}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        await _show_welcome(update, context, db_user, get_user_name(user), lang)
    finally:
        db.close()


async def _show_welcome(update, context, db_user, name: str, lang: str):
    bot_name = get_setting("bot_name", "SaveEliteBot")

    # Language-aware start message: tries start_message_{lang} first
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

    msg = update.message if not isinstance(update, CallbackQuery) else None
    if msg:
        await msg.reply_text(start_msg, reply_markup=main_markup)
        if extra_markup:
            await msg.reply_text("⌨️", reply_markup=extra_markup)
    else:
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

        # Language-aware help message
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
                keyboard = []
                for ch in unsubscribed:
                    title = ch.title or f"قناة {ch.id}"
                    link = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "#")
                    keyboard.append([InlineKeyboardButton(f"📢 {title}", url=link)])
                keyboard.append([InlineKeyboardButton(get_string("check_subscription", lang), callback_data="check_sub")])
                await query.answer(get_string("not_subscribed", lang), show_alert=True)
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

        elif data.startswith("lang_"):
            new_lang = data[len("lang_"):]

            lang_obj = db.query(BotLanguage).filter_by(code=new_lang, is_enabled=True).first()
            if not lang_obj:
                await query.answer("⚠️ هذه اللغة غير مفعّلة حالياً", show_alert=True)
                return

            db_user.language_code = new_lang
            db.commit()

            # Show confirmation in the new language
            confirm_text = get_string("lang_changed", new_lang)
            await query.answer(confirm_text, show_alert=True)

            # Refresh the language picker with new selection highlighted
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

        # ── Priority 1: Reply keyboard button response ───────────────────────
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

        # ── Priority 2: Subscription gate ───────────────────────────────────
        sub_enabled = get_setting("subscription_enabled", "true") == "true"
        if sub_enabled:
            is_subscribed, unsubscribed = await check_subscriptions(user.id, context.bot)
            if not is_subscribed:
                keyboard = []
                for ch in unsubscribed:
                    title = ch.title or f"قناة {ch.id}"
                    link = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "#")
                    keyboard.append([InlineKeyboardButton(f"📢 {title}", url=link)])
                keyboard.append([InlineKeyboardButton(get_string("check_subscription", lang), callback_data="check_sub")])
                await update.message.reply_text(
                    get_lang_setting("subscription_message", lang,
                                    get_string("subscribe_required", lang)),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return

        # ── Priority 3: URL / platform download ─────────────────────────────
        if not is_any_url(text):
            return

        detected_url, platform = detect_platform(text)

        if not detected_url or not platform:
            unsup_msg = get_lang_setting(
                "unsupported_platform_msg", lang,
                get_lang_setting("unsupported_message", lang,
                                 get_string("unsupported", lang))
            )
            await update.message.reply_text(unsup_msg)
            return

        platform_info = get_platform_info(platform)
        platform_name = platform_info.get("name", platform.title())
        platform_emoji = platform_info.get("emoji", "📥")
        enabled_key = platform_info.get("db_key", f"{platform}_enabled")

        if get_setting(enabled_key, "true") != "true":
            disabled_msg = get_lang_setting(
                f"{platform}_disabled_msg", lang,
                get_setting("disabled_platform_generic_msg",
                            f"عذراً، {platform_name} غير مفعل حالياً في البوت.")
            )
            await update.message.reply_text(disabled_msg)
            return

        wait_msg = await update.message.reply_text(
            get_lang_setting("downloading_message", lang,
                             get_string("downloading", lang))
        )

        activity = get_setting("activity_status", "upload_video")
        await context.bot.send_chat_action(
            update.effective_chat.id,
            ACTIVITY_MAP.get(activity, ChatAction.UPLOAD_VIDEO)
        )

        filepath, media_type, title = await download_media(detected_url, platform)

        if not filepath:
            err = get_lang_setting("error_message", lang, get_string("error", lang))
            await wait_msg.edit_text(err)
            db.add(Download(
                user_id=db_user.id, platform=platform,
                url=detected_url, media_type="video", success=False
            ))
            db.commit()
            return

        # Caption: language-aware
        if media_type == "photo":
            cap_key = "photo_caption"
        elif media_type == "audio":
            cap_key = "audio_caption"
        else:
            cap_key = "video_caption"

        cap_template = get_lang_setting(
            cap_key, lang,
            get_setting(cap_key,
                        get_string("success_caption", lang, bot_name=bot_name))
        )
        caption = (
            cap_template
            .replace("{bot_name}", bot_name)
            .replace("{name}", get_user_name(user))
            .replace("{platform}", platform_name)
            .replace("{platform_emoji}", platform_emoji)
        )

        # Download-location buttons
        dl_inline_rows, dl_reply_btns = get_buttons_for_location("download")
        dl_main_markup, dl_extra_markup = build_reply_markup(dl_inline_rows, dl_reply_btns)

        try:
            await wait_msg.delete()
        except Exception:
            pass

        try:
            with open(filepath, "rb") as f:
                if media_type == "photo":
                    await update.message.reply_photo(photo=f, caption=caption,
                                                     reply_markup=dl_main_markup)
                elif media_type == "audio":
                    await update.message.reply_audio(audio=f, caption=caption,
                                                     reply_markup=dl_main_markup)
                else:
                    await update.message.reply_video(video=f, caption=caption,
                                                     supports_streaming=True,
                                                     reply_markup=dl_main_markup)

            if dl_extra_markup:
                await update.message.reply_text("⌨️", reply_markup=dl_extra_markup)

            db_user.download_count += 1
            db.add(Download(
                user_id=db_user.id, platform=platform,
                url=detected_url, media_type=media_type, success=True
            ))
            db.commit()

        except Exception as e:
            logger.error(f"Error sending media [{platform}]: {e}")
            await update.message.reply_text(
                get_lang_setting("error_message", lang, get_string("error", lang))
            )
        finally:
            cleanup_file(filepath)

    finally:
        db.close()

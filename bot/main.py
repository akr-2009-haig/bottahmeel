import os
import logging
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters
)

from bot.database.db import init_db
from bot.handlers.user_handler import (
    start_handler, help_handler, lang_handler,
    callback_handler, message_handler
)
from bot.admin.admin_handler import (
    admin_command, admin_callback, admin_message_handler, is_admin
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BOT_OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "0"))

ADMIN_CB_PREFIXES = [
    "adm_", "ui_",
    "ban_user_", "unban_user_", "delete_user_",
    "confirm_ban_", "confirm_unban_", "confirm_delete_user_",
    "admin_details_", "disable_admin_", "enable_admin_",
    "delete_admin_", "confirm_disable_admin_", "confirm_delete_admin_",
    "edit_admin_perms_", "toggle_perm_", "perms_", "sub_",
    "delete_sub_", "confirm_delete_sub_", "delete_pub_", "confirm_delete_pub_",
    "bc_", "do_broadcast_", "view_ad_", "delete_ad_",
    "af_", "toggle_ignore_inactive", "confirm_af_reset",
    "sched_", "pause_sched_", "resume_sched_", "delete_sched_", "confirm_delete_sched_",
    "group_details_", "delete_group_", "confirm_delete_group_",
    "confirm_del_inactive_", "export_", "toggle_tiktok", "toggle_youtube",
    "toggle_instagram", "toggle_likee", "set_activity_",
    "confirm_settings_reset", "confirm_ui_reset",
    "view_all_messages",
]

ADMIN_WAIT_PREFIXES = [
    "add_admin_id", "add_sub_entity", "add_pub_entity", "create_group_name",
    "search_user", "get_user_info", "edit_setting_", "bc_text_",
    "send_to_user_id", "send_to_user_text", "af_speed_custom",
    "af_delay_custom", "af_retry_custom", "search_admin", "ad_title", "ad_text",
    "ui_msg_text_", "ui_btn_label", "ui_btn_data_", "ui_btn_data_reply",
    "ui_wa_label", "ui_wa_url", "ui_lang_tr_", "ui_plat_msg_", "ui_caption_",
]


async def combined_callback_handler(update: Update, context):
    query = update.callback_query
    if not query:
        return
    data = query.data or ""

    is_adm_cb = any(data.startswith(p) for p in ADMIN_CB_PREFIXES)

    if is_adm_cb:
        db_check = None
        try:
            from bot.database import SessionLocal
            db_check = SessionLocal()
            if is_admin(query.from_user.id, db_check):
                db_check.close()
                await admin_callback(update, context)
                return
        finally:
            if db_check:
                try:
                    db_check.close()
                except Exception:
                    pass

    await callback_handler(update, context)


async def combined_message_handler(update: Update, context):
    if not update.message or not update.message.text:
        return

    user = update.effective_user

    from bot.database import SessionLocal
    db = SessionLocal()
    try:
        is_adm = is_admin(user.id, db)
    finally:
        db.close()

    waiting = context.user_data.get("waiting_for", "")

    if is_adm and waiting and any(waiting.startswith(p) for p in ADMIN_WAIT_PREFIXES):
        await admin_message_handler(update, context)
        return

    await message_handler(update, context)


async def _post_init(application):
    """Register bot commands so the Menu button shows them in Telegram."""
    await application.bot.set_my_commands([
        BotCommand("start", "▶️ بدء البوت / Start"),
        BotCommand("help",  "❓ المساعدة / Help"),
        BotCommand("lang",  "🌍 تغيير اللغة / Language"),
    ])
    logger.info("Bot commands registered (Menu button).")


def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        return

    logger.info("Initializing database...")
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return

    logger.info("Starting bot...")
    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("lang", lang_handler))
    app.add_handler(CommandHandler("admin", admin_command))

    app.add_handler(CallbackQueryHandler(combined_callback_handler))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        combined_message_handler
    ))

    logger.info("Bot is running...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()

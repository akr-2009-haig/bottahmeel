from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.admin.admin_handler import admin_callback, admin_command, admin_message_handler, is_admin
from bot.config import load_settings
from bot.database import SessionLocal, init_db
from bot.handlers.user_handler import callback_handler, help_handler, lang_handler, message_handler, start_handler
from bot.monitoring.health import start_health_server
from bot.services import DownloadService
from bot.temp import cleanup_stale_directories

logger = logging.getLogger(__name__)

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
    if any(data.startswith(prefix) for prefix in ADMIN_CB_PREFIXES):
        db = SessionLocal()
        try:
            if is_admin(query.from_user.id, db):
                await admin_callback(update, context)
                return
        finally:
            db.close()
    await callback_handler(update, context)


async def combined_message_handler(update: Update, context):
    if not update.message or not update.message.text:
        return
    db = SessionLocal()
    try:
        is_adm = is_admin(update.effective_user.id, db)
    finally:
        db.close()
    waiting = context.user_data.get("waiting_for", "")
    if is_adm and waiting and any(waiting.startswith(prefix) for prefix in ADMIN_WAIT_PREFIXES):
        await admin_message_handler(update, context)
        return
    await message_handler(update, context)


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start", "▶️ بدء البوت / Start"),
        BotCommand("help", "❓ المساعدة / Help"),
        BotCommand("lang", "🌍 تغيير اللغة / Language"),
    ])
    removed = cleanup_stale_directories()
    logger.info("Bot commands registered; stale temp directories removed=%s", removed)
    if application.job_queue:
        application.job_queue.run_repeating(_cleanup_temp_job, interval=3600, first=300, name="temp-cleanup")
        application.job_queue.run_repeating(_enqueue_scheduled_posts_job, interval=30, first=5, name="scheduled-post-dispatch")


async def _cleanup_temp_job(context) -> None:
    removed = cleanup_stale_directories()
    logger.info("Periodic temp cleanup completed; removed=%s", removed)


async def _enqueue_scheduled_posts_job(context) -> None:
    enqueued_job_ids = DownloadService.enqueue_due_scheduled_posts()
    if enqueued_job_ids:
        logger.info("Enqueued due scheduled posts job_ids=%s", enqueued_job_ids)


def bootstrap_application() -> Application:
    settings = load_settings()
    settings.validate_for_mode()
    init_db()
    start_health_server()
    app = Application.builder().token(settings.bot_token).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("lang", lang_handler))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(combined_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, combined_message_handler))
    return app

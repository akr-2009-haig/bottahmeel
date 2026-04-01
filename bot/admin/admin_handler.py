import logging
import os
import csv
import json
import io
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import load_settings
from bot.database import (
    BackgroundJob,
    BroadcastLog,
    ChannelGroup,
    Download,
    JobStatus,
    PublishChannel,
    SavedAd,
    ScheduledPost,
    SessionLocal,
    SubscriptionChannel,
    User,
    UserStatus,
    AdminActivityLog,
    AdminPermission,
    AdminUser,
    AntiFloodSettings,
    WorkerHeartbeat,
    get_setting,
    set_setting,
)
from bot.queue import get_queue_stats
from bot.services import DownloadService
from bot.utils.platforms import PLATFORMS
from .keyboards import (
    admin_main_keyboard, users_menu_keyboard, admins_menu_keyboard,
    subscription_menu_keyboard, publish_menu_keyboard, broadcast_menu_keyboard,
    scheduled_menu_keyboard, groups_menu_keyboard, antiflood_menu_keyboard,
    stats_menu_keyboard, settings_menu_keyboard, ui_menu_keyboard,
    back_keyboard, confirm_keyboard, export_keyboard, delete_inactive_keyboard,
    speed_keyboard, delay_keyboard, retry_keyboard, activity_status_keyboard,
    platforms_keyboard, sub_settings_keyboard, messages_settings_keyboard,
    add_sub_type_keyboard, broadcast_compose_keyboard, repeat_type_keyboard,
    auto_delete_keyboard, admin_perms_keyboard, admin_add_menu_keyboard,
    admin_sections_keyboard
)
from .sub_handler import dispatch_sub_callback, sub3_handle_message, sub3_main
from .ui_handler import dispatch_ui_callback, ui_handle_message

logger = logging.getLogger(__name__)

BOT_OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "0"))
ADMIN_SECTIONS = {
    "users": "👥 قسم إدارة المستخدمين",
    "admins": "👮 قسم إدارة المشرفين",
    "subscription": "📢 قسم الاشتراك الإجباري",
    "publish": "📡 قسم قنوات النشر",
    "broadcast": "📣 قسم الإذاعة والإعلانات",
    "scheduled": "🗓 قسم النشر المجدول",
    "groups": "📂 قسم مجموعات القنوات",
    "antiflood": "🛡 قسم منع الحظر",
    "stats": "📊 قسم الإحصائيات",
    "settings": "⚙️ قسم إعدادات البوت",
}


def _admins_flow(context) -> dict:
    flow = context.user_data.setdefault("admins_flow", {})
    flow.setdefault("selected_admin_id", None)
    flow.setdefault("selected_permissions", [])
    flow.setdefault("selected_sections", [])
    flow.setdefault("current_page", 0)
    flow.setdefault("last_search_query", "")
    flow.setdefault("current_filter", "all")
    return flow


def _setting_saved(key: str, value: str) -> bool:
    return set_setting(key, value)


PERM_TO_SECTION: dict[str, str] = {
    "manage_users": "users",
    "add_admins": "admins",
    "delete_admins": "admins",
    "manage_subscription": "subscription",
    "manage_channels": "publish",
    "manage_broadcast": "broadcast",
    "manage_scheduled": "scheduled",
    "manage_groups": "groups",
    "manage_antiflood": "antiflood",
    "view_stats": "stats",
    "manage_settings": "settings",
}


def _permission_section_mismatch(perms: list[str], sections: list[str]) -> bool:
    if not perms or not sections:
        return False
    for perm in perms:
        section = PERM_TO_SECTION.get(perm)
        if section and section not in sections:
            return True
    return False


def is_owner(user_id: int) -> bool:
    return user_id == BOT_OWNER_ID


def is_admin(user_id: int, db=None) -> bool:
    if is_owner(user_id):
        return True
    close_db = db is None
    if db is None:
        db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter_by(telegram_id=user_id, is_active=True).first()
        return admin is not None
    finally:
        if close_db:
            db.close()


def get_admin(user_id: int, db) -> AdminUser | None:
    return db.query(AdminUser).filter_by(telegram_id=user_id, is_active=True).first()


def has_permission(user_id: int, permission: str, db) -> bool:
    if is_owner(user_id):
        return True
    admin = get_admin(user_id, db)
    if not admin:
        return False
    return permission in (admin.permissions or [])


def _job_type_counts(stats: dict, job_type: str) -> dict[str, int]:
    return stats.get("job_types", {}).get(job_type, {status.value: 0 for status in JobStatus})


def _status_badge(status: str) -> str:
    badges = {
        "pending": "⏳ قيد الانتظار",
        "processing": "⚙️ قيد المعالجة",
        "retry": "🔁 إعادة محاولة",
        "completed": "✅ مكتمل",
        "failed": "❌ فشل",
        "scheduled": "🗓 مجدول",
    }
    return badges.get(status, status)


def _worker_health_summary(db) -> tuple[int, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=load_settings().worker_heartbeat_ttl_seconds)
    workers = db.query(WorkerHeartbeat).all()
    active = 0
    stale = 0
    for worker in workers:
        if worker.status == "stopped":
            continue
        if worker.last_seen and worker.last_seen >= cutoff:
            active += 1
        else:
            stale += 1
    return active, stale


def _scheduled_runtime_status(post: ScheduledPost, job_status_by_id: dict[int, str]) -> str:
    if post.last_job_id and post.last_job_id in job_status_by_id:
        return job_status_by_id[post.last_job_id]
    if post.is_sent:
        return "completed"
    if not post.is_active:
        return "failed" if post.last_error else "pending"
    if post.scheduled_at and post.scheduled_at > datetime.now(timezone.utc):
        return "scheduled"
    if post.last_error:
        return "failed"
    return "pending"


def _broadcast_runtime_status(log: BroadcastLog) -> str:
    status = (log.status or "").strip().lower()
    if status in {"pending", "processing", "completed", "failed"}:
        return status
    if log.finished_at:
        return "completed"
    return "pending"


def _broadcast_media_label(media_type: str | None) -> str:
    return {
        None: "✉️ رسالة نصية",
        "photo": "🖼 صورة",
        "video": "🎥 فيديو",
        "document": "📎 ملف",
    }.get(media_type, "📣 إذاعة")


def _broadcast_media_from_waiting(waiting: str) -> tuple[str | None, str | None]:
    if waiting.startswith("bc_media_photo_"):
        return "photo", waiting.replace("bc_media_photo_", "")
    if waiting.startswith("bc_media_video_"):
        return "video", waiting.replace("bc_media_video_", "")
    if waiting.startswith("bc_media_document_"):
        return "document", waiting.replace("bc_media_document_", "")
    return None, None


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = SessionLocal()
    try:
        if not is_admin(user.id, db):
            await update.message.reply_text("🚫 ليس لديك صلاحية الوصول للوحة الإدارة.")
            return
        await update.message.reply_text(
            "🎛 **لوحة تحكم الإدارة**\n\nاختر القسم الذي تريد إدارته:",
            reply_markup=admin_main_keyboard(),
            parse_mode="Markdown"
        )
    finally:
        db.close()


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    db = SessionLocal()

    try:
        if not is_admin(user.id, db):
            await query.answer("🚫 ليس لديك صلاحية.", show_alert=True)
            return

        if data.startswith("ui_") or data == "adm_ui":
            handled = await dispatch_ui_callback(query, context, data)
            if handled:
                return

        handled = await dispatch_sub_callback(query, context)
        if handled:
            return

        if data == "adm_main":
            await query.edit_message_text(
                "🎛 **لوحة تحكم الإدارة**\n\nاختر القسم:",
                reply_markup=admin_main_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_users":
            await query.edit_message_text(
                "👥 **إدارة المستخدمين**\n\nاختر الإجراء:",
                reply_markup=users_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_admins":
            _admins_flow(context)
            await query.edit_message_text(
                "👮 **قسم إدارة المشرفين**\n\n"
                "من هنا يمكنك إضافة مشرفين، إدارة صلاحياتهم، متابعة نشاطهم، "
                "البحث عنهم، تعطيلهم أو تصدير قوائمهم.\n\nاختر الإجراء المطلوب:",
                reply_markup=admins_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "admins_add_menu":
            flow = _admins_flow(context)
            selected = flow.get("selected_admin_id")
            selected_user = db.query(User).filter_by(telegram_id=selected).first() if selected else None
            selected_name = selected_user.first_name if selected_user else "غير محدد"
            await query.edit_message_text(
                "➕ **إضافة مشرف جديد**\n\n"
                "لإضافة مشرف جديد، اتبع الخطوات التالية:\n"
                "1. تحديد المستخدم\n2. تحديد الصلاحيات\n3. تحديد الأقسام المسموح بها\n4. تأكيد الإضافة\n\n"
                f"👤 المستخدم المحدد حاليًا: {selected_name}\n"
                f"🆔 ID: `{selected or 'غير محدد'}`\n"
                f"⚙️ عدد الصلاحيات المحددة: {len(flow.get('selected_permissions', []))}\n"
                f"📂 عدد الأقسام المحددة: {len(flow.get('selected_sections', []))}",
                reply_markup=admin_add_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "admins_add_by_id":
            context.user_data["waiting_for"] = "add_admin_id_v2"
            await query.edit_message_text(
                "🆔 **إدخال ID المستخدم**\n\nأرسل الآن ID المستخدم الذي تريد ترقيته إلى مشرف.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ إلغاء العملية", callback_data="admins_cancel_add")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="admins_add_menu"),
                     InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
                ]),
                parse_mode="Markdown"
            )

        elif data == "admins_add_permissions":
            flow = _admins_flow(context)
            await query.edit_message_text(
                "⚙️ **تحديد صلاحيات المشرف**\n\n"
                "اختر الصلاحيات التي تريد منحها للمشرف. يمكن تحديد أكثر من صلاحية.",
                reply_markup=admin_perms_keyboard(flow.get("selected_permissions", [])),
                parse_mode="Markdown",
            )

        elif data == "admins_add_sections":
            flow = _admins_flow(context)
            await query.edit_message_text(
                "📂 **تحديد الأقسام المسموح بها**\n\n"
                "اختر الأقسام التي يمكن لهذا المشرف الوصول إليها داخل لوحة الإدارة.",
                reply_markup=admin_sections_keyboard(flow.get("selected_sections", [])),
                parse_mode="Markdown",
            )

        elif data == "admins_add_confirm":
            flow = _admins_flow(context)
            missing = []
            if not flow.get("selected_admin_id"):
                missing.append("- المستخدم")
            if not flow.get("selected_permissions"):
                missing.append("- الصلاحيات")
            if not flow.get("selected_sections"):
                missing.append("- الأقسام المسموح بها")
            if missing:
                await query.answer("⚠️ البيانات غير مكتملة", show_alert=True)
                await query.edit_message_text(
                    "⚠️ لا يمكن إضافة المشرف قبل استكمال البيانات التالية:\n" + "\n".join(missing),
                    reply_markup=admin_add_menu_keyboard(),
                )
            else:
                selected = db.query(User).filter_by(telegram_id=flow["selected_admin_id"]).first()
                name = (selected.first_name if selected else "غير معروف")
                warn = ""
                if _permission_section_mismatch(flow["selected_permissions"], flow["selected_sections"]):
                    warn = "\n\nℹ️ بعض الصلاحيات المحددة تتبع أقسامًا غير مسموح بها لهذا المشرف."
                await query.edit_message_text(
                    "✅ **تأكيد إضافة المشرف**\n\n"
                    "راجع البيانات التالية قبل التأكيد:\n\n"
                    f"- 👤 المستخدم: {name}\n"
                    f"- 🆔 ID: `{flow['selected_admin_id']}`\n"
                    f"- ⚙️ عدد الصلاحيات المحددة: {len(flow['selected_permissions'])}\n"
                    f"- 📂 عدد الأقسام المسموح بها: {len(flow['selected_sections'])}"
                    f"{warn}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ تأكيد نهائي", callback_data="admins_add_final_confirm")],
                        [InlineKeyboardButton("✏️ تعديل الصلاحيات", callback_data="admins_add_permissions"),
                         InlineKeyboardButton("📂 تعديل الأقسام", callback_data="admins_add_sections")],
                        [InlineKeyboardButton("👤 تغيير المستخدم", callback_data="admins_add_by_id")],
                        [InlineKeyboardButton("❌ إلغاء العملية", callback_data="admins_cancel_add")],
                        [InlineKeyboardButton("🔙 رجوع", callback_data="admins_add_menu"),
                         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
                    ]),
                    parse_mode="Markdown",
                )

        elif data == "admins_add_final_confirm":
            flow = _admins_flow(context)
            selected_id = flow.get("selected_admin_id")
            if not selected_id:
                await query.answer("⚠️ لم يتم تحديد المستخدم.", show_alert=True)
                return
            existing = db.query(AdminUser).filter_by(telegram_id=selected_id).first()
            if existing:
                await query.answer("ℹ️ هذا المستخدم مسجل بالفعل كمشرف.", show_alert=True)
                return
            user_obj = db.query(User).filter_by(telegram_id=selected_id).first()
            if not user_obj:
                await query.answer("❌ المستخدم غير موجود.", show_alert=True)
                return
            db.add(AdminUser(
                telegram_id=selected_id,
                username=user_obj.username,
                first_name=user_obj.first_name,
                permissions=flow.get("selected_permissions", []),
                allowed_sections=flow.get("selected_sections", []),
                is_active=True,
                added_by=query.from_user.id,
            ))
            db.commit()
            flow["selected_admin_id"] = None
            flow["selected_permissions"] = []
            flow["selected_sections"] = []
            await query.answer("✅ تم إضافة المشرف بنجاح.", show_alert=True)
            await _handle_admin_details(query, db, db.query(AdminUser).filter_by(telegram_id=selected_id).first().id)

        elif data == "admins_cancel_add":
            flow = _admins_flow(context)
            flow["selected_admin_id"] = None
            flow["selected_permissions"] = []
            flow["selected_sections"] = []
            context.user_data["waiting_for"] = None
            await query.edit_message_text(
                "❌ تم إلغاء عملية إضافة المشرف.",
                reply_markup=admins_menu_keyboard(),
            )

        elif data == "adm_sub":
            await sub3_main(query, context)

        elif data == "adm_publish":
            await query.edit_message_text(
                "📡 **قنوات ومجموعات النشر**\n\nاختر الإجراء:",
                reply_markup=publish_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_broadcast":
            await query.edit_message_text(
                "📣 **الإذاعة والإعلانات**\n\nاختر الإجراء:",
                reply_markup=broadcast_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_scheduled":
            await query.edit_message_text(
                "🗓 **النشر المجدول**\n\nاختر الإجراء:",
                reply_markup=scheduled_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_groups":
            await query.edit_message_text(
                "📂 **مجموعات القنوات والمجموعات**\n\nاختر الإجراء:",
                reply_markup=groups_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_antiflood":
            await query.edit_message_text(
                "🛡 **نظام منع الحظر**\n\nاختر الإجراء:",
                reply_markup=antiflood_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_stats":
            await query.edit_message_text(
                "📊 **الإحصائيات**\n\nاختر الإجراء:",
                reply_markup=stats_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_settings":
            await query.edit_message_text(
                "⚙️ **إعدادات البوت**\n\nاختر الإجراء:",
                reply_markup=settings_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_ui":
            await query.edit_message_text(
                "🧩 **إدارة واجهة المستخدم**\n\nاختر الإجراء:",
                reply_markup=ui_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data.startswith("adm_users_stats"):
            await _handle_users_stats(query, db)

        elif data.startswith("adm_users_list_"):
            page = int(data.split("_")[-1])
            await _handle_users_list(query, db, page)

        elif data == "adm_users_search":
            context.user_data["waiting_for"] = "search_user"
            await query.edit_message_text(
                "🔍 **البحث عن مستخدم**\n\nأرسل ID أو username المستخدم:",
                reply_markup=back_keyboard("adm_users"),
                parse_mode="Markdown"
            )

        elif data == "adm_users_export":
            await _handle_export_users(query, context, db)

        elif data == "adm_users_delete_inactive":
            await query.edit_message_text(
                "🧹 **حذف المستخدمين غير النشطين**\n\nاختر مدة الخمول:",
                reply_markup=delete_inactive_keyboard(),
                parse_mode="Markdown"
            )

        elif data.startswith("confirm_del_inactive_"):
            days = int(data.split("_")[-1])
            await _delete_inactive_users(query, db, days)

        elif data.startswith("adm_users_banned_"):
            page = int(data.split("_")[-1])
            await _handle_banned_users(query, db, page)

        elif data.startswith("unban_user_"):
            uid = int(data.split("_")[-1])
            await query.edit_message_text(
                f"⚠️ هل تريد إلغاء حظر المستخدم {uid}؟",
                reply_markup=confirm_keyboard(f"confirm_unban_{uid}", "adm_users")
            )

        elif data.startswith("confirm_unban_"):
            uid = int(data.split("_")[-1])
            user_obj = db.query(User).filter_by(id=uid).first()
            if user_obj:
                user_obj.status = UserStatus.ACTIVE
                db.commit()
                await query.answer("✅ تم إلغاء الحظر بنجاح", show_alert=True)
            await query.edit_message_text(
                "👥 **إدارة المستخدمين**", reply_markup=users_menu_keyboard(), parse_mode="Markdown"
            )

        elif data.startswith("adm_users_info"):
            context.user_data["waiting_for"] = "get_user_info"
            await query.edit_message_text(
                "👤 **جلب معلومات مستخدم**\n\nأرسل ID المستخدم:",
                reply_markup=back_keyboard("adm_users"),
                parse_mode="Markdown"
            )

        elif data.startswith("user_info_"):
            user_id = int(data.split("_")[-1])
            await _handle_user_details(query, db, user_id)

        elif data.startswith("ban_user_"):
            uid = int(data.split("_")[-1])
            await query.edit_message_text(
                f"⚠️ هل تريد حظر المستخدم {uid}؟",
                reply_markup=confirm_keyboard(f"confirm_ban_{uid}", "adm_users")
            )

        elif data.startswith("confirm_ban_"):
            uid = int(data.split("_")[-1])
            user_obj = db.query(User).filter_by(id=uid).first()
            if user_obj:
                user_obj.status = UserStatus.BANNED
                db.commit()
                await query.answer("🚫 تم حظر المستخدم", show_alert=True)
            await query.edit_message_text(
                "👥 **إدارة المستخدمين**", reply_markup=users_menu_keyboard(), parse_mode="Markdown"
            )

        elif data.startswith("delete_user_"):
            uid = int(data.split("_")[-1])
            await query.edit_message_text(
                f"⚠️ هل تريد حذف المستخدم {uid} نهائياً؟",
                reply_markup=confirm_keyboard(f"confirm_delete_user_{uid}", "adm_users")
            )

        elif data.startswith("confirm_delete_user_"):
            uid = int(data.split("_")[-1])
            user_obj = db.query(User).filter_by(id=uid).first()
            if user_obj:
                db.delete(user_obj)
                db.commit()
                await query.answer("🗑 تم حذف المستخدم", show_alert=True)
            await query.edit_message_text(
                "👥 **إدارة المستخدمين**", reply_markup=users_menu_keyboard(), parse_mode="Markdown"
            )

        elif data == "adm_admins_add":
            context.user_data["waiting_for"] = "add_admin_id"
            await query.edit_message_text(
                "➕ **إضافة مشرف جديد**\n\nأرسل ID المستخدم الذي تريد تعيينه مشرفاً:",
                reply_markup=back_keyboard("adm_admins"),
                parse_mode="Markdown"
            )

        elif data.startswith("adm_admins_list_"):
            page = int(data.split("_")[-1])
            await _handle_admins_list(query, db, page)

        elif data.startswith("admins_list_"):
            page = int(data.split("_")[-1])
            flow = _admins_flow(context)
            flow["current_page"] = page
            flow["current_filter"] = "all"
            await _handle_admins_list(query, db, page)

        elif data == "admins_manage_perms":
            await query.edit_message_text(
                "⚙️ **إدارة صلاحيات المشرفين**\n\n"
                "من هنا يمكنك اختيار مشرف ثم عرض صلاحياته أو تعديلها.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 اختيار من قائمة المشرفين", callback_data="admins_list_0"),
                     InlineKeyboardButton("🔍 البحث عن مشرف", callback_data="admins_search_menu")],
                    [InlineKeyboardButton("👤 عرض صلاحيات مشرف", callback_data="admins_view_selected_perms"),
                     InlineKeyboardButton("✏️ تعديل صلاحيات مشرف", callback_data="admins_edit_selected_perms")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins"),
                     InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
                ]),
                parse_mode="Markdown"
            )

        elif data == "admins_view_selected_perms":
            flow = _admins_flow(context)
            selected = flow.get("selected_admin_id")
            if not selected:
                await query.answer("⚠️ يجب اختيار مشرف أولًا.", show_alert=True)
                return
            admin_obj = db.query(AdminUser).filter_by(telegram_id=selected).first()
            if not admin_obj:
                await query.answer("❌ المشرف غير موجود.", show_alert=True)
                return
            perms = "\n".join([f"- ✅ {p}" for p in (admin_obj.permissions or [])]) or "- لا توجد صلاحيات"
            await query.edit_message_text(
                f"📊 **عرض صلاحيات المشرف**\n\nالصلاحيات الحالية:\n{perms}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ تعديل الصلاحيات", callback_data=f"edit_admin_perms_{admin_obj.id}")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="admins_manage_perms"),
                     InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
                ]),
                parse_mode="Markdown",
            )

        elif data == "admins_edit_selected_perms":
            flow = _admins_flow(context)
            selected = flow.get("selected_admin_id")
            if not selected:
                await query.answer("⚠️ يجب اختيار مشرف أولًا.", show_alert=True)
                return
            admin_obj = db.query(AdminUser).filter_by(telegram_id=selected).first()
            if not admin_obj:
                await query.answer("❌ المشرف غير موجود.", show_alert=True)
                return
            context.user_data["editing_admin_id"] = admin_obj.id
            context.user_data["selected_perms"] = list(admin_obj.permissions or [])
            await query.edit_message_text(
                "✏️ **تعديل صلاحيات المشرف**\n\nيمكنك الآن تعديل صلاحيات المشرف المحدد.",
                reply_markup=admin_perms_keyboard(context.user_data["selected_perms"]),
                parse_mode="Markdown",
            )

        elif data == "admins_search_menu":
            context.user_data["waiting_for"] = "search_admin_v2"
            await query.edit_message_text(
                "🔍 **البحث عن مشرف**\n\nاختر طريقة البحث:\n- عبر ID\n- عبر Username\n- عبر الاسم\n\nأرسل الآن قيمة البحث:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 عرض النتائج", callback_data="admins_search_results_0"),
                     InlineKeyboardButton("🧹 مسح البحث", callback_data="admins_search_clear")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins"),
                     InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
                ]),
                parse_mode="Markdown",
            )

        elif data.startswith("admins_search_results_"):
            page = int(data.split("_")[-1])
            results = context.user_data.get("admins_search_results", [])
            if not results:
                await query.answer("ℹ️ لا توجد نتائج بحث محفوظة حاليًا.", show_alert=True)
                return
            page = max(0, min(page, len(results) - 1))
            admin_obj = db.query(AdminUser).filter_by(id=results[page]).first()
            if not admin_obj:
                await query.answer("❌ النتيجة غير متاحة.", show_alert=True)
                return
            _admins_flow(context)["selected_admin_id"] = admin_obj.telegram_id
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admins_search_results_{page-1}"))
            if page < len(results) - 1:
                nav.append(InlineKeyboardButton("➡️ التالي", callback_data=f"admins_search_results_{page+1}"))
            kb = [[InlineKeyboardButton("👤 عرض المشرف", callback_data=f"admin_details_{admin_obj.id}")]]
            if nav:
                kb.append(nav)
            kb.extend([
                [InlineKeyboardButton("🧹 مسح البحث", callback_data="admins_search_clear")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="admins_search_menu"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
            ])
            await query.edit_message_text(
                "📋 **نتائج البحث**\n\n"
                f"👤 الاسم: {admin_obj.first_name or 'غير معروف'}\n"
                f"🆔 ID: `{admin_obj.telegram_id}`\n"
                f"🔗 Username: @{admin_obj.username or 'لا يوجد'}",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown",
            )

        elif data == "admins_search_clear":
            context.user_data.pop("admins_search_results", None)
            _admins_flow(context)["last_search_query"] = ""
            await query.answer("✅ تم مسح نتائج البحث الحالية.", show_alert=True)

        elif data.startswith("admins_activity_"):
            page = int(data.split("_")[-1])
            _admins_flow(context)["current_page"] = page
            await _handle_admins_activity(query, db)

        elif data.startswith("admins_disabled_"):
            page = int(data.split("_")[-1])
            _admins_flow(context)["current_page"] = page
            await _handle_disabled_admins(query, db)

        elif data == "admins_export_menu":
            await query.edit_message_text(
                "📥 **تصدير قائمة المشرفين**\n\nاختر صيغة التصدير المطلوبة:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📄 تصدير CSV", callback_data="admins_export_fmt_csv"),
                     InlineKeyboardButton("📄 تصدير TXT", callback_data="admins_export_fmt_txt")],
                    [InlineKeyboardButton("📄 تصدير JSON", callback_data="admins_export_fmt_json")],
                    [InlineKeyboardButton("📥 تحميل الملف", callback_data="admins_export_download")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins"),
                     InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
                ]),
                parse_mode="Markdown",
            )

        elif data.startswith("admins_export_fmt_"):
            fmt = data.split("_")[-1]
            context.user_data["admins_export_format"] = fmt
            await query.answer(f"✅ تم تحديد صيغة {fmt.upper()}. اضغط تحميل الملف.", show_alert=True)

        elif data == "admins_export_download":
            fmt = context.user_data.get("admins_export_format")
            if not fmt:
                await query.answer("⚠️ يرجى اختيار صيغة التصدير أولًا.", show_alert=True)
                return
            await _handle_export(query, context, db, fmt, "admins")

        elif data == "adm_admins_activity":
            await _handle_admins_activity(query, db)

        elif data == "adm_admins_disabled":
            await _handle_disabled_admins(query, db)

        elif data == "adm_admins_export":
            await _handle_export_admins(query, context, db)

        elif data.startswith("admin_details_"):
            admin_id = int(data.split("_")[-1])
            admin_obj = db.query(AdminUser).filter_by(id=admin_id).first()
            if admin_obj:
                _admins_flow(context)["selected_admin_id"] = admin_obj.telegram_id
            await _handle_admin_details(query, db, admin_id)

        elif data.startswith("disable_admin_"):
            admin_id = int(data.split("_")[-1])
            await query.edit_message_text(
                "⚠️ هل تريد تعطيل هذا المشرف؟",
                reply_markup=confirm_keyboard(f"confirm_disable_admin_{admin_id}", "adm_admins")
            )

        elif data.startswith("confirm_disable_admin_"):
            admin_id = int(data.split("_")[-1])
            admin_obj = db.query(AdminUser).filter_by(id=admin_id).first()
            if admin_obj:
                if admin_obj.telegram_id == query.from_user.id:
                    await query.answer("⚠️ لا يمكنك تعطيل حسابك الإداري الحالي.", show_alert=True)
                    return
                admin_obj.is_active = False
                db.commit()
                await query.answer("🚫 تم تعطيل المشرف", show_alert=True)
            await query.edit_message_text(
                "👮 **إدارة المشرفين**", reply_markup=admins_menu_keyboard(), parse_mode="Markdown"
            )

        elif data.startswith("enable_admin_"):
            admin_id = int(data.split("_")[-1])
            admin_obj = db.query(AdminUser).filter_by(id=admin_id).first()
            if admin_obj:
                admin_obj.is_active = True
                db.commit()
                await query.answer("✅ تم تفعيل المشرف", show_alert=True)
            await query.edit_message_text(
                "👮 **إدارة المشرفين**", reply_markup=admins_menu_keyboard(), parse_mode="Markdown"
            )

        elif data.startswith("delete_admin_"):
            admin_id = int(data.split("_")[-1])
            await query.edit_message_text(
                "⚠️ هل تريد حذف هذا المشرف نهائياً؟",
                reply_markup=confirm_keyboard(f"confirm_delete_admin_{admin_id}", "adm_admins")
            )

        elif data.startswith("confirm_delete_admin_"):
            admin_id = int(data.split("_")[-1])
            admin_obj = db.query(AdminUser).filter_by(id=admin_id).first()
            if admin_obj:
                if admin_obj.telegram_id == query.from_user.id:
                    await query.answer("⚠️ لا يمكنك حذف نفسك أثناء الجلسة الحالية.", show_alert=True)
                    return
                active_admins = db.query(AdminUser).filter_by(is_active=True).count()
                if admin_obj.is_active and active_admins <= 1:
                    await query.answer("⚠️ لا يمكن حذف آخر مشرف رئيسي في النظام.", show_alert=True)
                    return
                db.delete(admin_obj)
                db.commit()
                await query.answer("🗑 تم حذف المشرف", show_alert=True)
            await query.edit_message_text(
                "👮 **إدارة المشرفين**", reply_markup=admins_menu_keyboard(), parse_mode="Markdown"
            )

        elif data.startswith("edit_admin_perms_"):
            admin_id = int(data.split("_")[-1])
            admin_obj = db.query(AdminUser).filter_by(id=admin_id).first()
            if admin_obj:
                context.user_data["editing_admin_id"] = admin_id
                context.user_data["selected_perms"] = list(admin_obj.permissions or [])
                await query.edit_message_text(
                    f"⚙️ **تعديل صلاحيات المشرف**\n\nاضغط على الصلاحية لتفعيلها/إلغائها:",
                    reply_markup=admin_perms_keyboard(context.user_data["selected_perms"]),
                    parse_mode="Markdown"
                )

        elif data.startswith("toggle_perm_"):
            perm = data.replace("toggle_perm_", "")
            flow = _admins_flow(context)
            selected = context.user_data.get("selected_perms")
            if selected is None:
                selected = flow.get("selected_permissions", [])
            if perm in selected:
                selected.remove(perm)
            else:
                selected.append(perm)
            context.user_data["selected_perms"] = selected
            flow["selected_permissions"] = selected
            await query.edit_message_reply_markup(
                reply_markup=admin_perms_keyboard(selected)
            )
            await query.answer(
                f"{'🧹 تم إلغاء تحديد' if perm not in selected else '✅ تم تحديد'} صلاحية: {perm}",
                show_alert=False,
            )

        elif data == "perms_select_all":
            all_perms = [p.value for p in AdminPermission]
            context.user_data["selected_perms"] = all_perms
            flow = _admins_flow(context)
            flow["selected_permissions"] = all_perms
            await query.edit_message_reply_markup(
                reply_markup=admin_perms_keyboard(all_perms)
            )
            await query.answer("✅ تم تحديد جميع الصلاحيات.", show_alert=False)

        elif data == "perms_deselect_all":
            context.user_data["selected_perms"] = []
            flow = _admins_flow(context)
            flow["selected_permissions"] = []
            await query.edit_message_reply_markup(
                reply_markup=admin_perms_keyboard([])
            )
            await query.answer("✅ تم إلغاء تحديد جميع الصلاحيات.", show_alert=False)

        elif data == "perms_save":
            admin_id = context.user_data.get("editing_admin_id")
            new_admin_id = context.user_data.get("new_admin_id")
            flow = _admins_flow(context)
            selected = context.user_data.get("selected_perms", flow.get("selected_permissions", []))
            if not selected:
                await query.answer("⚠️ يجب تحديد صلاحية واحدة على الأقل.", show_alert=True)
                return
            if admin_id:
                admin_obj = db.query(AdminUser).filter_by(id=admin_id).first()
                if admin_obj:
                    admin_obj.permissions = selected
                    db.commit()
                    await query.answer("✅ تم حفظ الصلاحيات بنجاح", show_alert=True)
            elif new_admin_id:
                user_obj = db.query(User).filter_by(telegram_id=new_admin_id).first()
                if not user_obj:
                    logger.warning("perms_save: user telegram_id=%s not found in DB", new_admin_id)
                derived_sections = list({PERM_TO_SECTION[p] for p in selected if p in PERM_TO_SECTION})
                db.add(AdminUser(
                    telegram_id=new_admin_id,
                    username=user_obj.username if user_obj else None,
                    first_name=user_obj.first_name if user_obj else None,
                    permissions=selected,
                    allowed_sections=derived_sections,
                    is_active=True,
                    added_by=query.from_user.id,
                ))
                db.commit()
                await query.answer("✅ تم إنشاء المشرف وحفظ صلاحياته", show_alert=True)
            context.user_data.pop("editing_admin_id", None)
            context.user_data.pop("new_admin_id", None)
            context.user_data.pop("selected_perms", None)
            flow["selected_permissions"] = []
            await query.edit_message_text(
                "👮 **إدارة المشرفين**", reply_markup=admins_menu_keyboard(), parse_mode="Markdown"
            )

        elif data.startswith("admins_toggle_section_"):
            section = data.replace("admins_toggle_section_", "")
            flow = _admins_flow(context)
            selected = flow.get("selected_sections", [])
            if section in selected:
                selected.remove(section)
                msg = f"🧹 تم إلغاء السماح بالوصول إلى: {ADMIN_SECTIONS.get(section, section)}"
            else:
                selected.append(section)
                msg = f"✅ تم السماح بالوصول إلى: {ADMIN_SECTIONS.get(section, section)}"
            flow["selected_sections"] = selected
            await query.edit_message_reply_markup(reply_markup=admin_sections_keyboard(selected))
            await query.answer(msg, show_alert=False)

        elif data == "admins_sections_select_all":
            flow = _admins_flow(context)
            flow["selected_sections"] = list(ADMIN_SECTIONS.keys())
            await query.edit_message_reply_markup(reply_markup=admin_sections_keyboard(flow["selected_sections"]))
            await query.answer("✅ تم تحديد جميع الأقسام.", show_alert=False)

        elif data == "admins_sections_clear_all":
            flow = _admins_flow(context)
            flow["selected_sections"] = []
            await query.edit_message_reply_markup(reply_markup=admin_sections_keyboard([]))
            await query.answer("✅ تم إلغاء تحديد جميع الأقسام.", show_alert=False)

        elif data == "admins_sections_save":
            flow = _admins_flow(context)
            if not flow.get("selected_sections"):
                await query.answer("⚠️ يجب تحديد قسم واحد على الأقل.", show_alert=True)
                return
            await query.answer("✅ تم حفظ الأقسام المسموح بها بنجاح.", show_alert=True)
            await query.edit_message_text(
                "✅ تم حفظ الأقسام المسموح بها بنجاح.",
                reply_markup=admin_add_menu_keyboard(),
            )

        elif data == "admins_sections_cancel":
            _admins_flow(context)["selected_sections"] = []
            await query.edit_message_text(
                "❌ تم إلغاء عملية تحديد الأقسام.",
                reply_markup=admin_add_menu_keyboard(),
            )

        elif data == "adm_sub_add":
            await query.edit_message_text(
                "➕ **إضافة جهة اشتراك**\n\nاختر نوع الجهة:",
                reply_markup=add_sub_type_keyboard(),
                parse_mode="Markdown"
            )

        elif data in ("sub_add_channel", "sub_add_group", "sub_add_bot"):
            type_map = {"sub_add_channel": "channel", "sub_add_group": "group", "sub_add_bot": "bot"}
            context.user_data["waiting_for"] = "add_sub_entity"
            context.user_data["sub_add_type"] = type_map[data]
            await query.edit_message_text(
                "🔗 **إدخال رابط الجهة**\n\nأرسل رابط القناة/المجموعة أو @username:",
                reply_markup=back_keyboard("adm_sub"),
                parse_mode="Markdown"
            )

        elif data.startswith("adm_sub_list_"):
            page = int(data.split("_")[-1])
            await _handle_sub_list(query, db, page)

        elif data == "adm_sub_settings":
            enabled = get_setting("subscription_enabled", "true") == "true"
            status_text = "✅ مفعل" if enabled else "❌ معطل"
            await query.edit_message_text(
                f"⚙️ **إعدادات الاشتراك الإجباري**\n\nالحالة الحالية: {status_text}",
                reply_markup=sub_settings_keyboard(enabled),
                parse_mode="Markdown"
            )

        elif data == "sub_enable":
            if not _setting_saved("subscription_enabled", "true"):
                await query.answer("❌ تعذر حفظ إعداد الاشتراك الإجباري.", show_alert=True)
                return
            await query.edit_message_text(
                "⚙️ **إعدادات الاشتراك الإجباري**\n\nالحالة: ✅ مفعل",
                reply_markup=sub_settings_keyboard(True),
                parse_mode="Markdown"
            )
            await query.answer("✅ تم تفعيل الاشتراك الإجباري")

        elif data == "sub_disable":
            if not _setting_saved("subscription_enabled", "false"):
                await query.answer("❌ تعذر حفظ إعداد الاشتراك الإجباري.", show_alert=True)
                return
            await query.edit_message_text(
                "⚙️ **إعدادات الاشتراك الإجباري**\n\nالحالة: ❌ معطل",
                reply_markup=sub_settings_keyboard(False),
                parse_mode="Markdown"
            )
            await query.answer("🔓 تم تعطيل الاشتراك الإجباري")

        elif data.startswith("delete_sub_"):
            sub_id = int(data.split("_")[-1])
            await query.edit_message_text(
                "⚠️ هل تريد حذف هذه الجهة من قائمة الاشتراك الإجباري؟",
                reply_markup=confirm_keyboard(f"confirm_delete_sub_{sub_id}", "adm_sub")
            )

        elif data.startswith("confirm_delete_sub_"):
            sub_id = int(data.split("_")[-1])
            sub = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
            if sub:
                db.delete(sub)
                db.commit()
                await query.answer("🗑 تم حذف الجهة", show_alert=True)
            await query.edit_message_text(
                "📢 **إدارة الاشتراك الإجباري**", reply_markup=subscription_menu_keyboard(), parse_mode="Markdown"
            )

        elif data == "adm_sub_delete":
            await _handle_sub_list(query, db, 0)

        elif data.startswith("adm_pub_list_"):
            page = int(data.split("_")[-1])
            await _handle_pub_list(query, db, page)

        elif data == "adm_pub_add":
            context.user_data["waiting_for"] = "add_pub_entity"
            await query.edit_message_text(
                "➕ **إضافة جهة نشر**\n\nأرسل رابط القناة/المجموعة أو @username:",
                reply_markup=back_keyboard("adm_publish"),
                parse_mode="Markdown"
            )

        elif data.startswith("delete_pub_"):
            pub_id = int(data.split("_")[-1])
            await query.edit_message_text(
                "⚠️ هل تريد حذف هذه الجهة من قنوات النشر؟",
                reply_markup=confirm_keyboard(f"confirm_delete_pub_{pub_id}", "adm_publish")
            )

        elif data.startswith("confirm_delete_pub_"):
            pub_id = int(data.split("_")[-1])
            pub = db.query(PublishChannel).filter_by(id=pub_id).first()
            if pub:
                db.delete(pub)
                db.commit()
                await query.answer("🗑 تم حذف الجهة", show_alert=True)
            await query.edit_message_text(
                "📡 **قنوات النشر**", reply_markup=publish_menu_keyboard(), parse_mode="Markdown"
            )

        elif data == "adm_pub_delete":
            await _handle_pub_list(query, db, 0)

        elif data == "adm_bc_users":
            await query.edit_message_text(
                "👥 **إذاعة للمستخدمين**\n\nاختر الإجراء:",
                reply_markup=broadcast_compose_keyboard("users"),
                parse_mode="Markdown"
            )

        elif data == "adm_bc_channels":
            await query.edit_message_text(
                "📡 **إذاعة للقنوات والمجموعات**\n\nاختر الإجراء:",
                reply_markup=broadcast_compose_keyboard("channels"),
                parse_mode="Markdown"
            )

        elif data.startswith("bc_write_"):
            target = data.replace("bc_write_", "")
            context.user_data["waiting_for"] = f"bc_text_{target}"
            await query.edit_message_text(
                "✏️ **كتابة رسالة الإذاعة**\n\nأرسل نص الرسالة الآن:",
                reply_markup=back_keyboard("adm_broadcast"),
                parse_mode="Markdown"
            )

        elif data.startswith("bc_photo_") or data.startswith("bc_video_") or data.startswith("bc_file_"):
            prefix_map = {
                "bc_photo_": ("photo", "صورة"),
                "bc_video_": ("video", "فيديو"),
                "bc_file_": ("document", "ملف"),
            }
            prefix = next(key for key in prefix_map if data.startswith(key))
            media_type, label = prefix_map[prefix]
            target = data.replace(prefix, "")
            context.user_data["waiting_for"] = f"bc_media_{media_type}_{target}"
            await query.edit_message_text(
                f"📎 **إضافة {label} للإذاعة**\n\nأرسل {label} الآن. يمكنك إضافة نص في الـ caption أو كتابته لاحقاً.",
                reply_markup=back_keyboard("adm_broadcast"),
                parse_mode="Markdown"
            )

        elif data.startswith("bc_send_all_") or data.startswith("bc_send_active_"):
            target = data.split("_")[-1]
            context.user_data["bc_scope"] = "active" if data.startswith("bc_send_active_") else "all"
            await query.answer("✅ تم تحديث نطاق الإرسال", show_alert=True)
            await query.edit_message_text(
                "📣 **إعداد الإذاعة**\n\n"
                f"🎯 المستهدف: {'المستخدمين' if target == 'users' else 'القنوات'}\n"
                f"👥 النطاق: {'النشطين فقط' if context.user_data['bc_scope'] == 'active' else 'الكل'}\n"
                f"🧾 النوع: {_broadcast_media_label(context.user_data.get('bc_media_type'))}\n"
                f"📝 النص: {'موجود' if context.user_data.get('bc_text') else 'غير موجود'}",
                reply_markup=broadcast_compose_keyboard(target),
                parse_mode="Markdown"
            )

        elif data.startswith("bc_confirm_"):
            target = data.replace("bc_confirm_", "")
            bc_text = context.user_data.get("bc_text", "")
            media_type = context.user_data.get("bc_media_type")
            scope = context.user_data.get("bc_scope", "all")
            if not bc_text and not media_type:
                await query.answer("❌ أضف نصاً أو وسائط قبل الإرسال", show_alert=True)
                return
            await query.edit_message_text(
                "⚠️ **تأكيد الإرسال**\n\n"
                f"🧾 النوع: {_broadcast_media_label(media_type)}\n"
                f"🎯 المستهدف: {'المستخدمين' if target == 'users' else 'القنوات'}\n"
                f"👥 النطاق: {'النشطين فقط' if scope == 'active' else 'الكل'}\n"
                f"📝 الرسالة:\n{bc_text or 'بدون نص'}",
                reply_markup=confirm_keyboard(f"do_broadcast_{target}", "adm_broadcast"),
                parse_mode="Markdown"
            )

        elif data.startswith("do_broadcast_"):
            target = data.replace("do_broadcast_", "")
            await _do_broadcast(query, context, db, target)

        elif data.startswith("adm_bc_progress_"):
            log_id = int(data.split("_")[-1])
            await _handle_broadcast_progress(query, db, log_id)

        elif data == "adm_bc_create_ad":
            context.user_data["waiting_for"] = "ad_title"
            await query.edit_message_text(
                "📢 **إنشاء إعلان جديد**\n\nأرسل عنوان الإعلان:",
                reply_markup=back_keyboard("adm_broadcast"),
                parse_mode="Markdown"
            )

        elif data.startswith("adm_bc_saved_ads"):
            await _handle_saved_ads(query, db)

        elif data.startswith("adm_sched_list_"):
            page = int(data.split("_")[-1])
            await _handle_sched_list(query, db, page)

        elif data == "adm_sched_create":
            context.user_data["waiting_for"] = "sched_text"
            context.user_data["sched_data"] = {}
            await query.edit_message_text(
                "➕ **إنشاء منشور مجدول**\n\nأرسل نص المنشور:",
                reply_markup=back_keyboard("adm_scheduled"),
                parse_mode="Markdown"
            )

        elif data == "adm_sched_active":
            await _handle_active_scheduled(query, db)

        elif data == "adm_sched_pause":
            await _handle_active_scheduled(query, db)

        elif data == "adm_sched_resume":
            await _handle_inactive_scheduled(query, db)

        elif data == "adm_sched_delete":
            await _handle_sched_list(query, db, 0)

        elif data.startswith("sched_repeat_"):
            repeat_type = data.replace("sched_repeat_", "")
            await _create_scheduled_post(query, context, db, user.id, repeat_type)

        elif data.startswith("pause_sched_"):
            sched_id = int(data.split("_")[-1])
            sched = db.query(ScheduledPost).filter_by(id=sched_id).first()
            if sched:
                sched.is_active = False
                sched.queued_at = None
                db.commit()
                await query.answer("⏸ تم إيقاف المنشور", show_alert=True)
            await _handle_sched_list(query, db, 0)

        elif data.startswith("resume_sched_"):
            sched_id = int(data.split("_")[-1])
            sched = db.query(ScheduledPost).filter_by(id=sched_id).first()
            if sched:
                sched.is_active = True
                sched.queued_at = None
                sched.last_error = None
                db.commit()
                await query.answer("▶️ تم تشغيل المنشور", show_alert=True)
            await _handle_sched_list(query, db, 0)

        elif data.startswith("delete_sched_"):
            sched_id = int(data.split("_")[-1])
            await query.edit_message_text(
                "⚠️ هل تريد حذف هذا المنشور المجدول؟",
                reply_markup=confirm_keyboard(f"confirm_delete_sched_{sched_id}", "adm_scheduled")
            )

        elif data.startswith("confirm_delete_sched_"):
            sched_id = int(data.split("_")[-1])
            sched = db.query(ScheduledPost).filter_by(id=sched_id).first()
            if sched:
                db.delete(sched)
                db.commit()
                await query.answer("🗑 تم حذف المنشور", show_alert=True)
            await query.edit_message_text(
                "🗓 **النشر المجدول**", reply_markup=scheduled_menu_keyboard(), parse_mode="Markdown"
            )

        elif data.startswith("adm_grp_list_"):
            page = int(data.split("_")[-1])
            await _handle_groups_list(query, db, page)

        elif data == "adm_pub_groups":
            await _handle_publish_groups(query, db)

        elif data == "adm_grp_entities":
            await _handle_publish_groups(query, db)

        elif data == "adm_grp_delete":
            await _handle_groups_list(query, db, 0)

        elif data == "adm_grp_create":
            context.user_data["waiting_for"] = "create_group_name"
            await query.edit_message_text(
                "➕ **إنشاء مجموعة قنوات**\n\nأرسل اسم المجموعة:",
                reply_markup=back_keyboard("adm_groups"),
                parse_mode="Markdown"
            )

        elif data == "adm_grp_search":
            context.user_data["waiting_for"] = "search_group"
            await query.edit_message_text(
                "🔍 **البحث عن مجموعة**\n\nأرسل رقم المجموعة أو جزءاً من اسمها:",
                reply_markup=back_keyboard("adm_groups"),
                parse_mode="Markdown"
            )

        elif data == "adm_grp_edit":
            context.user_data["waiting_for"] = "rename_group"
            await query.edit_message_text(
                "✏️ **تعديل مجموعة**\n\nأرسل الرسالة بالصيغة:\n`معرف_المجموعة | الاسم الجديد`",
                reply_markup=back_keyboard("adm_groups"),
                parse_mode="Markdown"
            )

        elif data == "adm_grp_add_entity":
            context.user_data["waiting_for"] = "group_add_entity"
            await query.edit_message_text(
                "➕ **إضافة جهة إلى مجموعة**\n\nأرسل الرسالة بالصيغة:\n`معرف_المجموعة | معرف_جهة_النشر`",
                reply_markup=back_keyboard("adm_groups"),
                parse_mode="Markdown"
            )

        elif data.startswith("group_details_"):
            group_id = int(data.split("_")[-1])
            await _handle_group_details(query, db, group_id)

        elif data.startswith("delete_group_"):
            grp_id = int(data.split("_")[-1])
            await query.edit_message_text(
                "⚠️ هل تريد حذف هذه المجموعة؟",
                reply_markup=confirm_keyboard(f"confirm_delete_group_{grp_id}", "adm_groups")
            )

        elif data.startswith("confirm_delete_group_"):
            grp_id = int(data.split("_")[-1])
            grp = db.query(ChannelGroup).filter_by(id=grp_id).first()
            if grp:
                db.delete(grp)
                db.commit()
                await query.answer("🗑 تم حذف المجموعة", show_alert=True)
            await query.edit_message_text(
                "📂 **مجموعات القنوات**", reply_markup=groups_menu_keyboard(), parse_mode="Markdown"
            )

        elif data == "adm_af_speed":
            settings = db.query(AntiFloodSettings).first()
            current = settings.messages_per_minute if settings else 20
            await query.edit_message_text(
                f"⚡ **إعداد سرعة الإرسال**\n\nالإعداد الحالي: {current} رسائل/دقيقة\n\nاختر السرعة:",
                reply_markup=speed_keyboard(),
                parse_mode="Markdown"
            )

        elif data.startswith("af_speed_"):
            val = data.split("_")[-1]
            if val == "custom":
                context.user_data["waiting_for"] = "af_speed_custom"
                await query.edit_message_text(
                    "✏️ أرسل عدد الرسائل في الدقيقة:",
                    reply_markup=back_keyboard("adm_antiflood"),
                    parse_mode="Markdown"
                )
            else:
                speed = int(val)
                settings = db.query(AntiFloodSettings).first()
                if settings:
                    settings.messages_per_minute = speed
                    db.commit()
                await query.answer(f"✅ تم ضبط السرعة على {speed} رسائل/دقيقة", show_alert=True)
                await query.edit_message_text(
                    "🛡 **نظام منع الحظر**", reply_markup=antiflood_menu_keyboard(), parse_mode="Markdown"
                )

        elif data == "adm_af_delay":
            settings = db.query(AntiFloodSettings).first()
            current = settings.delay_between_messages if settings else 1.0
            await query.edit_message_text(
                f"⏳ **التأخير بين الرسائل**\n\nالتأخير الحالي: {current} ثانية\n\nاختر التأخير:",
                reply_markup=delay_keyboard(),
                parse_mode="Markdown"
            )

        elif data.startswith("af_delay_"):
            val = data.split("_")[-1]
            if val == "custom":
                context.user_data["waiting_for"] = "af_delay_custom"
                await query.edit_message_text(
                    "✏️ أرسل مدة التأخير بالثواني:",
                    reply_markup=back_keyboard("adm_antiflood"),
                    parse_mode="Markdown"
                )
            else:
                delay = float(val)
                settings = db.query(AntiFloodSettings).first()
                if settings:
                    settings.delay_between_messages = delay
                    db.commit()
                await query.answer(f"✅ تم ضبط التأخير على {delay} ثانية", show_alert=True)
                await query.edit_message_text(
                    "🛡 **نظام منع الحظر**", reply_markup=antiflood_menu_keyboard(), parse_mode="Markdown"
                )

        elif data == "adm_af_retry":
            settings = db.query(AntiFloodSettings).first()
            current = settings.retry_count if settings else 3
            await query.edit_message_text(
                f"🔁 **إعداد إعادة المحاولة**\n\nالإعداد الحالي: {current} مرات\n\nاختر:",
                reply_markup=retry_keyboard(),
                parse_mode="Markdown"
            )

        elif data.startswith("af_retry_"):
            val = data.split("_")[-1]
            if val == "custom":
                context.user_data["waiting_for"] = "af_retry_custom"
                await query.edit_message_text(
                    "✏️ أرسل عدد المحاولات:",
                    reply_markup=back_keyboard("adm_antiflood"),
                    parse_mode="Markdown"
                )
            else:
                retries = int(val)
                settings = db.query(AntiFloodSettings).first()
                if settings:
                    settings.retry_count = retries
                    db.commit()
                await query.answer(f"✅ تم ضبط المحاولات على {retries}", show_alert=True)
                await query.edit_message_text(
                    "🛡 **نظام منع الحظر**", reply_markup=antiflood_menu_keyboard(), parse_mode="Markdown"
                )

        elif data == "adm_af_reset":
            await query.edit_message_text(
                "⚠️ هل تريد إعادة ضبط إعدادات منع الحظر للقيم الافتراضية؟",
                reply_markup=confirm_keyboard("confirm_af_reset", "adm_antiflood")
            )

        elif data == "confirm_af_reset":
            settings = db.query(AntiFloodSettings).first()
            if settings:
                settings.messages_per_minute = 20
                settings.delay_between_messages = 1.0
                settings.retry_count = 3
                settings.ignore_inactive = True
                db.commit()
            await query.answer("✅ تم إعادة ضبط الإعدادات", show_alert=True)
            await query.edit_message_text(
                "🛡 **نظام منع الحظر**", reply_markup=antiflood_menu_keyboard(), parse_mode="Markdown"
            )

        elif data == "adm_af_monitor":
            total_users = db.query(User).count()
            active_users = db.query(User).filter_by(status=UserStatus.ACTIVE).count()
            settings = db.query(AntiFloodSettings).first()
            text = (
                "📊 **مراقبة الإرسال**\n\n"
                f"👥 إجمالي المستخدمين: {total_users}\n"
                f"✅ النشطين: {active_users}\n"
                f"⚡ السرعة الحالية: {settings.messages_per_minute if settings else 20} رسائل/دقيقة\n"
                f"⏳ التأخير: {settings.delay_between_messages if settings else 1.0} ثانية\n"
                f"🔁 المحاولات: {settings.retry_count if settings else 3}"
            )
            await query.edit_message_text(
                text,
                reply_markup=back_keyboard("adm_antiflood"),
                parse_mode="Markdown"
            )

        elif data == "adm_stats_users":
            await _handle_stats_users(query, db)

        elif data == "adm_stats_platforms":
            await _handle_stats_platforms(query, db)

        elif data == "adm_stats_broadcast":
            await _handle_stats_broadcast(query, db)

        elif data == "adm_stats_scheduled":
            await _handle_stats_scheduled(query, db)

        elif data == "adm_stats_refresh":
            await query.edit_message_text(
                "📊 **الإحصائيات**\n\nاختر الإجراء:",
                reply_markup=stats_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_stats_export":
            await query.edit_message_text(
                "📥 **تصدير الإحصائيات**\n\nاختر التنسيق:",
                reply_markup=export_keyboard("adm_stats"),
                parse_mode="Markdown"
            )

        elif data == "adm_set_activity":
            current = get_setting("activity_status", "upload_video")
            await query.edit_message_text(
                f"⚡ **حالة نشاط البوت**\n\nالحالة الحالية: {current}\n\nاختر الحالة:",
                reply_markup=activity_status_keyboard(),
                parse_mode="Markdown"
            )

        elif data.startswith("set_activity_"):
            activity = data.replace("set_activity_", "")
            if not _setting_saved("activity_status", activity):
                await query.answer("❌ تعذر حفظ حالة النشاط.", show_alert=True)
                return
            await query.edit_message_text(
                "⚙️ **إعدادات البوت**", reply_markup=settings_menu_keyboard(), parse_mode="Markdown"
            )
            await query.answer("✅ تم حفظ حالة النشاط")

        elif data == "adm_set_platforms":
            from .ui_handler import ui_platforms_main
            await ui_platforms_main(query, context)

        elif data == "adm_set_buttons":
            from .ui_handler import ui_buttons_main
            await ui_buttons_main(query, context)

        elif data == "adm_set_lang":
            from .ui_handler import ui_langs_main
            await ui_langs_main(query, context)

        elif data == "adm_set_download":
            settings = load_settings()
            await query.edit_message_text(
                "🧠 **إعدادات التحميل**\n\n"
                f"👷 حجم دفعة العامل: {settings.worker_batch_size}\n"
                f"⏱ فاصل العامل: {settings.worker_poll_interval} ثانية\n"
                f"🧹 تنظيف الملفات المؤقتة: {settings.temp_cleanup_hours} ساعة",
                reply_markup=back_keyboard("adm_settings"),
                parse_mode="Markdown"
            )

        elif data.startswith("toggle_"):
            from bot.utils.platforms import PLATFORMS
            from bot.database import set_setting
            platform_map = {f"toggle_{k}": f"{k}_enabled" for k in PLATFORMS}
            if data in platform_map:
                key = platform_map[data]
                current = get_setting(key, "true")
                new_val = "false" if current == "true" else "true"
                if not set_setting(key, new_val):
                    await query.answer("❌ تعذر حفظ حالة المنصة.", show_alert=True)
                    return
                from .ui_handler import ui_platforms_main
                await ui_platforms_main(query, context)
                await query.answer("✅ تم تحديث حالة المنصة")

        elif data == "adm_set_messages":
            await query.edit_message_text(
                "💬 **رسائل البوت**\n\nاختر الرسالة للتعديل:",
                reply_markup=messages_settings_keyboard(),
                parse_mode="Markdown"
            )

        elif data.startswith("edit_msg_"):
            msg_key = data.replace("edit_msg_", "")
            key_map = {
                "downloading": "downloading_message",
                "unsupported": "unsupported_message",
                "help": "help_message",
                "error": "error_message",
            }
            setting_key = key_map.get(msg_key, msg_key)
            current = get_setting(setting_key, "")
            context.user_data["waiting_for"] = f"edit_setting_{setting_key}"
            await query.edit_message_text(
                f"✏️ **تعديل الرسالة**\n\nالنص الحالي:\n{current}\n\nأرسل النص الجديد:",
                reply_markup=back_keyboard("adm_set_messages"),
                parse_mode="Markdown"
            )

        elif data == "adm_set_start_msg":
            current = get_setting("start_message", "")
            context.user_data["waiting_for"] = "edit_setting_start_message"
            await query.edit_message_text(
                f"👋 **تعديل رسالة البداية**\n\nالنص الحالي:\n{current}\n\nأرسل النص الجديد:\n(استخدم {{name}} لاسم المستخدم)",
                reply_markup=back_keyboard("adm_settings"),
                parse_mode="Markdown"
            )

        elif data == "adm_set_sub_msg":
            current = get_setting("subscription_message", "")
            context.user_data["waiting_for"] = "edit_setting_subscription_message"
            await query.edit_message_text(
                f"📢 **تعديل رسالة الاشتراك**\n\nالنص الحالي:\n{current}\n\nأرسل النص الجديد:",
                reply_markup=back_keyboard("adm_settings"),
                parse_mode="Markdown"
            )

        elif data == "adm_set_caption":
            current = get_setting("video_caption", "")
            context.user_data["waiting_for"] = "edit_setting_video_caption"
            await query.edit_message_text(
                f"📎 **Caption الوسائط**\n\nالنص الحالي:\n{current}\n\nأرسل النص الجديد:\n(استخدم {{bot_name}} لاسم البوت)",
                reply_markup=back_keyboard("adm_settings"),
                parse_mode="Markdown"
            )

        elif data == "adm_set_reset":
            await query.edit_message_text(
                "⚠️ هل تريد إعادة ضبط جميع إعدادات البوت للقيم الافتراضية؟",
                reply_markup=confirm_keyboard("confirm_settings_reset", "adm_settings")
            )

        elif data == "confirm_settings_reset":
            from bot.database.db import _seed_defaults
            _seed_defaults()
            await query.answer("✅ تم إعادة ضبط الإعدادات", show_alert=True)
            await query.edit_message_text(
                "⚙️ **إعدادات البوت**", reply_markup=settings_menu_keyboard(), parse_mode="Markdown"
            )

        elif data == "adm_ui_messages":
            await query.edit_message_text(
                "💬 **إدارة رسائل البوت**\n\nاختر الرسالة:",
                reply_markup=messages_settings_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_ui_activity":
            await query.edit_message_text(
                "⚡ **حالة نشاط البوت**\n\nاختر الحالة:",
                reply_markup=activity_status_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_ui_platforms":
            platform_settings = {
                "tiktok_enabled": get_setting("tiktok_enabled", "true"),
                "youtube_enabled": get_setting("youtube_enabled", "false"),
                "instagram_enabled": get_setting("instagram_enabled", "false"),
                "likee_enabled": get_setting("likee_enabled", "false"),
            }
            await query.edit_message_text(
                "🎵 **منصات التحميل**\n\nاضغط للتفعيل/التعطيل:",
                reply_markup=platforms_keyboard(platform_settings),
                parse_mode="Markdown"
            )

        elif data == "adm_ui_preview":
            bot_name = get_setting("bot_name", "SaveEliteBot")
            start_msg = get_setting("start_message", "")
            sub_msg = get_setting("subscription_message", "")
            preview = (
                f"👁 **معاينة الواجهة**\n\n"
                f"**رسالة البداية:**\n{start_msg[:200] if start_msg else 'غير محددة'}\n\n"
                f"**رسالة الاشتراك:**\n{sub_msg[:200] if sub_msg else 'غير محددة'}\n\n"
                f"**اسم البوت:** {bot_name}"
            )
            await query.edit_message_text(
                preview,
                reply_markup=back_keyboard("adm_ui"),
                parse_mode="Markdown"
            )

        elif data == "adm_ui_reset":
            await query.edit_message_text(
                "⚠️ هل تريد إعادة ضبط الواجهة للإعدادات الافتراضية؟",
                reply_markup=confirm_keyboard("confirm_ui_reset", "adm_ui")
            )

        elif data == "confirm_ui_reset":
            from bot.database.db import _seed_defaults
            _seed_defaults()
            await query.answer("✅ تم إعادة ضبط الواجهة", show_alert=True)
            await query.edit_message_text(
                "🧩 **إدارة واجهة المستخدم**", reply_markup=ui_menu_keyboard(), parse_mode="Markdown"
            )

        elif data.startswith("export_"):
            parts = data.split("_")
            fmt = parts[1]
            back_section = "_".join(parts[2:])
            await _handle_export(query, context, db, fmt, back_section)

        elif data == "adm_sub_check":
            channels = db.query(SubscriptionChannel).filter_by(is_active=True).all()
            if not channels:
                await query.answer("ℹ️ لا توجد قنوات اشتراك مضافة", show_alert=True)
                return
            await query.edit_message_text(
                f"🔍 **فحص الجهات**\n\nعدد الجهات: {len(channels)}\n\nيمكن فحص صلاحيات البوت يدوياً.",
                reply_markup=back_keyboard("adm_sub"),
                parse_mode="Markdown"
            )

        elif data == "adm_pub_stats":
            total_channels = db.query(PublishChannel).filter_by(is_active=True).count()
            total_posts = db.query(PublishChannel).with_entities(PublishChannel.post_count).all()
            total_pub = sum(p[0] for p in total_posts)
            text = (
                f"📊 **إحصائيات النشر**\n\n"
                f"📡 عدد القنوات: {total_channels}\n"
                f"📨 إجمالي المنشورات: {total_pub}"
            )
            await query.edit_message_text(text, reply_markup=back_keyboard("adm_publish"), parse_mode="Markdown")

        elif data == "adm_bc_reports":
            await _handle_bc_reports(query, db)

        elif data == "adm_sched_reports":
            await _handle_sched_reports(query, db)

        elif data == "adm_stats_channels":
            total = db.query(PublishChannel).count()
            active = db.query(PublishChannel).filter_by(is_active=True).count()
            groups = db.query(ChannelGroup).count()
            await query.edit_message_text(
                f"📡 **إحصائيات القنوات**\n\n"
                f"📡 إجمالي القنوات: {total}\n"
                f"✅ النشطة: {active}\n"
                f"📂 المجموعات: {groups}",
                reply_markup=back_keyboard("adm_stats"),
                parse_mode="Markdown"
            )

        elif data == "adm_stats_activity":
            total_downloads = db.query(User).with_entities(User.download_count).all()
            total_dl = sum(u[0] for u in total_downloads)
            stats = get_queue_stats()
            active_workers, stale_workers = _worker_health_summary(db)
            download_jobs = _job_type_counts(stats, DownloadService.job_type)
            broadcast_jobs = _job_type_counts(stats, DownloadService.broadcast_job_type)
            scheduled_jobs = _job_type_counts(stats, DownloadService.scheduled_post_job_type)
            await query.edit_message_text(
                f"📈 **إحصائيات النشاط**\n\n"
                f"📥 إجمالي التحميلات: {total_dl}\n"
                f"👷 العمال النشطون: {active_workers}\n"
                f"⚠️ العمال المتأخرون: {stale_workers}\n\n"
                f"📦 التنزيلات — انتظار: {download_jobs['pending']} | معالجة: {download_jobs['processing']} | إعادة: {download_jobs['retry']} | فشل: {download_jobs['failed']}\n"
                f"📣 الإذاعات — انتظار: {broadcast_jobs['pending']} | معالجة: {broadcast_jobs['processing']} | إعادة: {broadcast_jobs['retry']} | فشل: {broadcast_jobs['failed']}\n"
                f"🗓 المجدول — انتظار: {scheduled_jobs['pending']} | معالجة: {scheduled_jobs['processing']} | إعادة: {scheduled_jobs['retry']} | فشل: {scheduled_jobs['failed']}\n\n"
                f"⏱ أقدم مهمة جاهزة: {stats['oldest_ready_age_seconds']} ثانية",
                reply_markup=back_keyboard("adm_stats"),
                parse_mode="Markdown"
            )

        elif data == "sub_recheck":
            await query.answer("🔄 تم إعادة الفحص", show_alert=True)
            enabled = get_setting("subscription_enabled", "true") == "true"
            await query.edit_message_text(
                f"⚙️ **إعدادات الاشتراك**\nالحالة: {'✅ مفعل' if enabled else '❌ معطل'}",
                reply_markup=sub_settings_keyboard(enabled),
                parse_mode="Markdown"
            )

        elif data == "adm_sub_refresh":
            await sub3_main(query, context)

        elif data in ("adm_pub_refresh", "adm_grp_refresh", "adm_sched_refresh", "adm_bc_refresh"):
            section_map = {
                "adm_pub_refresh": ("adm_publish", "📡 **قنوات النشر**", publish_menu_keyboard),
                "adm_grp_refresh": ("adm_groups", "📂 **مجموعات القنوات**", groups_menu_keyboard),
                "adm_sched_refresh": ("adm_scheduled", "🗓 **النشر المجدول**", scheduled_menu_keyboard),
                "adm_bc_refresh": ("adm_broadcast", "📣 **الإذاعة والإعلانات**", broadcast_menu_keyboard),
            }
            _, text, kb_func = section_map[data]
            await query.edit_message_text(text, reply_markup=kb_func(), parse_mode="Markdown")

        elif data == "adm_admins_search":
            context.user_data["waiting_for"] = "search_admin"
            await query.edit_message_text(
                "🔍 **البحث عن مشرف**\n\nأرسل ID أو @username:",
                reply_markup=back_keyboard("adm_admins"),
                parse_mode="Markdown"
            )

        elif data == "adm_sub_backup":
            channels = db.query(SubscriptionChannel).filter_by(is_backup=True).all()
            if not channels:
                text = "📦 **جهات الاشتراك الاحتياطية**\n\nلا توجد جهات احتياطية بعد."
            else:
                text = "📦 **جهات الاشتراك الاحتياطية**\n\n"
                for ch in channels:
                    text += f"• {ch.title or ch.username or ch.chat_id}\n"
            await query.edit_message_text(text, reply_markup=back_keyboard("adm_sub"), parse_mode="Markdown")

        elif data == "adm_sub_by_members":
            channels = db.query(SubscriptionChannel).filter_by(is_active=True).all()
            text = "👥 **الجهات حسب عدد المشتركين**\n\n"
            if channels:
                for ch in channels:
                    text += f"• {ch.title or ch.username or ch.chat_id}\n"
            else:
                text += "لا توجد جهات مضافة."
            await query.edit_message_text(text, reply_markup=back_keyboard("adm_sub"), parse_mode="Markdown")

        elif data == "adm_pub_activity":
            channels = db.query(PublishChannel).order_by(PublishChannel.post_count.desc()).limit(10).all()
            text = "👥 **القنوات حسب النشاط**\n\n"
            if channels:
                for i, ch in enumerate(channels, 1):
                    text += f"{i}. {ch.title or ch.username or ch.chat_id} — {ch.post_count} منشور\n"
            else:
                text += "لا توجد قنوات نشر."
            await query.edit_message_text(text, reply_markup=back_keyboard("adm_publish"), parse_mode="Markdown")

        elif data == "adm_pub_check":
            await query.edit_message_text(
                "🔍 **فحص صلاحيات البوت**\n\nيرجى التأكد من أن البوت مشرف في القنوات المضافة.",
                reply_markup=back_keyboard("adm_publish"),
                parse_mode="Markdown"
            )

        elif data == "adm_af_inactive":
            settings = db.query(AntiFloodSettings).first()
            status = "✅ مفعل" if (settings and settings.ignore_inactive) else "❌ معطل"
            await query.edit_message_text(
                f"🚫 **تجاهل القنوات غير النشطة**\n\nالحالة: {status}",
                reply_markup=confirm_keyboard("toggle_ignore_inactive", "adm_antiflood"),
                parse_mode="Markdown"
            )

        elif data == "toggle_ignore_inactive":
            settings = db.query(AntiFloodSettings).first()
            if settings:
                settings.ignore_inactive = not settings.ignore_inactive
                db.commit()
                await query.answer("✅ تم تغيير الإعداد", show_alert=True)
            await query.edit_message_text(
                "🛡 **نظام منع الحظر**", reply_markup=antiflood_menu_keyboard(), parse_mode="Markdown"
            )

        elif data == "adm_af_errors":
            await query.edit_message_text(
                "📋 **سجل الأخطاء**\n\nلا توجد أخطاء مسجلة حالياً.",
                reply_markup=back_keyboard("adm_antiflood"),
                parse_mode="Markdown"
            )

        elif data == "adm_af_test":
            await query.edit_message_text(
                "🔍 **اختبار الإرسال**\n\nأضف @username أو رابط القناة لاختبار الإرسال:",
                reply_markup=back_keyboard("adm_antiflood"),
                parse_mode="Markdown"
            )

        elif data == "adm_users_channels":
            channels = db.query(SubscriptionChannel).filter_by(is_active=True).all()
            text = "📡 **القنوات حسب عدد المشتركين**\n\n"
            for ch in channels:
                text += f"• {ch.title or ch.username or ch.chat_id}\n"
            if not channels:
                text += "لا توجد قنوات اشتراك."
            await query.edit_message_text(text, reply_markup=back_keyboard("adm_users"), parse_mode="Markdown")

        elif data == "adm_users_top_channels":
            await query.edit_message_text(
                "🚀 **القنوات الأكثر جلباً للمستخدمين**\n\nهذه الميزة تحتاج ربط مصادر الجذب بالقنوات.",
                reply_markup=back_keyboard("adm_users"),
                parse_mode="Markdown"
            )

        elif data == "adm_users_send":
            context.user_data["waiting_for"] = "send_to_user_id"
            await query.edit_message_text(
                "📩 **إرسال رسالة لمستخدم**\n\nأرسل ID المستخدم أولاً:",
                reply_markup=back_keyboard("adm_users"),
                parse_mode="Markdown"
            )

        elif data == "adm_users_send_multi":
            context.user_data["waiting_for"] = "bc_text_users"
            context.user_data["bc_scope"] = "all"
            await query.edit_message_text(
                "📨 **إرسال رسالة لعدة مستخدمين**\n\nأرسل نص الرسالة:",
                reply_markup=back_keyboard("adm_users"),
                parse_mode="Markdown"
            )

        elif data == "adm_admins_perms":
            await query.edit_message_text(
                "⚙️ **إدارة صلاحيات المشرفين**\n\nاختر مشرفاً من قائمة المشرفين لتعديل صلاحياته.",
                reply_markup=back_keyboard("adm_admins"),
                parse_mode="Markdown"
            )

        elif data == "view_all_messages":
            msgs = {
                "رسالة البداية": get_setting("start_message", ""),
                "رسالة الاشتراك": get_setting("subscription_message", ""),
                "رسالة التحميل": get_setting("downloading_message", ""),
                "رابط غير مدعوم": get_setting("unsupported_message", ""),
                "المساعدة": get_setting("help_message", ""),
                "الخطأ": get_setting("error_message", ""),
            }
            text = "📋 **جميع رسائل البوت:**\n\n"
            for title, val in msgs.items():
                short = val[:50] + "..." if len(val) > 50 else val
                text += f"**{title}:** {short}\n\n"
            await query.edit_message_text(text, reply_markup=back_keyboard("adm_set_messages"), parse_mode="Markdown")

        elif data.startswith("adm_bc_saved_ads"):
            await _handle_saved_ads(query, db)

        elif data == "adm_bc_delete_ad":
            await _handle_saved_ads(query, db)

        elif data.startswith("view_ad_"):
            ad_id = int(data.split("_")[-1])
            ad = db.query(SavedAd).filter_by(id=ad_id).first()
            if not ad:
                await query.answer("❌ الإعلان غير موجود", show_alert=True)
                return
            await query.edit_message_text(
                "📢 **تفاصيل الإعلان**\n\n"
                f"🆔 المعرف: `{ad.id}`\n"
                f"🏷 العنوان: {ad.title or 'بدون عنوان'}\n"
                f"🧾 النوع: {_broadcast_media_label(ad.media_type)}\n"
                f"📨 مرات الإرسال: {ad.send_count}\n\n"
                f"{ad.text or 'بدون نص'}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🗑 حذف", callback_data=f"delete_ad_{ad.id}")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="adm_bc_saved_ads")],
                ]),
                parse_mode="Markdown"
            )

        elif data.startswith("delete_ad_"):
            ad_id = int(data.split("_")[-1])
            ad = db.query(SavedAd).filter_by(id=ad_id).first()
            if ad:
                db.delete(ad)
                db.commit()
                await query.answer("🗑 تم حذف الإعلان", show_alert=True)
            await _handle_saved_ads(query, db)

    except Exception as e:
        logger.error(f"Admin callback error for {data}: {e}", exc_info=True)
        try:
            await query.answer("❌ حدث خطأ. يرجى المحاولة مجدداً.", show_alert=True)
        except Exception:
            pass
    finally:
        db.close()


async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = update.effective_user
    db = SessionLocal()
    try:
        if not is_admin(user.id, db):
            return

        waiting = context.user_data.get("waiting_for")
        if not waiting:
            return

        if waiting.startswith("bc_media_"):
            media_type, target = _broadcast_media_from_waiting(waiting)
            file_id = None
            if media_type == "photo" and update.message.photo:
                file_id = update.message.photo[-1].file_id
            elif media_type == "video" and update.message.video:
                file_id = update.message.video.file_id
            elif media_type == "document" and update.message.document:
                file_id = update.message.document.file_id
            if not file_id or not target:
                await update.message.reply_text("❌ أرسل نوع الوسائط المطلوب فقط.")
                return
            context.user_data["bc_media_type"] = media_type
            context.user_data["bc_media_file_id"] = file_id
            if update.message.caption and not context.user_data.get("bc_text"):
                context.user_data["bc_text"] = update.message.caption.strip()
            context.user_data["waiting_for"] = None
            await update.message.reply_text(
                "✅ تم حفظ وسائط الإذاعة.\n\n"
                f"🧾 النوع: {_broadcast_media_label(media_type)}\n"
                f"📝 النص: {'موجود' if context.user_data.get('bc_text') else 'غير موجود'}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 تأكيد الإرسال", callback_data=f"bc_confirm_{target}")],
                    [InlineKeyboardButton("❌ إلغاء", callback_data="adm_broadcast")],
                ])
            )
            return

        text = (update.message.text or update.message.caption or "").strip()
        if not text:
            return

        if waiting and (
            waiting.startswith("ui_") or
            waiting.startswith("ui_msg_") or
            waiting.startswith("ui_btn_") or
            waiting.startswith("ui_wa_") or
            waiting.startswith("ui_lang_") or
            waiting.startswith("ui_plat_") or
            waiting.startswith("ui_caption_")
        ):
            handled = await ui_handle_message(update, context)
            if handled:
                return

        if waiting.startswith("sub3_"):
            handled = await sub3_handle_message(update, context)
            if handled:
                return

        if waiting == "add_admin_id":
            try:
                admin_tg_id = int(text)
                existing = db.query(AdminUser).filter_by(telegram_id=admin_tg_id).first()
                if existing:
                    existing.is_active = True
                    db.commit()
                    await update.message.reply_text(
                        "✅ المشرف موجود مسبقاً وتم تفعيله.",
                        reply_markup=admins_menu_keyboard()
                    )
                else:
                    context.user_data["new_admin_id"] = admin_tg_id
                    context.user_data["selected_perms"] = []
                    context.user_data["editing_admin_id"] = None
                    await update.message.reply_text(
                        f"✅ ID المستخدم: {admin_tg_id}\n\nالآن حدد الصلاحيات:",
                        reply_markup=admin_perms_keyboard([])
                    )
                context.user_data["waiting_for"] = None
            except ValueError:
                await update.message.reply_text("❌ يرجى إرسال ID صحيح (أرقام فقط).")
            return

        elif waiting == "add_admin_id_v2":
            if not text.isdigit():
                await update.message.reply_text("⚠️ الرجاء إرسال ID صحيح مكوّن من أرقام فقط.")
                return
            tg_id = int(text)
            user_obj = db.query(User).filter_by(telegram_id=tg_id).first()
            if not user_obj:
                await update.message.reply_text("❌ لم يتم العثور على مستخدم بهذا الـ ID.")
                return
            flow = _admins_flow(context)
            flow["selected_admin_id"] = tg_id
            context.user_data["waiting_for"] = None
            await update.message.reply_text(
                "✅ تم العثور على المستخدم بنجاح.\n\n"
                f"- 👤 الاسم: {user_obj.first_name or 'غير معروف'}\n"
                f"- 🆔 ID: {user_obj.telegram_id}\n"
                f"- 🔗 Username: @{user_obj.username or 'لا يوجد'}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ متابعة إضافة المشرف", callback_data="admins_add_menu")],
                    [InlineKeyboardButton("❌ إلغاء", callback_data="admins_cancel_add")],
                ])
            )
            return

        elif waiting == "perms_save_new":
            pass

        elif waiting == "add_sub_entity":
            chat_type = context.user_data.get("sub_add_type", "channel")
            username = text.replace("https://t.me/", "").replace("@", "").strip()
            try:
                chat = await context.bot.get_chat(f"@{username}" if not username.startswith("-") else username)
                sub = SubscriptionChannel(
                    chat_id=chat.id,
                    username=chat.username,
                    title=chat.title,
                    invite_link=chat.invite_link,
                    chat_type=chat_type,
                    is_active=True
                )
                db.add(sub)
                db.commit()
                await update.message.reply_text(
                    f"✅ تمت إضافة **{chat.title}** بنجاح.",
                    reply_markup=subscription_menu_keyboard(),
                    parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ: {e}\n\nتأكد أن البوت عضو في القناة.")
            context.user_data["waiting_for"] = None
            return

        elif waiting == "add_pub_entity":
            username = text.replace("https://t.me/", "").replace("@", "").strip()
            try:
                chat = await context.bot.get_chat(f"@{username}" if not username.startswith("-") else username)
                pub = PublishChannel(
                    chat_id=chat.id,
                    username=chat.username,
                    title=chat.title,
                    chat_type=chat.type,
                    is_active=True
                )
                db.add(pub)
                db.commit()
                await update.message.reply_text(
                    f"✅ تمت إضافة **{chat.title}** لقنوات النشر.",
                    reply_markup=publish_menu_keyboard(),
                    parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ: {e}")
            context.user_data["waiting_for"] = None
            return

        elif waiting == "create_group_name":
            grp = ChannelGroup(name=text)
            db.add(grp)
            db.commit()
            await update.message.reply_text(
                f"✅ تم إنشاء مجموعة **{text}** بنجاح.",
                reply_markup=groups_menu_keyboard(),
                parse_mode="Markdown"
            )
            context.user_data["waiting_for"] = None
            return

        elif waiting == "search_group":
            result = None
            if text.isdigit():
                result = db.query(ChannelGroup).filter_by(id=int(text)).first()
            else:
                result = db.query(ChannelGroup).filter(ChannelGroup.name.ilike(f"%{text}%")).first()
            if result:
                channels = db.query(PublishChannel).filter_by(group_id=result.id).order_by(PublishChannel.id.asc()).all()
                lines = "\n".join(
                    f"• {ch.title or ch.username or ch.chat_id} (ID: {ch.id})"
                    for ch in channels
                ) or "لا توجد جهات نشر داخل هذه المجموعة."
                await update.message.reply_text(
                    f"📂 **نتيجة البحث**\n\n"
                    f"🆔 المعرف: `{result.id}`\n"
                    f"🏷 الاسم: {result.name}\n"
                    f"📡 الجهات:\n{lines}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📂 التفاصيل", callback_data=f"group_details_{result.id}")],
                        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_groups")],
                    ]),
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ لم يتم العثور على المجموعة.")
            context.user_data["waiting_for"] = None
            return

        elif waiting == "rename_group":
            try:
                group_id_raw, new_name = [part.strip() for part in text.split("|", 1)]
                group = db.query(ChannelGroup).filter_by(id=int(group_id_raw)).first()
            except ValueError:
                group = None
            if not group or not new_name:
                await update.message.reply_text("❌ استخدم الصيغة: `معرف_المجموعة | الاسم الجديد`", parse_mode="Markdown")
                return
            group.name = new_name
            db.commit()
            context.user_data["waiting_for"] = None
            await update.message.reply_text(
                f"✅ تم تحديث اسم المجموعة إلى: {new_name}",
                reply_markup=groups_menu_keyboard(),
            )
            return

        elif waiting == "group_add_entity":
            try:
                group_id_raw, channel_id_raw = [part.strip() for part in text.split("|", 1)]
                group = db.query(ChannelGroup).filter_by(id=int(group_id_raw)).first()
                channel = db.query(PublishChannel).filter_by(id=int(channel_id_raw)).first()
            except ValueError:
                group = None
                channel = None
            if not group or not channel:
                await update.message.reply_text("❌ استخدم الصيغة: `معرف_المجموعة | معرف_جهة_النشر` مع معرفات صحيحة.", parse_mode="Markdown")
                return
            channel.group_id = group.id
            db.commit()
            context.user_data["waiting_for"] = None
            await update.message.reply_text(
                f"✅ تمت إضافة **{channel.title or channel.username or channel.chat_id}** إلى المجموعة **{group.name}**.",
                reply_markup=groups_menu_keyboard(),
                parse_mode="Markdown",
            )
            return

        elif waiting == "search_user":
            result = None
            if text.isdigit():
                result = db.query(User).filter_by(telegram_id=int(text)).first()
            else:
                uname = text.lstrip("@")
                result = db.query(User).filter_by(username=uname).first()
            if result:
                status_emoji = {"active": "✅", "banned": "🚫", "inactive": "⚪"}
                st = status_emoji.get(result.status.value, "❓")
                reply_text = (
                    f"👤 **معلومات المستخدم**\n\n"
                    f"🆔 ID: `{result.telegram_id}`\n"
                    f"👤 الاسم: {result.first_name or ''} {result.last_name or ''}\n"
                    f"📛 Username: @{result.username or 'لا يوجد'}\n"
                    f"🌍 اللغة: {result.language_code}\n"
                    f"📊 الحالة: {st} {result.status.value}\n"
                    f"📥 التحميلات: {result.download_count}\n"
                    f"📅 الانضمام: {result.joined_at.strftime('%Y-%m-%d') if result.joined_at else 'غير معروف'}"
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚫 حظر", callback_data=f"ban_user_{result.id}"),
                     InlineKeyboardButton("🗑 حذف", callback_data=f"delete_user_{result.id}")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="adm_users")]
                ])
                await update.message.reply_text(reply_text, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ لم يتم العثور على المستخدم.")
            context.user_data["waiting_for"] = None
            return

        elif waiting == "get_user_info":
            try:
                tg_id = int(text)
                result = db.query(User).filter_by(telegram_id=tg_id).first()
                if result:
                    reply_text = (
                        f"👤 **معلومات المستخدم**\n\n"
                        f"🆔 Telegram ID: `{result.telegram_id}`\n"
                        f"👤 الاسم: {result.first_name or ''} {result.last_name or ''}\n"
                        f"📛 Username: @{result.username or 'لا يوجد'}\n"
                        f"🌍 اللغة: {result.language_code}\n"
                        f"📊 الحالة: {result.status.value}\n"
                        f"📥 إجمالي التحميلات: {result.download_count}\n"
                        f"🎵 TikTok: {result.tiktok_count}\n"
                        f"📅 تاريخ الانضمام: {result.joined_at.strftime('%Y-%m-%d') if result.joined_at else 'غير معروف'}"
                    )
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🚫 حظر", callback_data=f"ban_user_{result.id}"),
                         InlineKeyboardButton("🗑 حذف", callback_data=f"delete_user_{result.id}")],
                        [InlineKeyboardButton("✅ إلغاء الحظر", callback_data=f"unban_user_{result.id}")],
                        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_users")]
                    ])
                    await update.message.reply_text(reply_text, reply_markup=keyboard, parse_mode="Markdown")
                else:
                    await update.message.reply_text("❌ لم يتم العثور على المستخدم.")
            except ValueError:
                await update.message.reply_text("❌ يرجى إرسال ID صحيح.")
            context.user_data["waiting_for"] = None
            return

        elif waiting and waiting.startswith("edit_setting_"):
            setting_key = waiting.replace("edit_setting_", "")
            if not _setting_saved(setting_key, text):
                await update.message.reply_text("❌ تعذر حفظ الإعداد. أعد المحاولة.")
                return
            await update.message.reply_text(
                f"✅ تم حفظ الإعداد بنجاح.",
                reply_markup=settings_menu_keyboard()
            )
            context.user_data["waiting_for"] = None
            return

        elif waiting and waiting.startswith("bc_text_"):
            target = waiting.replace("bc_text_", "")
            context.user_data["bc_text"] = text
            context.user_data["bc_target"] = target
            context.user_data["waiting_for"] = None
            await update.message.reply_text(
                f"✅ تم حفظ نص الرسالة.\n\nالرسالة:\n{text}\n\nاضغط تأكيد الإرسال من القائمة.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 تأكيد الإرسال", callback_data=f"bc_confirm_{target}"),
                     InlineKeyboardButton("❌ إلغاء", callback_data="adm_broadcast")]
                ])
            )
            return

        elif waiting == "send_to_user_id":
            try:
                tg_id = int(text)
                context.user_data["send_to_user_tg_id"] = tg_id
                context.user_data["waiting_for"] = "send_to_user_text"
                await update.message.reply_text(
                    f"✅ المستخدم: {tg_id}\n\nأرسل الرسالة الآن:"
                )
            except ValueError:
                await update.message.reply_text("❌ يرجى إرسال ID صحيح.")
            return

        elif waiting == "send_to_user_text":
            tg_id = context.user_data.get("send_to_user_tg_id")
            if tg_id:
                try:
                    await context.bot.send_message(chat_id=tg_id, text=text)
                    await update.message.reply_text("✅ تم إرسال الرسالة بنجاح.", reply_markup=users_menu_keyboard())
                except Exception as e:
                    await update.message.reply_text(f"❌ فشل الإرسال: {e}")
            context.user_data["waiting_for"] = None
            return

        elif waiting in ("af_speed_custom", "af_delay_custom", "af_retry_custom"):
            try:
                val = float(text)
                settings = db.query(AntiFloodSettings).first()
                if settings:
                    if waiting == "af_speed_custom":
                        settings.messages_per_minute = int(val)
                    elif waiting == "af_delay_custom":
                        settings.delay_between_messages = val
                    elif waiting == "af_retry_custom":
                        settings.retry_count = int(val)
                    db.commit()
                await update.message.reply_text(
                    "✅ تم حفظ الإعداد.",
                    reply_markup=antiflood_menu_keyboard()
                )
            except ValueError:
                await update.message.reply_text("❌ يرجى إرسال قيمة رقمية صحيحة.")
            context.user_data["waiting_for"] = None
            return

        elif waiting == "sched_text":
            channel_ids = DownloadService.default_scheduled_channel_ids()
            if not channel_ids:
                await update.message.reply_text(
                    "❌ لا توجد قنوات نشر نشطة حالياً. أضف قناة نشر ثم أعد المحاولة.",
                    reply_markup=scheduled_menu_keyboard(),
                )
                context.user_data["waiting_for"] = None
                context.user_data.pop("sched_data", None)
                return
            context.user_data["sched_data"] = {
                "text": text,
                "channel_ids": channel_ids,
            }
            context.user_data["waiting_for"] = "sched_time"
            await update.message.reply_text(
                "🗓 أرسل وقت النشر بصيغة:\n`2026-03-25 18:30`\n\nسيتم اعتماد التوقيت العالمي UTC.",
                parse_mode="Markdown",
            )
            return

        elif waiting == "sched_time":
            sched_data = context.user_data.get("sched_data") or {}
            try:
                scheduled_at = datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            except ValueError:
                await update.message.reply_text("❌ الصيغة غير صحيحة. استخدم الشكل: 2026-03-25 18:30")
                return

            if scheduled_at <= datetime.now(timezone.utc):
                await update.message.reply_text("❌ يجب أن يكون وقت النشر في المستقبل.")
                return

            sched_data["scheduled_at"] = scheduled_at
            context.user_data["sched_data"] = sched_data
            context.user_data["waiting_for"] = None
            await update.message.reply_text(
                "🔁 **تحديد تكرار المنشور**\n\nاختر نوع التكرار:",
                reply_markup=repeat_type_keyboard(),
                parse_mode="Markdown",
            )
            return

        elif waiting == "search_admin":
            result = None
            if text.isdigit():
                result = db.query(AdminUser).filter_by(telegram_id=int(text)).first()
            else:
                uname = text.lstrip("@")
                result = db.query(AdminUser).filter_by(username=uname).first()
            if result:
                perms = ", ".join(result.permissions or []) or "لا توجد"
                status_text = "✅ نشط" if result.is_active else "🚫 معطل"
                await update.message.reply_text(
                    f"👮 **معلومات المشرف**\n\n"
                    f"🆔 ID: `{result.telegram_id}`\n"
                    f"👤 الاسم: {result.first_name or 'غير معروف'}\n"
                    f"📊 الحالة: {status_text}\n"
                    f"⚙️ الصلاحيات: {perms}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✏️ تعديل الصلاحيات", callback_data=f"edit_admin_perms_{result.id}")],
                        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins")]
                    ]),
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ لم يتم العثور على المشرف.")
            context.user_data["waiting_for"] = None
            return

        elif waiting == "search_admin_v2":
            flow = _admins_flow(context)
            flow["last_search_query"] = text
            results = []
            if text.isdigit():
                rec = db.query(AdminUser).filter_by(telegram_id=int(text)).first()
                if rec:
                    results.append(rec.id)
            else:
                uname = text.lstrip("@").lower()
                rec = db.query(AdminUser).filter(func.lower(AdminUser.username) == uname).first()
                if rec:
                    results.append(rec.id)
                for item in db.query(AdminUser).filter(AdminUser.first_name.ilike(f"%{text}%")).limit(10).all():
                    if item.id not in results:
                        results.append(item.id)
            context.user_data["admins_search_results"] = results
            context.user_data["waiting_for"] = None
            if not results:
                await update.message.reply_text("❌ لم يتم العثور على أي نتائج مطابقة.")
                return
            if len(results) == 1:
                await update.message.reply_text("✅ تم العثور على المشرف.")
            else:
                await update.message.reply_text("✅ تم العثور على عدة نتائج مطابقة. استخدم زر (📋 عرض النتائج).")
            return

        elif waiting == "ad_title":
            context.user_data["ad_data"] = {"title": text}
            context.user_data["waiting_for"] = "ad_text"
            await update.message.reply_text("✅ تم حفظ العنوان.\n\nأرسل نص الإعلان:")
            return

        elif waiting == "ad_text":
            ad_data = context.user_data.get("ad_data", {})
            ad_data["text"] = text
            ad = SavedAd(
                title=ad_data.get("title", "بدون عنوان"),
                text=text,
                created_by=user.id
            )
            db.add(ad)
            db.commit()
            await update.message.reply_text(
                f"✅ تم حفظ الإعلان **{ad_data.get('title')}** بنجاح.",
                reply_markup=broadcast_menu_keyboard(),
                parse_mode="Markdown"
            )
            context.user_data["waiting_for"] = None
            return

    except Exception as e:
        logger.error(f"Admin message handler error: {e}", exc_info=True)
    finally:
        db.close()


async def _handle_users_stats(query, db):
    total = db.query(User).count()
    active = db.query(User).filter_by(status=UserStatus.ACTIVE).count()
    banned = db.query(User).filter_by(status=UserStatus.BANNED).count()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = db.query(User).filter(User.joined_at >= today).count()
    week_ago = today - timedelta(days=7)
    new_week = db.query(User).filter(User.joined_at >= week_ago).count()
    month_ago = today - timedelta(days=30)
    new_month = db.query(User).filter(User.joined_at >= month_ago).count()

    total_downloads = db.query(User).with_entities(User.download_count).all()
    dl_total = sum(u[0] for u in total_downloads)

    text = (
        f"📊 **إحصائيات المستخدمين**\n\n"
        f"👥 الإجمالي: {total}\n"
        f"✅ النشطين: {active}\n"
        f"🚫 المحظورين: {banned}\n\n"
        f"📅 الجدد اليوم: {new_today}\n"
        f"📅 الجدد هذا الأسبوع: {new_week}\n"
        f"📅 الجدد هذا الشهر: {new_month}\n\n"
        f"📥 إجمالي التحميلات: {dl_total}"
    )
    await query.edit_message_text(
        text,
        reply_markup=back_keyboard("adm_users"),
        parse_mode="Markdown"
    )


async def _handle_users_list(query, db, page: int):
    per_page = 5
    users = db.query(User).order_by(User.joined_at.desc()).offset(page * per_page).limit(per_page).all()
    total = db.query(User).count()

    if not users:
        await query.edit_message_text(
            "👥 لا يوجد مستخدمون.",
            reply_markup=back_keyboard("adm_users"),
            parse_mode="Markdown"
        )
        return

    text = f"📋 **قائمة المستخدمين** (صفحة {page + 1})\n\n"
    buttons = []
    for u in users:
        name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username or str(u.telegram_id)
        status_icon = "✅" if u.status == UserStatus.ACTIVE else "🚫"
        text += f"{status_icon} {name} | ID: `{u.telegram_id}` | ⬇️ {u.download_count}\n"
        buttons.append([
            InlineKeyboardButton(f"👤 {name[:20]}", callback_data=f"user_info_{u.id}"),
            InlineKeyboardButton("🚫 حظر", callback_data=f"ban_user_{u.id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_user_{u.id}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_users_list_{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_users_list_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_users"),
                    InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_banned_users(query, db, page: int):
    per_page = 5
    users = db.query(User).filter_by(status=UserStatus.BANNED).offset(page * per_page).limit(per_page).all()
    total = db.query(User).filter_by(status=UserStatus.BANNED).count()

    if not users:
        await query.edit_message_text(
            "🚫 لا يوجد مستخدمون محظورون.",
            reply_markup=back_keyboard("adm_users"),
            parse_mode="Markdown"
        )
        return

    text = f"🚫 **المستخدمون المحظورون** ({total} مستخدم)\n\n"
    buttons = []
    for u in users:
        name = f"{u.first_name or ''} {u.last_name or ''}".strip() or str(u.telegram_id)
        text += f"• {name} | `{u.telegram_id}`\n"
        buttons.append([
            InlineKeyboardButton(f"✅ إلغاء حظر {name[:15]}", callback_data=f"unban_user_{u.id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_user_{u.id}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_users_banned_{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_users_banned_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_users")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_user_details(query, db, user_id: int):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        await query.answer("❌ المستخدم غير موجود", show_alert=True)
        return

    status_emoji = {
        UserStatus.ACTIVE: "✅",
        UserStatus.BANNED: "🚫",
        UserStatus.INACTIVE: "⚪",
    }
    status_icon = status_emoji.get(user.status, "❓")
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or str(user.telegram_id)
    buttons = [
        [
            InlineKeyboardButton("🚫 حظر", callback_data=f"ban_user_{user.id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_user_{user.id}"),
        ]
    ]
    if user.status == UserStatus.BANNED:
        buttons.append([InlineKeyboardButton("✅ إلغاء الحظر", callback_data=f"unban_user_{user.id}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_users")])

    await query.edit_message_text(
        (
            f"👤 **معلومات المستخدم**\n\n"
            f"🆔 Telegram ID: `{user.telegram_id}`\n"
            f"👤 الاسم: {name}\n"
            f"📛 Username: @{user.username or 'لا يوجد'}\n"
            f"🌍 اللغة: {user.language_code}\n"
            f"📊 الحالة: {status_icon} {user.status.value}\n"
            f"📥 إجمالي التحميلات: {user.download_count}\n"
            f"🎵 TikTok: {user.tiktok_count}\n"
            f"📺 YouTube: {user.youtube_count}\n"
            f"📷 Instagram: {user.instagram_count}\n"
            f"❤️ Likee: {user.likee_count}\n"
            f"📅 تاريخ الانضمام: {user.joined_at.strftime('%Y-%m-%d') if user.joined_at else 'غير معروف'}"
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def _handle_admins_list(query, db, page: int):
    per_page = 5
    admins = db.query(AdminUser).offset(page * per_page).limit(per_page).all()
    total = db.query(AdminUser).count()

    if not admins:
        await query.edit_message_text(
            "📭 لا يوجد مشرفون حاليًا.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة مشرف", callback_data="admins_add_menu")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
            ]),
            parse_mode="Markdown"
        )
        return

    text = f"📋 **قائمة المشرفين** ({total})\n\n"
    buttons = []
    for a in admins:
        name = a.first_name or a.username or str(a.telegram_id)
        status = "✅" if a.is_active else "🚫"
        text += f"{status} {name} | `{a.telegram_id}`\n"
        buttons.append([
            InlineKeyboardButton(f"👤 {name[:15]}", callback_data=f"admin_details_{a.id}"),
            InlineKeyboardButton("✏️ صلاحيات", callback_data=f"edit_admin_perms_{a.id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_admin_{a.id}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_admins_list_{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_admins_list_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton("🔍 البحث عن مشرف", callback_data="admins_search_menu"),
        InlineKeyboardButton("🔄 تحديث القائمة", callback_data=f"admins_list_{page}")
    ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins"),
                    InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_admin_details(query, db, admin_id: int):
    admin = db.query(AdminUser).filter_by(id=admin_id).first()
    if not admin:
        await query.answer("❌ المشرف غير موجود", show_alert=True)
        return
    name = admin.first_name or admin.username or str(admin.telegram_id)
    perms = ", ".join(admin.permissions or []) or "لا توجد صلاحيات"
    status = "✅ نشط" if admin.is_active else "🚫 معطل"
    text = (
        f"👮 **معلومات المشرف**\n\n"
        f"🆔 ID: `{admin.telegram_id}`\n"
        f"👤 الاسم: {name}\n"
        f"📊 الحالة: {status}\n"
        f"⚙️ الصلاحيات: {perms}\n"
        f"📅 أُضيف: {admin.added_at.strftime('%Y-%m-%d') if admin.added_at else 'غير معروف'}"
    )
    buttons = [
        [InlineKeyboardButton("✏️ تعديل الصلاحيات", callback_data=f"edit_admin_perms_{admin_id}")],
        [InlineKeyboardButton("🚫 تعطيل", callback_data=f"disable_admin_{admin_id}"),
         InlineKeyboardButton("✅ تفعيل", callback_data=f"enable_admin_{admin_id}")],
        [InlineKeyboardButton("🗑 حذف", callback_data=f"delete_admin_{admin_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admins_list_0"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_admins_activity(query, db):
    admins = db.query(AdminUser).all()
    text = f"📊 **نشاط المشرفين**\n\nعدد المشرفين: {len(admins)}\n\n"
    for a in admins[:10]:
        name = a.first_name or a.username or str(a.telegram_id)
        last = a.last_active.strftime('%Y-%m-%d') if a.last_active else "لم يدخل"
        text += f"• {name}: آخر نشاط {last}\n"
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث البيانات", callback_data="admins_activity_0")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins"),
             InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
        ]),
        parse_mode="Markdown"
    )


async def _handle_disabled_admins(query, db):
    admins = db.query(AdminUser).filter_by(is_active=False).all()
    if not admins:
        await query.edit_message_text(
            "✅ لا يوجد مشرفون معطلون حاليًا.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
            ]),
            parse_mode="Markdown"
        )
        return
    text = f"🚫 **المشرفون المعطلون** ({len(admins)})\n\n"
    buttons = []
    for a in admins:
        name = a.first_name or a.username or str(a.telegram_id)
        text += f"• {name} | `{a.telegram_id}`\n"
        buttons.append([
            InlineKeyboardButton(f"✅ تفعيل {name[:15]}", callback_data=f"enable_admin_{a.id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_admin_{a.id}")
        ])
    buttons.append([InlineKeyboardButton("🔄 تحديث القائمة", callback_data="admins_disabled_0")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins"),
                    InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_sub_list(query, db, page: int):
    per_page = 5
    channels = db.query(SubscriptionChannel).filter_by(is_backup=False).offset(page * per_page).limit(per_page).all()
    total = db.query(SubscriptionChannel).filter_by(is_backup=False).count()

    if not channels:
        await query.edit_message_text(
            "📋 لا توجد جهات اشتراك مضافة.",
            reply_markup=back_keyboard("adm_sub"),
            parse_mode="Markdown"
        )
        return

    text = f"📋 **جهات الاشتراك الإجباري** ({total})\n\n"
    buttons = []
    for ch in channels:
        name = ch.title or ch.username or str(ch.chat_id)
        text += f"• {name}\n"
        buttons.append([
            InlineKeyboardButton(f"📡 {name[:20]}", url=f"https://t.me/{ch.username}" if ch.username else "https://t.me"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_sub_{ch.id}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_sub_list_{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_sub_list_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_sub")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_pub_list(query, db, page: int):
    per_page = 5
    channels = db.query(PublishChannel).offset(page * per_page).limit(per_page).all()
    total = db.query(PublishChannel).count()

    if not channels:
        await query.edit_message_text(
            "📡 لا توجد قنوات نشر مضافة.",
            reply_markup=back_keyboard("adm_publish"),
            parse_mode="Markdown"
        )
        return

    text = f"📡 **قنوات النشر** ({total})\n\n"
    buttons = []
    for ch in channels:
        name = ch.title or ch.username or str(ch.chat_id)
        text += f"• {name} | {ch.post_count} منشور\n"
        buttons.append([
            InlineKeyboardButton(f"📡 {name[:20]}", url=f"https://t.me/{ch.username}" if ch.username else "https://t.me"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_pub_{ch.id}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_pub_list_{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_pub_list_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_publish")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_sched_list(query, db, page: int):
    per_page = 5
    posts = db.query(ScheduledPost).order_by(ScheduledPost.scheduled_at).offset(page * per_page).limit(per_page).all()
    total = db.query(ScheduledPost).count()
    job_ids = [post.last_job_id for post in posts if post.last_job_id]
    job_status_by_id = {}
    if job_ids:
        for job in db.query(BackgroundJob).filter(BackgroundJob.id.in_(job_ids)).all():
            status = job.status.value if hasattr(job.status, "value") else str(job.status)
            job_status_by_id[job.id] = status

    if not posts:
        await query.edit_message_text(
            "🗓 لا توجد منشورات مجدولة.",
            reply_markup=back_keyboard("adm_scheduled"),
            parse_mode="Markdown"
        )
        return

    text = f"📋 **المنشورات المجدولة** ({total})\n\n"
    buttons = []
    for p in posts:
        status = _status_badge(_scheduled_runtime_status(p, job_status_by_id)) if p.is_active else "⏸ متوقف"
        short_text = (p.text or "بدون نص")[:30]
        sched_time = p.scheduled_at.strftime('%Y-%m-%d %H:%M') if p.scheduled_at else "غير محدد"
        fail_suffix = f" | ⚠️ {p.fail_count}" if p.fail_count else ""
        text += f"• {short_text} | {sched_time} | {status}{fail_suffix}\n"
        row = [
            InlineKeyboardButton("⏸ إيقاف" if p.is_active else "▶️ تشغيل",
                                 callback_data=f"{'pause' if p.is_active else 'resume'}_sched_{p.id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_sched_{p.id}")
        ]
        buttons.append(row)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_sched_list_{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_sched_list_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_scheduled")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_active_scheduled(query, db):
    posts = db.query(ScheduledPost).filter_by(is_active=True, is_sent=False).all()
    job_ids = [post.last_job_id for post in posts if post.last_job_id]
    job_status_by_id = {}
    if job_ids:
        for job in db.query(BackgroundJob).filter(BackgroundJob.id.in_(job_ids)).all():
            status = job.status.value if hasattr(job.status, "value") else str(job.status)
            job_status_by_id[job.id] = status
    if not posts:
        await query.edit_message_text(
            "⏱ لا توجد منشورات نشطة.",
            reply_markup=back_keyboard("adm_scheduled"),
            parse_mode="Markdown"
        )
        return
    text = f"⏱ **المنشورات النشطة** ({len(posts)})\n\n"
    buttons = []
    for p in posts:
        short = (p.text or "بدون نص")[:30]
        sched = p.scheduled_at.strftime('%Y-%m-%d %H:%M') if p.scheduled_at else "غير محدد"
        text += f"• {short} | {sched} | {_status_badge(_scheduled_runtime_status(p, job_status_by_id))}\n"
        buttons.append([
            InlineKeyboardButton(f"⏸ إيقاف", callback_data=f"pause_sched_{p.id}"),
            InlineKeyboardButton(f"🗑 حذف", callback_data=f"delete_sched_{p.id}")
        ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_scheduled")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_inactive_scheduled(query, db):
    posts = db.query(ScheduledPost).filter_by(is_active=False, is_sent=False).order_by(ScheduledPost.scheduled_at).all()
    if not posts:
        await query.edit_message_text(
            "▶️ لا توجد منشورات متوقفة حالياً.",
            reply_markup=back_keyboard("adm_scheduled"),
            parse_mode="Markdown"
        )
        return
    text = f"▶️ **المنشورات المتوقفة** ({len(posts)})\n\n"
    buttons = []
    for post in posts:
        when = post.scheduled_at.strftime('%Y-%m-%d %H:%M') if post.scheduled_at else "غير محدد"
        text += f"• {(post.text or 'بدون نص')[:30]} | {when}\n"
        buttons.append([InlineKeyboardButton("▶️ تشغيل", callback_data=f"resume_sched_{post.id}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_scheduled")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_publish_groups(query, db):
    groups = db.query(ChannelGroup).order_by(ChannelGroup.name.asc()).all()
    if not groups:
        await query.edit_message_text(
            "📂 لا توجد مجموعات نشر مضافة.",
            reply_markup=back_keyboard("adm_publish"),
            parse_mode="Markdown"
        )
        return
    text = "📂 **مجموعات النشر**\n\n"
    buttons = []
    for group in groups:
        count = db.query(PublishChannel).filter_by(group_id=group.id).count()
        text += f"• {group.name} — {count} جهة نشر\n"
        buttons.append([InlineKeyboardButton(f"📂 {group.name[:30]}", callback_data=f"group_details_{group.id}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_publish")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_group_details(query, db, group_id: int):
    group = db.query(ChannelGroup).filter_by(id=group_id).first()
    if not group:
        await query.answer("❌ المجموعة غير موجودة", show_alert=True)
        return
    channels = db.query(PublishChannel).filter_by(group_id=group.id).order_by(PublishChannel.id.asc()).all()
    lines = [
        f"• {(channel.title or channel.username or channel.chat_id)} (ID: {channel.id})"
        for channel in channels
    ] or ["لا توجد جهات نشر داخل هذه المجموعة."]
    await query.edit_message_text(
        f"📂 **تفاصيل المجموعة**\n\n"
        f"🆔 المعرف: `{group.id}`\n"
        f"🏷 الاسم: {group.name}\n"
        f"📡 عدد الجهات: {len(channels)}\n\n"
        + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة جهة", callback_data="adm_grp_add_entity")],
            [InlineKeyboardButton("✏️ تعديل", callback_data="adm_grp_edit"),
             InlineKeyboardButton("🗑 حذف", callback_data=f"delete_group_{group.id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="adm_groups")],
        ]),
        parse_mode="Markdown"
    )


async def _handle_groups_list(query, db, page: int):
    per_page = 5
    groups = db.query(ChannelGroup).offset(page * per_page).limit(per_page).all()
    total = db.query(ChannelGroup).count()

    if not groups:
        await query.edit_message_text(
            "📂 لا توجد مجموعات قنوات.",
            reply_markup=back_keyboard("adm_groups"),
            parse_mode="Markdown"
        )
        return

    text = f"📂 **مجموعات القنوات** ({total})\n\n"
    buttons = []
    for g in groups:
        channels_count = len(g.channels)
        text += f"• {g.name} ({channels_count} قناة)\n"
        buttons.append([
            InlineKeyboardButton(f"📂 {g.name[:20]}", callback_data=f"group_details_{g.id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_group_{g.id}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"adm_grp_list_{page - 1}"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"adm_grp_list_{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_groups")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_stats_scheduled(query, db):
    total = db.query(ScheduledPost).count()
    active = db.query(ScheduledPost).filter_by(is_active=True, is_sent=False).count()
    completed = db.query(ScheduledPost).filter_by(is_sent=True).count()
    failed = db.query(ScheduledPost).filter(ScheduledPost.last_error.isnot(None)).count()
    await query.edit_message_text(
        f"🗓 **إحصائيات النشر المجدول**\n\n"
        f"📋 الإجمالي: {total}\n"
        f"▶️ النشط: {active}\n"
        f"✅ المكتمل: {completed}\n"
        f"⚠️ الذي يحتوي أخطاء: {failed}",
        reply_markup=back_keyboard("adm_stats"),
        parse_mode="Markdown"
    )


async def _handle_stats_users(query, db):
    total = db.query(User).count()
    active = db.query(User).filter_by(status=UserStatus.ACTIVE).count()
    banned = db.query(User).filter_by(status=UserStatus.BANNED).count()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = db.query(User).filter(User.joined_at >= today).count()

    all_users = db.query(User).all()
    total_tiktok = sum(u.tiktok_count for u in all_users)

    text = (
        f"👥 **إحصائيات المستخدمين**\n\n"
        f"📊 الإجمالي: {total}\n"
        f"✅ النشطين: {active}\n"
        f"🚫 المحظورين: {banned}\n"
        f"📅 جدد اليوم: {new_today}\n\n"
        f"🎵 تحميلات TikTok: {total_tiktok}"
    )
    await query.edit_message_text(text, reply_markup=back_keyboard("adm_stats"), parse_mode="Markdown")


async def _handle_stats_platforms(query, db):
    rows = (
        db.query(Download.platform, func.count(Download.id))
        .filter(Download.success.is_(True))
        .group_by(Download.platform)
        .all()
    )
    counts = {platform: count for platform, count in rows}
    total = sum(counts.values())
    lines = [f"{info['emoji']} {info['name']}: {counts.get(key, 0)} تحميل" for key, info in PLATFORMS.items()]
    text = (
        f"🌐 **إحصائيات المنصات**\n\n"
        f"{chr(10).join(lines)}\n\n"
        f"📊 الإجمالي: {total} تحميل"
    )
    await query.edit_message_text(text, reply_markup=back_keyboard("adm_stats"), parse_mode="Markdown")


async def _handle_stats_broadcast(query, db):
    logs = db.query(BroadcastLog).order_by(BroadcastLog.started_at.desc()).limit(10).all()
    if not logs:
        text = "📣 **إحصائيات الإذاعة**\n\nلم يتم إجراء أي إذاعة بعد."
    else:
        text = f"📣 **إحصائيات الإذاعة** (آخر {len(logs)})\n\n"
        for log in logs:
            date = log.started_at.strftime('%Y-%m-%d') if log.started_at else ""
            success_rate = round(log.total_sent / max(log.total_sent + log.total_failed, 1) * 100)
            text += f"• {date}: {log.total_sent} نجح | {log.total_failed} فشل ({success_rate}%)\n"
    await query.edit_message_text(text, reply_markup=back_keyboard("adm_stats"), parse_mode="Markdown")


async def _handle_bc_reports(query, db):
    logs = db.query(BroadcastLog).order_by(BroadcastLog.started_at.desc()).limit(5).all()
    total_sent = sum(l.total_sent for l in logs)
    total_failed = sum(l.total_failed for l in logs)
    stats = get_queue_stats()
    broadcast_jobs = _job_type_counts(stats, DownloadService.broadcast_job_type)
    active_broadcasts = db.query(BroadcastLog).filter(BroadcastLog.status.in_(["pending", "processing"])).count()
    text = (
        f"📊 **تقارير الإذاعة**\n\n"
        f"📨 إجمالي المرسلة: {total_sent}\n"
        f"⚠️ إجمالي الفاشلة: {total_failed}\n"
        f"📊 عدد الإذاعات: {len(logs)}\n"
        f"🚦 الجارية الآن: {active_broadcasts}\n\n"
        f"⏳ مهام الإذاعة المعلقة: {broadcast_jobs['pending']}\n"
        f"⚙️ مهام الإذاعة قيد المعالجة: {broadcast_jobs['processing']}\n"
        f"🔁 إعادة المحاولة: {broadcast_jobs['retry']}\n"
        f"❌ مهام فاشلة: {broadcast_jobs['failed']}"
    )
    if logs:
        text += "\n\n📌 **آخر العمليات**\n"
        for log in logs:
            text += (
                f"• #{log.id} — {_status_badge(_broadcast_runtime_status(log))}"
                f" | ✅ {log.total_sent} | ❌ {log.total_failed}\n"
            )
    await query.edit_message_text(text, reply_markup=back_keyboard("adm_broadcast"), parse_mode="Markdown")


async def _handle_sched_reports(query, db):
    total = db.query(ScheduledPost).count()
    active = db.query(ScheduledPost).filter_by(is_active=True).count()
    sent = db.query(ScheduledPost).filter_by(is_sent=True).count()
    failed = db.query(ScheduledPost).filter(ScheduledPost.fail_count > 0).count()
    due_now = (
        db.query(ScheduledPost)
        .filter(
            ScheduledPost.is_active.is_(True),
            ScheduledPost.is_sent.is_(False),
            ScheduledPost.scheduled_at <= datetime.now(timezone.utc),
        )
        .count()
    )
    stats = get_queue_stats()
    scheduled_jobs = _job_type_counts(stats, DownloadService.scheduled_post_job_type)
    text = (
        f"📊 **تقارير النشر المجدول**\n\n"
        f"📨 إجمالي المنشورات: {total}\n"
        f"⏱ النشطة: {active}\n"
        f"✅ المُرسلة: {sent}\n"
        f"⚠️ الفاشلة: {failed}\n"
        f"🕒 المستحقة الآن: {due_now}\n\n"
        f"⏳ مهام النشر المعلقة: {scheduled_jobs['pending']}\n"
        f"⚙️ قيد المعالجة: {scheduled_jobs['processing']}\n"
        f"🔁 إعادة المحاولة: {scheduled_jobs['retry']}\n"
        f"❌ مهام فاشلة: {scheduled_jobs['failed']}"
    )
    await query.edit_message_text(text, reply_markup=back_keyboard("adm_scheduled"), parse_mode="Markdown")


async def _handle_broadcast_progress(query, db, log_id: int):
    log = db.query(BroadcastLog).filter_by(id=log_id).first()
    if not log:
        await query.answer("❌ لم يتم العثور على سجل الإذاعة", show_alert=True)
        return
    status = _broadcast_runtime_status(log)
    text = (
        f"📣 **تقدم الإذاعة #{log.id}**\n\n"
        f"🚦 الحالة: {_status_badge(status)}\n"
        f"✅ تم الإرسال: {log.total_sent}\n"
        f"❌ فشل: {log.total_failed}\n"
        f"🕒 بدأت: {log.started_at.strftime('%Y-%m-%d %H:%M') if log.started_at else 'غير معروف'}\n"
        f"🏁 انتهت: {log.finished_at.strftime('%Y-%m-%d %H:%M') if log.finished_at else 'لم تنتهِ بعد'}"
    )
    if log.error_message:
        text += f"\n⚠️ آخر خطأ: {log.error_message[:120]}"
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data=f"adm_bc_progress_{log.id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="adm_broadcast")],
        ]),
        parse_mode="Markdown",
    )


async def _handle_saved_ads(query, db):
    ads = db.query(SavedAd).order_by(SavedAd.created_at.desc()).limit(10).all()
    if not ads:
        await query.edit_message_text(
            "📋 لا توجد إعلانات محفوظة.",
            reply_markup=back_keyboard("adm_broadcast"),
            parse_mode="Markdown"
        )
        return
    text = f"📋 **الإعلانات المحفوظة** ({len(ads)})\n\n"
    buttons = []
    for ad in ads:
        short = (ad.text or "بدون نص")[:40]
        text += f"• {ad.title or 'بدون عنوان'}: {short}\n"
        buttons.append([
            InlineKeyboardButton(f"📢 {(ad.title or 'إعلان')[:20]}", callback_data=f"view_ad_{ad.id}"),
            InlineKeyboardButton("🗑 حذف", callback_data=f"delete_ad_{ad.id}")
        ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_broadcast")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _do_broadcast(query, context, db, target: str):
    bc_text = context.user_data.get("bc_text", "")
    scope = context.user_data.get("bc_scope", "all")
    media_type = context.user_data.get("bc_media_type")
    media_file_id = context.user_data.get("bc_media_file_id")
    if not bc_text and not media_type:
        await query.answer("❌ لا توجد رسالة أو وسائط", show_alert=True)
        return

    log = BroadcastLog(
        text=bc_text,
        target_type=target,
        total_sent=0,
        total_failed=0,
        sent_by=query.from_user.id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    job_id = DownloadService.enqueue_broadcast(
        text=bc_text,
        target=target,
        broadcast_log_id=log.id,
        offset=0,
        scope=scope,
        media_type=media_type,
        media_file_id=media_file_id,
    )
    log.status = "pending"
    log.last_job_id = job_id
    log.error_message = None
    db.commit()

    context.user_data.pop("bc_text", None)
    context.user_data.pop("bc_scope", None)
    context.user_data.pop("bc_media_type", None)
    context.user_data.pop("bc_media_file_id", None)
    await query.edit_message_text(
        f"✅ **تمت جدولة الإذاعة**\n\n"
        f"🆔 المهمة: `{job_id}`\n"
        f"📣 النوع: {target}\n"
        f"🧾 المحتوى: {_broadcast_media_label(media_type)}\n"
        f"👥 النطاق: {'النشطين فقط' if scope == 'active' else 'الكل'}\n"
        f"⏳ ستتم المعالجة في الخلفية بواسطة العامل.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 متابعة التقدم", callback_data=f"adm_bc_progress_{log.id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="adm_broadcast"),
             InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
        ]),
        parse_mode="Markdown"
    )


async def _create_scheduled_post(query, context, db, created_by: int, repeat_type: str):
    sched_data = context.user_data.get("sched_data") or {}
    scheduled_at = sched_data.get("scheduled_at")
    if not scheduled_at:
        await query.answer("❌ انتهت جلسة إنشاء المنشور. أعد المحاولة.", show_alert=True)
        await query.edit_message_text(
            "🗓 **النشر المجدول**\n\nاختر الإجراء:",
            reply_markup=scheduled_menu_keyboard(),
            parse_mode="Markdown"
        )
        return
    if not isinstance(scheduled_at, datetime):
        context.user_data.pop("sched_data", None)
        await query.answer("❌ وقت الجدولة غير صالح. أعد إنشاء المنشور.", show_alert=True)
        await query.edit_message_text(
            "🗓 **النشر المجدول**\n\nاختر الإجراء:",
            reply_markup=scheduled_menu_keyboard(),
            parse_mode="Markdown"
        )
        return
    post = ScheduledPost(
        text=sched_data.get("text"),
        channel_ids=sched_data.get("channel_ids") or [],
        scheduled_at=scheduled_at,
        repeat_type=repeat_type,
        is_active=True,
        is_sent=False,
        created_by=created_by,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    context.user_data.pop("sched_data", None)
    await query.edit_message_text(
        "✅ تم حفظ المنشور المجدول.\n\n"
        f"🆔 المعرف: {post.id}\n"
        f"🕒 الموعد: {scheduled_at.strftime('%Y-%m-%d %H:%M')} UTC\n"
        f"🔁 التكرار: {repeat_type}\n"
        f"📡 القنوات المستهدفة: {len(post.channel_ids or [])}\n"
        "⚙️ سيتم تحويله إلى مهمة خلفية عند حلول الموعد.",
        reply_markup=scheduled_menu_keyboard(),
        parse_mode="Markdown"
    )


async def _handle_export_users(query, context, db):
    users = db.query(User).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Telegram ID", "Username", "First Name", "Last Name", "Language", "Status", "Downloads", "Joined"])
    for u in users:
        writer.writerow([
            u.id, u.telegram_id, u.username or "", u.first_name or "",
            u.last_name or "", u.language_code, u.status.value,
            u.download_count, u.joined_at.strftime('%Y-%m-%d') if u.joined_at else ""
        ])
    output.seek(0)
    await context.bot.send_document(
        chat_id=query.from_user.id,
        document=output.getvalue().encode("utf-8"),
        filename="users.csv",
        caption=f"📥 تصدير المستخدمين - {len(users)} مستخدم"
    )
    await query.answer("✅ تم تصدير المستخدمين", show_alert=True)


async def _handle_export_admins(query, context, db):
    admins = db.query(AdminUser).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Telegram ID", "Username", "First Name", "Permissions", "Active", "Added"])
    for a in admins:
        writer.writerow([
            a.id, a.telegram_id, a.username or "", a.first_name or "",
            ", ".join(a.permissions or []), a.is_active,
            a.added_at.strftime('%Y-%m-%d') if a.added_at else ""
        ])
    output.seek(0)
    await context.bot.send_document(
        chat_id=query.from_user.id,
        document=output.getvalue().encode("utf-8"),
        filename="admins.csv",
        caption=f"📥 قائمة المشرفين - {len(admins)} مشرف"
    )
    await query.answer("✅ تم تصدير القائمة", show_alert=True)


async def _handle_export(query, context, db, fmt: str, section: str):
    if "users" in section:
        data = db.query(User).all()
        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["telegram_id", "username", "first_name", "status", "downloads"])
            for u in data:
                writer.writerow([u.telegram_id, u.username, u.first_name, u.status.value, u.download_count])
            file_content = output.getvalue().encode("utf-8")
            filename = "users.csv"
        elif fmt == "json":
            rows = [{"telegram_id": u.telegram_id, "username": u.username, "status": u.status.value} for u in data]
            file_content = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
            filename = "users.json"
        else:
            lines = [f"{u.telegram_id}\t{u.username or ''}\t{u.first_name or ''}" for u in data]
            file_content = "\n".join(lines).encode("utf-8")
            filename = "users.txt"

        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=file_content,
            filename=filename,
            caption=f"📥 تصدير البيانات - {len(data)} سجل"
        )
        await query.answer("✅ تم التصدير", show_alert=True)
    elif "admins" in section:
        data = db.query(AdminUser).all()
        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["telegram_id", "username", "first_name", "is_active", "permissions", "allowed_sections"])
            for a in data:
                writer.writerow([
                    a.telegram_id, a.username or "", a.first_name or "", a.is_active,
                    ",".join(a.permissions or []), ",".join(a.allowed_sections or [])
                ])
            file_content = output.getvalue().encode("utf-8")
            filename = "admins.csv"
        elif fmt == "json":
            rows = [{
                "telegram_id": a.telegram_id,
                "username": a.username,
                "first_name": a.first_name,
                "is_active": a.is_active,
                "permissions": a.permissions or [],
                "allowed_sections": a.allowed_sections or [],
            } for a in data]
            file_content = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
            filename = "admins.json"
        else:
            lines = [
                f"{a.telegram_id}\t{a.username or ''}\t{a.first_name or ''}\t{a.is_active}\t"
                f"{','.join(a.permissions or [])}\t{','.join(a.allowed_sections or [])}"
                for a in data
            ]
            file_content = "\n".join(lines).encode("utf-8")
            filename = "admins.txt"

        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=file_content,
            filename=filename,
            caption=f"📥 تصدير قائمة المشرفين - {len(data)} سجل"
        )
        await query.answer("✅ تم تجهيز الملف بنجاح.", show_alert=True)

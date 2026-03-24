import logging
import os
import csv
import json
import io
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database import (
    SessionLocal, User, AdminUser, SubscriptionChannel, PublishChannel,
    ChannelGroup, ScheduledPost, BroadcastLog, SavedAd, AntiFloodSettings,
    UserStatus, AdminPermission, get_setting, set_setting, AdminActivityLog
)
from bot.services import DownloadService
from .keyboards import (
    admin_main_keyboard, users_menu_keyboard, admins_menu_keyboard,
    subscription_menu_keyboard, publish_menu_keyboard, broadcast_menu_keyboard,
    scheduled_menu_keyboard, groups_menu_keyboard, antiflood_menu_keyboard,
    stats_menu_keyboard, settings_menu_keyboard, ui_menu_keyboard,
    back_keyboard, confirm_keyboard, export_keyboard, delete_inactive_keyboard,
    speed_keyboard, delay_keyboard, retry_keyboard, activity_status_keyboard,
    platforms_keyboard, sub_settings_keyboard, messages_settings_keyboard,
    add_sub_type_keyboard, broadcast_compose_keyboard, repeat_type_keyboard,
    auto_delete_keyboard, admin_perms_keyboard
)
from .ui_handler import dispatch_ui_callback, ui_handle_message

logger = logging.getLogger(__name__)

BOT_OWNER_ID = int(os.environ.get("BOT_OWNER_ID", "0"))


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
            await query.edit_message_text(
                "👮 **إدارة المشرفين**\n\nاختر الإجراء:",
                reply_markup=admins_menu_keyboard(),
                parse_mode="Markdown"
            )

        elif data == "adm_sub":
            await query.edit_message_text(
                "📢 **إدارة الاشتراك الإجباري**\n\nاختر الإجراء:",
                reply_markup=subscription_menu_keyboard(),
                parse_mode="Markdown"
            )

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

        elif data == "adm_admins_activity":
            await _handle_admins_activity(query, db)

        elif data == "adm_admins_disabled":
            await _handle_disabled_admins(query, db)

        elif data == "adm_admins_export":
            await _handle_export_admins(query, context, db)

        elif data.startswith("admin_details_"):
            admin_id = int(data.split("_")[-1])
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
            selected = context.user_data.get("selected_perms", [])
            if perm in selected:
                selected.remove(perm)
            else:
                selected.append(perm)
            context.user_data["selected_perms"] = selected
            await query.edit_message_reply_markup(
                reply_markup=admin_perms_keyboard(selected)
            )

        elif data == "perms_select_all":
            all_perms = [p.value for p in AdminPermission]
            context.user_data["selected_perms"] = all_perms
            await query.edit_message_reply_markup(
                reply_markup=admin_perms_keyboard(all_perms)
            )

        elif data == "perms_deselect_all":
            context.user_data["selected_perms"] = []
            await query.edit_message_reply_markup(
                reply_markup=admin_perms_keyboard([])
            )

        elif data == "perms_save":
            admin_id = context.user_data.get("editing_admin_id")
            selected = context.user_data.get("selected_perms", [])
            if admin_id:
                admin_obj = db.query(AdminUser).filter_by(id=admin_id).first()
                if admin_obj:
                    admin_obj.permissions = selected
                    db.commit()
                    await query.answer("✅ تم حفظ الصلاحيات بنجاح", show_alert=True)
            await query.edit_message_text(
                "👮 **إدارة المشرفين**", reply_markup=admins_menu_keyboard(), parse_mode="Markdown"
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
            set_setting("subscription_enabled", "true")
            await query.answer("✅ تم تفعيل الاشتراك الإجباري", show_alert=True)
            await query.edit_message_text(
                "⚙️ **إعدادات الاشتراك الإجباري**\n\nالحالة: ✅ مفعل",
                reply_markup=sub_settings_keyboard(True),
                parse_mode="Markdown"
            )

        elif data == "sub_disable":
            set_setting("subscription_enabled", "false")
            await query.answer("🔓 تم تعطيل الاشتراك الإجباري", show_alert=True)
            await query.edit_message_text(
                "⚙️ **إعدادات الاشتراك الإجباري**\n\nالحالة: ❌ معطل",
                reply_markup=sub_settings_keyboard(False),
                parse_mode="Markdown"
            )

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

        elif data.startswith("bc_confirm_"):
            target = data.replace("bc_confirm_", "")
            bc_text = context.user_data.get("bc_text", "")
            if not bc_text:
                await query.answer("❌ لم تكتب نص الرسالة بعد", show_alert=True)
                return
            await query.edit_message_text(
                f"⚠️ **تأكيد الإرسال**\n\nالرسالة:\n{bc_text}\n\nالمستهدف: {'المستخدمين' if target == 'users' else 'القنوات'}",
                reply_markup=confirm_keyboard(f"do_broadcast_{target}", "adm_broadcast"),
                parse_mode="Markdown"
            )

        elif data.startswith("do_broadcast_"):
            target = data.replace("do_broadcast_", "")
            await _do_broadcast(query, context, db, target)

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

        elif data.startswith("pause_sched_"):
            sched_id = int(data.split("_")[-1])
            sched = db.query(ScheduledPost).filter_by(id=sched_id).first()
            if sched:
                sched.is_active = False
                db.commit()
                await query.answer("⏸ تم إيقاف المنشور", show_alert=True)
            await _handle_sched_list(query, db, 0)

        elif data.startswith("resume_sched_"):
            sched_id = int(data.split("_")[-1])
            sched = db.query(ScheduledPost).filter_by(id=sched_id).first()
            if sched:
                sched.is_active = True
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

        elif data == "adm_grp_create":
            context.user_data["waiting_for"] = "create_group_name"
            await query.edit_message_text(
                "➕ **إنشاء مجموعة قنوات**\n\nأرسل اسم المجموعة:",
                reply_markup=back_keyboard("adm_groups"),
                parse_mode="Markdown"
            )

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
            set_setting("activity_status", activity)
            await query.answer("✅ تم حفظ حالة النشاط", show_alert=True)
            await query.edit_message_text(
                "⚙️ **إعدادات البوت**", reply_markup=settings_menu_keyboard(), parse_mode="Markdown"
            )

        elif data == "adm_set_platforms":
            from .ui_handler import ui_platforms_main
            await ui_platforms_main(query, context)

        elif data.startswith("toggle_"):
            from bot.utils.platforms import PLATFORMS
            from bot.database import set_setting
            platform_map = {f"toggle_{k}": f"{k}_enabled" for k in PLATFORMS}
            if data in platform_map:
                key = platform_map[data]
                current = get_setting(key, "true")
                new_val = "false" if current == "true" else "true"
                set_setting(key, new_val)
                from .ui_handler import ui_platforms_main
                await ui_platforms_main(query, context)

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
            await query.edit_message_text(
                f"📈 **إحصائيات النشاط**\n\n"
                f"📥 إجمالي التحميلات: {total_dl}",
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

        elif data in ("adm_sub_refresh", "adm_pub_refresh", "adm_grp_refresh", "adm_sched_refresh", "adm_bc_refresh"):
            section_map = {
                "adm_sub_refresh": ("adm_sub", "📢 **إدارة الاشتراك الإجباري**", subscription_menu_keyboard),
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
            await query.edit_message_text(
                "🗑 **حذف إعلان**\n\nاختر إعلاناً من القائمة المحفوظة لحذفه.",
                reply_markup=back_keyboard("adm_broadcast"),
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Admin callback error for {data}: {e}", exc_info=True)
        try:
            await query.answer("❌ حدث خطأ. يرجى المحاولة مجدداً.", show_alert=True)
        except Exception:
            pass
    finally:
        db.close()


async def admin_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    db = SessionLocal()
    try:
        if not is_admin(user.id, db):
            return

        waiting = context.user_data.get("waiting_for")
        if not waiting:
            return

        text = update.message.text.strip()

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
            set_setting(setting_key, text)
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


async def _handle_admins_list(query, db, page: int):
    per_page = 5
    admins = db.query(AdminUser).offset(page * per_page).limit(per_page).all()
    total = db.query(AdminUser).count()

    if not admins:
        await query.edit_message_text(
            "👮 لا يوجد مشرفون مضافون.",
            reply_markup=back_keyboard("adm_admins"),
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
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins")])

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
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def _handle_admins_activity(query, db):
    admins = db.query(AdminUser).all()
    text = f"📊 **نشاط المشرفين**\n\nعدد المشرفين: {len(admins)}\n\n"
    for a in admins[:10]:
        name = a.first_name or a.username or str(a.telegram_id)
        last = a.last_active.strftime('%Y-%m-%d') if a.last_active else "لم يدخل"
        text += f"• {name}: آخر نشاط {last}\n"
    await query.edit_message_text(text, reply_markup=back_keyboard("adm_admins"), parse_mode="Markdown")


async def _handle_disabled_admins(query, db):
    admins = db.query(AdminUser).filter_by(is_active=False).all()
    if not admins:
        await query.edit_message_text(
            "🚫 لا يوجد مشرفون معطلون.",
            reply_markup=back_keyboard("adm_admins"),
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
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins")])
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
        status = "✅ نشط" if p.is_active else "⏸ متوقف"
        short_text = (p.text or "بدون نص")[:30]
        sched_time = p.scheduled_at.strftime('%Y-%m-%d %H:%M') if p.scheduled_at else "غير محدد"
        text += f"• {short_text} | {sched_time} | {status}\n"
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
        text += f"• {short} | {sched}\n"
        buttons.append([
            InlineKeyboardButton(f"⏸ إيقاف", callback_data=f"pause_sched_{p.id}"),
            InlineKeyboardButton(f"🗑 حذف", callback_data=f"delete_sched_{p.id}")
        ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_scheduled")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


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
    users = db.query(User).all()
    tiktok = sum(u.tiktok_count for u in users)
    youtube = sum(u.youtube_count for u in users)
    instagram = sum(u.instagram_count for u in users)
    likee = sum(u.likee_count for u in users)
    total = tiktok + youtube + instagram + likee

    text = (
        f"🌐 **إحصائيات المنصات**\n\n"
        f"🎵 TikTok: {tiktok} تحميل\n"
        f"📺 YouTube: {youtube} تحميل\n"
        f"📷 Instagram: {instagram} تحميل\n"
        f"❤️ Likee: {likee} تحميل\n\n"
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
    text = (
        f"📊 **تقارير الإذاعة**\n\n"
        f"📨 إجمالي المرسلة: {total_sent}\n"
        f"⚠️ إجمالي الفاشلة: {total_failed}\n"
        f"📊 عدد الإذاعات: {len(logs)}"
    )
    await query.edit_message_text(text, reply_markup=back_keyboard("adm_broadcast"), parse_mode="Markdown")


async def _handle_sched_reports(query, db):
    total = db.query(ScheduledPost).count()
    active = db.query(ScheduledPost).filter_by(is_active=True).count()
    sent = db.query(ScheduledPost).filter_by(is_sent=True).count()
    failed = db.query(ScheduledPost).filter(ScheduledPost.fail_count > 0).count()
    text = (
        f"📊 **تقارير النشر المجدول**\n\n"
        f"📨 إجمالي المنشورات: {total}\n"
        f"⏱ النشطة: {active}\n"
        f"✅ المُرسلة: {sent}\n"
        f"⚠️ الفاشلة: {failed}"
    )
    await query.edit_message_text(text, reply_markup=back_keyboard("adm_scheduled"), parse_mode="Markdown")


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
    if not bc_text:
        await query.answer("❌ لا توجد رسالة", show_alert=True)
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
    )

    context.user_data["bc_text"] = ""
    await query.edit_message_text(
        f"✅ **تمت جدولة الإذاعة**\n\n"
        f"🆔 المهمة: `{job_id}`\n"
        f"📣 النوع: {target}\n"
        f"⏳ ستتم المعالجة في الخلفية بواسطة العامل.",
        reply_markup=back_keyboard("adm_broadcast"),
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

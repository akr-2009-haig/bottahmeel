from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_main_keyboard():
    buttons = [
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="adm_users"),
         InlineKeyboardButton("👮 إدارة المشرفين", callback_data="adm_admins")],
        [InlineKeyboardButton("📢 الاشتراك الإجباري", callback_data="adm_sub"),
         InlineKeyboardButton("📡 قنوات النشر", callback_data="adm_publish")],
        [InlineKeyboardButton("📣 الإذاعة والإعلانات", callback_data="adm_broadcast"),
         InlineKeyboardButton("🗓 النشر المجدول", callback_data="adm_scheduled")],
        [InlineKeyboardButton("📂 مجموعات القنوات", callback_data="adm_groups"),
         InlineKeyboardButton("🛡 نظام منع الحظر", callback_data="adm_antiflood")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm_stats"),
         InlineKeyboardButton("⚙️ إعدادات البوت", callback_data="adm_settings")],
        [InlineKeyboardButton("🧩 إدارة واجهة المستخدم", callback_data="adm_ui")],
    ]
    return InlineKeyboardMarkup(buttons)


def back_keyboard(back_to: str = "adm_main"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=back_to),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def back_only(back_to: str = "adm_main"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=back_to)]
    ])


def confirm_keyboard(confirm_cb: str, cancel_cb: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ تأكيد", callback_data=confirm_cb),
         InlineKeyboardButton("❌ إلغاء العملية", callback_data=cancel_cb)]
    ])


def users_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("📊 إحصائيات المستخدمين", callback_data="adm_users_stats"),
         InlineKeyboardButton("📋 عرض المستخدمين", callback_data="adm_users_list_0")],
        [InlineKeyboardButton("🔍 البحث عن مستخدم", callback_data="adm_users_search"),
         InlineKeyboardButton("👤 جلب معلومات مستخدم", callback_data="adm_users_info")],
        [InlineKeyboardButton("📡 القنوات حسب المشتركين", callback_data="adm_users_channels"),
         InlineKeyboardButton("🚀 القنوات الأكثر جلباً", callback_data="adm_users_top_channels")],
        [InlineKeyboardButton("🚫 المستخدمين المحظورين", callback_data="adm_users_banned_0"),
         InlineKeyboardButton("📩 إرسال رسالة لمستخدم", callback_data="adm_users_send")],
        [InlineKeyboardButton("📨 إرسال لعدة مستخدمين", callback_data="adm_users_send_multi"),
         InlineKeyboardButton("🧹 حذف غير النشطين", callback_data="adm_users_delete_inactive")],
        [InlineKeyboardButton("📥 تصدير المستخدمين", callback_data="adm_users_export")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def admins_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("➕ إضافة مشرف", callback_data="adm_admins_add"),
         InlineKeyboardButton("📋 قائمة المشرفين", callback_data="adm_admins_list_0")],
        [InlineKeyboardButton("⚙️ إدارة الصلاحيات", callback_data="adm_admins_perms"),
         InlineKeyboardButton("📊 نشاط المشرفين", callback_data="adm_admins_activity")],
        [InlineKeyboardButton("🚫 المشرفين المعطلين", callback_data="adm_admins_disabled"),
         InlineKeyboardButton("🔍 البحث عن مشرف", callback_data="adm_admins_search")],
        [InlineKeyboardButton("📥 تصدير القائمة", callback_data="adm_admins_export")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def subscription_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("➕ إضافة جهة اشتراك", callback_data="adm_sub_add"),
         InlineKeyboardButton("📋 عرض الجهات", callback_data="adm_sub_list_0")],
        [InlineKeyboardButton("📦 جهات احتياطية", callback_data="adm_sub_backup"),
         InlineKeyboardButton("👥 الجهات حسب المشتركين", callback_data="adm_sub_by_members")],
        [InlineKeyboardButton("⚙️ إعدادات الاشتراك", callback_data="adm_sub_settings"),
         InlineKeyboardButton("🔍 فحص الجهات", callback_data="adm_sub_check")],
        [InlineKeyboardButton("🗑 حذف جهة", callback_data="adm_sub_delete"),
         InlineKeyboardButton("🔄 تحديث الجهات", callback_data="adm_sub_refresh")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def publish_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("➕ إضافة جهة نشر", callback_data="adm_pub_add"),
         InlineKeyboardButton("📋 عرض جهات النشر", callback_data="adm_pub_list_0")],
        [InlineKeyboardButton("📂 مجموعات النشر", callback_data="adm_pub_groups"),
         InlineKeyboardButton("👥 القنوات حسب النشاط", callback_data="adm_pub_activity")],
        [InlineKeyboardButton("🔍 فحص صلاحيات البوت", callback_data="adm_pub_check"),
         InlineKeyboardButton("📊 إحصائيات النشر", callback_data="adm_pub_stats")],
        [InlineKeyboardButton("🗑 حذف جهة نشر", callback_data="adm_pub_delete"),
         InlineKeyboardButton("🔄 تحديث الجهات", callback_data="adm_pub_refresh")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def broadcast_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("👥 إذاعة للمستخدمين", callback_data="adm_bc_users"),
         InlineKeyboardButton("📡 إذاعة للقنوات", callback_data="adm_bc_channels")],
        [InlineKeyboardButton("📢 إنشاء إعلان", callback_data="adm_bc_create_ad"),
         InlineKeyboardButton("📋 الإعلانات المحفوظة", callback_data="adm_bc_saved_ads")],
        [InlineKeyboardButton("📊 تقارير الإذاعة", callback_data="adm_bc_reports"),
         InlineKeyboardButton("🗑 حذف إعلان", callback_data="adm_bc_delete_ad")],
        [InlineKeyboardButton("🔄 تحديث الإعلانات", callback_data="adm_bc_refresh")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def scheduled_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("➕ إنشاء منشور مجدول", callback_data="adm_sched_create"),
         InlineKeyboardButton("📋 قائمة المنشورات", callback_data="adm_sched_list_0")],
        [InlineKeyboardButton("📊 تقارير الجدولة", callback_data="adm_sched_reports"),
         InlineKeyboardButton("⏱ المنشورات النشطة", callback_data="adm_sched_active")],
        [InlineKeyboardButton("⏸ إيقاف منشور", callback_data="adm_sched_pause"),
         InlineKeyboardButton("▶️ تشغيل منشور", callback_data="adm_sched_resume")],
        [InlineKeyboardButton("🗑 حذف منشور", callback_data="adm_sched_delete"),
         InlineKeyboardButton("🔄 تحديث القائمة", callback_data="adm_sched_refresh")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def groups_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("➕ إنشاء مجموعة", callback_data="adm_grp_create"),
         InlineKeyboardButton("📋 عرض المجموعات", callback_data="adm_grp_list_0")],
        [InlineKeyboardButton("➕ إضافة جهة لمجموعة", callback_data="adm_grp_add_entity"),
         InlineKeyboardButton("📡 عرض جهات المجموعة", callback_data="adm_grp_entities")],
        [InlineKeyboardButton("✏️ تعديل مجموعة", callback_data="adm_grp_edit"),
         InlineKeyboardButton("🗑 حذف مجموعة", callback_data="adm_grp_delete")],
        [InlineKeyboardButton("🔍 البحث عن مجموعة", callback_data="adm_grp_search"),
         InlineKeyboardButton("🔄 تحديث المجموعات", callback_data="adm_grp_refresh")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def antiflood_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("⚡ إعداد سرعة الإرسال", callback_data="adm_af_speed"),
         InlineKeyboardButton("⏳ التأخير بين الرسائل", callback_data="adm_af_delay")],
        [InlineKeyboardButton("🔁 إعداد إعادة المحاولة", callback_data="adm_af_retry"),
         InlineKeyboardButton("🚫 تجاهل القنوات غير النشطة", callback_data="adm_af_inactive")],
        [InlineKeyboardButton("📊 مراقبة الإرسال", callback_data="adm_af_monitor"),
         InlineKeyboardButton("📋 سجل الأخطاء", callback_data="adm_af_errors")],
        [InlineKeyboardButton("🔍 اختبار الإرسال", callback_data="adm_af_test"),
         InlineKeyboardButton("🔄 إعادة ضبط الإعدادات", callback_data="adm_af_reset")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def stats_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("👥 إحصائيات المستخدمين", callback_data="adm_stats_users"),
         InlineKeyboardButton("📡 إحصائيات القنوات", callback_data="adm_stats_channels")],
        [InlineKeyboardButton("📣 إحصائيات الإذاعة", callback_data="adm_stats_broadcast"),
         InlineKeyboardButton("🗓 إحصائيات النشر المجدول", callback_data="adm_stats_scheduled")],
        [InlineKeyboardButton("📈 إحصائيات النشاط", callback_data="adm_stats_activity"),
         InlineKeyboardButton("🌐 إحصائيات المنصات", callback_data="adm_stats_platforms")],
        [InlineKeyboardButton("📥 تصدير الإحصائيات", callback_data="adm_stats_export"),
         InlineKeyboardButton("🔄 تحديث الإحصائيات", callback_data="adm_stats_refresh")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def settings_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("👋 رسالة البداية", callback_data="adm_set_start_msg"),
         InlineKeyboardButton("📢 رسالة الاشتراك", callback_data="adm_set_sub_msg")],
        [InlineKeyboardButton("💬 رسائل البوت", callback_data="adm_set_messages"),
         InlineKeyboardButton("🌍 إعدادات اللغة", callback_data="adm_set_lang")],
        [InlineKeyboardButton("🔘 إدارة الأزرار", callback_data="adm_set_buttons"),
         InlineKeyboardButton("⚡ حالة نشاط البوت", callback_data="adm_set_activity")],
        [InlineKeyboardButton("🎵 المنصات المدعومة", callback_data="adm_set_platforms"),
         InlineKeyboardButton("📎 Caption الوسائط", callback_data="adm_set_caption")],
        [InlineKeyboardButton("🧠 إعدادات التحميل", callback_data="adm_set_download"),
         InlineKeyboardButton("🔄 إعادة ضبط الإعدادات", callback_data="adm_set_reset")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def ui_menu_keyboard():
    buttons = [
        [InlineKeyboardButton("💬 إدارة الرسائل", callback_data="adm_ui_messages"),
         InlineKeyboardButton("🔘 إدارة الأزرار", callback_data="adm_ui_buttons")],
        [InlineKeyboardButton("🌐 Web App Buttons", callback_data="adm_ui_webapps"),
         InlineKeyboardButton("⚡ حالة نشاط البوت", callback_data="adm_ui_activity")],
        [InlineKeyboardButton("🌍 إدارة اللغات", callback_data="adm_ui_langs"),
         InlineKeyboardButton("🎨 تنسيق الواجهة", callback_data="adm_ui_format")],
        [InlineKeyboardButton("🎵 منصات التحميل", callback_data="adm_ui_platforms"),
         InlineKeyboardButton("👁 معاينة الواجهة", callback_data="adm_ui_preview")],
        [InlineKeyboardButton("🔄 إعادة ضبط الواجهة", callback_data="adm_ui_reset")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def export_keyboard(back_to: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 تصدير CSV", callback_data=f"export_csv_{back_to}"),
         InlineKeyboardButton("📄 تصدير TXT", callback_data=f"export_txt_{back_to}"),
         InlineKeyboardButton("📄 تصدير JSON", callback_data=f"export_json_{back_to}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=back_to)]
    ])


def delete_inactive_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 حذف مستخدمي 30 يوم", callback_data="confirm_del_inactive_30")],
        [InlineKeyboardButton("📅 حذف مستخدمي 60 يوم", callback_data="confirm_del_inactive_60")],
        [InlineKeyboardButton("📅 حذف مستخدمي 90 يوم", callback_data="confirm_del_inactive_90")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_users"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def speed_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ 5 رسائل/دقيقة", callback_data="af_speed_5"),
         InlineKeyboardButton("⚡ 10 رسائل/دقيقة", callback_data="af_speed_10")],
        [InlineKeyboardButton("⚡ 20 رسالة/دقيقة", callback_data="af_speed_20"),
         InlineKeyboardButton("⚡ 30 رسالة/دقيقة", callback_data="af_speed_30")],
        [InlineKeyboardButton("✏️ قيمة مخصصة", callback_data="af_speed_custom")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_antiflood"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def delay_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 ثانية", callback_data="af_delay_1"),
         InlineKeyboardButton("2 ثانية", callback_data="af_delay_2"),
         InlineKeyboardButton("3 ثواني", callback_data="af_delay_3")],
        [InlineKeyboardButton("5 ثواني", callback_data="af_delay_5"),
         InlineKeyboardButton("10 ثواني", callback_data="af_delay_10"),
         InlineKeyboardButton("30 ثانية", callback_data="af_delay_30")],
        [InlineKeyboardButton("✏️ تأخير مخصص", callback_data="af_delay_custom")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_antiflood"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def retry_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 مرة واحدة", callback_data="af_retry_1"),
         InlineKeyboardButton("🔁 مرتين", callback_data="af_retry_2"),
         InlineKeyboardButton("🔁 3 مرات", callback_data="af_retry_3")],
        [InlineKeyboardButton("✏️ عدد مخصص", callback_data="af_retry_custom")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_antiflood"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def activity_status_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⌨️ يكتب…", callback_data="set_activity_typing"),
         InlineKeyboardButton("🎥 يرسل مقطعاً", callback_data="set_activity_upload_video")],
        [InlineKeyboardButton("📷 يرسل صورة", callback_data="set_activity_upload_photo"),
         InlineKeyboardButton("📁 يرفع ملف", callback_data="set_activity_upload_document")],
        [InlineKeyboardButton("🎧 يسجل صوت", callback_data="set_activity_record_voice")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_settings"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def platforms_keyboard(settings: dict):
    def status(key): return "✅" if settings.get(key, "true") == "true" else "❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🎵 TikTok {status('tiktok_enabled')}", callback_data="toggle_tiktok"),
         InlineKeyboardButton(f"📺 YouTube {status('youtube_enabled')}", callback_data="toggle_youtube")],
        [InlineKeyboardButton(f"📷 Instagram {status('instagram_enabled')}", callback_data="toggle_instagram"),
         InlineKeyboardButton(f"❤️ Likee {status('likee_enabled')}", callback_data="toggle_likee")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_settings"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def sub_settings_keyboard(enabled: bool):
    toggle_text = "🔓 تعطيل الاشتراك الإجباري" if enabled else "🔒 تفعيل الاشتراك الإجباري"
    toggle_cb = "sub_disable" if enabled else "sub_enable"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_text, callback_data=toggle_cb)],
        [InlineKeyboardButton("📢 تعديل رسالة الاشتراك", callback_data="adm_set_sub_msg")],
        [InlineKeyboardButton("🔄 إعادة فحص الاشتراكات", callback_data="sub_recheck")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_sub"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def messages_settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 رسالة التحميل", callback_data="edit_msg_downloading"),
         InlineKeyboardButton("⚠️ رسالة رابط غير مدعوم", callback_data="edit_msg_unsupported")],
        [InlineKeyboardButton("❓ رسالة المساعدة", callback_data="edit_msg_help"),
         InlineKeyboardButton("📢 رسالة الخطأ", callback_data="edit_msg_error")],
        [InlineKeyboardButton("📋 عرض الرسائل", callback_data="view_all_messages")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_settings"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def add_sub_type_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إضافة قناة", callback_data="sub_add_channel"),
         InlineKeyboardButton("👥 إضافة مجموعة", callback_data="sub_add_group"),
         InlineKeyboardButton("🤖 إضافة بوت", callback_data="sub_add_bot")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_sub"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def broadcast_compose_keyboard(target: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ كتابة الرسالة", callback_data=f"bc_write_{target}"),
         InlineKeyboardButton("📎 إضافة صورة", callback_data=f"bc_photo_{target}")],
        [InlineKeyboardButton("📎 إضافة فيديو", callback_data=f"bc_video_{target}"),
         InlineKeyboardButton("📎 إضافة ملف", callback_data=f"bc_file_{target}")],
        [InlineKeyboardButton("👥 إرسال للكل", callback_data=f"bc_send_all_{target}"),
         InlineKeyboardButton("📊 إرسال للنشطين", callback_data=f"bc_send_active_{target}")],
        [InlineKeyboardButton("📤 بدء الإرسال", callback_data=f"bc_confirm_{target}"),
         InlineKeyboardButton("❌ إلغاء", callback_data="adm_broadcast")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_broadcast"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def repeat_type_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣ مرة واحدة", callback_data="sched_repeat_once"),
         InlineKeyboardButton("🔁 يومي", callback_data="sched_repeat_daily")],
        [InlineKeyboardButton("📅 أسبوعي", callback_data="sched_repeat_weekly"),
         InlineKeyboardButton("🗓 شهري", callback_data="sched_repeat_monthly")],
        [InlineKeyboardButton("♾ تكرار دائم", callback_data="sched_repeat_forever")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_scheduled"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def auto_delete_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("10 دقائق", callback_data="autodel_600"),
         InlineKeyboardButton("30 دقيقة", callback_data="autodel_1800")],
        [InlineKeyboardButton("1 ساعة", callback_data="autodel_3600"),
         InlineKeyboardButton("6 ساعات", callback_data="autodel_21600")],
        [InlineKeyboardButton("12 ساعة", callback_data="autodel_43200"),
         InlineKeyboardButton("1 يوم", callback_data="autodel_86400")],
        [InlineKeyboardButton("❌ عدم الحذف", callback_data="autodel_0")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_scheduled"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


def admin_perms_keyboard(selected: list):
    all_perms = [
        ("manage_users", "👥 إدارة المستخدمين"),
        ("manage_subscription", "📢 إدارة الاشتراك"),
        ("manage_channels", "📡 إدارة القنوات"),
        ("manage_broadcast", "📣 إدارة الإذاعة"),
        ("manage_scheduled", "🗓 إدارة النشر المجدول"),
        ("manage_groups", "📂 إدارة المجموعات"),
        ("manage_antiflood", "🛡 إدارة منع الحظر"),
        ("view_stats", "📊 مشاهدة الإحصائيات"),
        ("manage_settings", "⚙️ إدارة الإعدادات"),
        ("add_admins", "➕ إضافة مشرفين"),
        ("delete_admins", "🗑 حذف مشرفين"),
    ]
    buttons = []
    for perm_key, perm_name in all_perms:
        check = "✅" if perm_key in selected else "☑️"
        buttons.append([InlineKeyboardButton(f"{check} {perm_name}", callback_data=f"toggle_perm_{perm_key}")])
    buttons.append([
        InlineKeyboardButton("🔄 تحديد الكل", callback_data="perms_select_all"),
        InlineKeyboardButton("🧹 إلغاء الكل", callback_data="perms_deselect_all")
    ])
    buttons.append([
        InlineKeyboardButton("✅ حفظ الصلاحيات", callback_data="perms_save"),
        InlineKeyboardButton("❌ إلغاء", callback_data="adm_admins")
    ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_admins")])
    return InlineKeyboardMarkup(buttons)

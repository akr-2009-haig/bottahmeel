from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def ui_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 إدارة الرسائل", callback_data="ui_messages"),
         InlineKeyboardButton("🔘 إدارة الأزرار", callback_data="ui_buttons")],
        [InlineKeyboardButton("🌐 Web App Manager", callback_data="ui_webapps"),
         InlineKeyboardButton("⚡ حالة النشاط", callback_data="ui_activity")],
        [InlineKeyboardButton("🌍 إدارة اللغات", callback_data="ui_langs"),
         InlineKeyboardButton("🎨 تنسيق النصوص", callback_data="ui_format")],
        [InlineKeyboardButton("🎵 منصات التحميل", callback_data="ui_platforms"),
         InlineKeyboardButton("📦 إدارة Caption", callback_data="ui_caption")],
        [InlineKeyboardButton("👁 معاينة الواجهة", callback_data="ui_preview"),
         InlineKeyboardButton("🔄 إعادة الضبط", callback_data="ui_reset_confirm")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_settings")],
    ])


def ui_back(sub="adm_ui"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=sub),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")]
    ])


# ─────────────────────────────────────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────────────────────────────────────

def ui_messages_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👋 رسالة البداية", callback_data="ui_msg_start"),
         InlineKeyboardButton("📢 رسالة الاشتراك", callback_data="ui_msg_sub")],
        [InlineKeyboardButton("📥 رسالة التحميل", callback_data="ui_msg_download"),
         InlineKeyboardButton("⚠️ رابط غير مدعوم", callback_data="ui_msg_unsupported")],
        [InlineKeyboardButton("❓ رسالة المساعدة", callback_data="ui_msg_help"),
         InlineKeyboardButton("❌ رسالة الخطأ", callback_data="ui_msg_error")],
        [InlineKeyboardButton("📋 عرض جميع الرسائل", callback_data="ui_msg_all")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_single_message_keyboard(msg_key: str, has_buttons: bool = False):
    rows = [
        [InlineKeyboardButton("✏️ تعديل النص", callback_data=f"ui_edit_msg_{msg_key}")],
    ]
    if has_buttons:
        rows.append([
            InlineKeyboardButton("🔘 أزرار هذه الرسالة", callback_data=f"ui_btn_list_0"),
        ])
    rows.append([InlineKeyboardButton("👁 معاينة الرسالة", callback_data=f"ui_preview_msg_{msg_key}")])
    rows.append([
        InlineKeyboardButton("🔙 رجوع", callback_data="ui_messages"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main"),
    ])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────────
# BUTTONS
# ─────────────────────────────────────────────────────────────────────────────

def ui_buttons_keyboard(total: int = 0, active: int = 0):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة زر جديد", callback_data="ui_btn_add")],
        [InlineKeyboardButton("📋 عرض الأزرار", callback_data="ui_btn_list_0"),
         InlineKeyboardButton("✏️ تعديل زر", callback_data="ui_btn_edit_pick")],
        [InlineKeyboardButton("🗑 حذف زر", callback_data="ui_btn_delete_pick"),
         InlineKeyboardButton("🔄 ترتيب الأزرار", callback_data="ui_btn_reorder_pick")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_btn_type_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔘 Inline Button", callback_data="ui_btn_type_inline"),
         InlineKeyboardButton("🔗 URL Button", callback_data="ui_btn_type_url")],
        [InlineKeyboardButton("⚙️ Callback Button", callback_data="ui_btn_type_callback"),
         InlineKeyboardButton("⌨️ Reply Button", callback_data="ui_btn_type_reply")],
        [InlineKeyboardButton("🌐 Web App (داخل رسالة)", callback_data="ui_btn_type_webapp")],
        [InlineKeyboardButton("📱 Web App (لوحة مفاتيح)", callback_data="ui_btn_type_reply_webapp")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="ui_buttons"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_btn_location_keyboard(back="ui_btn_add"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👋 رسالة /start", callback_data="ui_btn_loc_start"),
         InlineKeyboardButton("❓ رسالة /help", callback_data="ui_btn_loc_help")],
        [InlineKeyboardButton("📢 رسالة الاشتراك", callback_data="ui_btn_loc_sub"),
         InlineKeyboardButton("📥 رسالة التحميل", callback_data="ui_btn_loc_download")],
        [InlineKeyboardButton("📌 رسالة مخصصة", callback_data="ui_btn_loc_custom")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=back),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_btn_detail_keyboard(btn_id: int, is_active: bool):
    toggle_label = "❌ تعطيل الزر" if is_active else "✅ تفعيل الزر"
    toggle_cb = f"ui_btn_disable_{btn_id}" if is_active else f"ui_btn_enable_{btn_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تعديل العنوان", callback_data=f"ui_btn_edit_label_{btn_id}"),
         InlineKeyboardButton("✏️ تعديل البيانات", callback_data=f"ui_btn_edit_data_{btn_id}")],
        [InlineKeyboardButton(toggle_label, callback_data=toggle_cb)],
        [InlineKeyboardButton("🗑 حذف الزر", callback_data=f"ui_btn_del_{btn_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="ui_btn_list_0"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_btn_reorder_pick_keyboard(locations: list):
    loc_labels = {
        "start": "👋 /start",
        "help": "❓ /help",
        "sub": "📢 الاشتراك",
        "download": "📥 التحميل",
        "custom": "📌 مخصص",
    }
    rows = []
    for loc in locations:
        label = loc_labels.get(loc, loc)
        rows.append([InlineKeyboardButton(label, callback_data=f"ui_btn_reorder_loc_{loc}")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="ui_buttons"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
    return InlineKeyboardMarkup(rows)


def ui_btn_reorder_keyboard(location: str, buttons: list):
    rows = []
    for i, btn in enumerate(buttons):
        up = InlineKeyboardButton("⬆️", callback_data=f"ui_btn_up_{btn.id}") if i > 0 else InlineKeyboardButton("·", callback_data="btn_noop_up")
        dn = InlineKeyboardButton("⬇️", callback_data=f"ui_btn_dn_{btn.id}") if i < len(buttons) - 1 else InlineKeyboardButton("·", callback_data="btn_noop_dn")
        name_btn = InlineKeyboardButton(f"{i+1}. {btn.label[:25]}", callback_data=f"ui_btn_detail_{btn.id}")
        rows.append([up, name_btn, dn])
    rows.append([InlineKeyboardButton("💾 الترتيب محفوظ تلقائياً", callback_data="btn_noop_save")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="ui_btn_reorder_pick"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────────
# WEB APP MANAGER
# ─────────────────────────────────────────────────────────────────────────────

def ui_webapps_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة Web App جديد", callback_data="ui_wa_add")],
        [InlineKeyboardButton("📋 عرض وإدارة التطبيقات", callback_data="ui_wa_list_0")],
        [InlineKeyboardButton("🗑 حذف تطبيق", callback_data="ui_wa_delete_pick"),
         InlineKeyboardButton("📍 إدارة المواضع", callback_data="ui_wa_placement_manage")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_wa_placement_keyboard():
    """Step 3 of WA add: choose where the button appears."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 داخل الرسالة (Inline)", callback_data="ui_wa_pl_inline")],
        [InlineKeyboardButton("⌨️ لوحة المفاتيح (Reply Keyboard)", callback_data="ui_wa_pl_reply_keyboard")],
        [InlineKeyboardButton("📱 شريط المدخلات (Menu Button) ★", callback_data="ui_wa_pl_menu_button")],
        [InlineKeyboardButton("📂 قائمة البوت (Bot Menu)", callback_data="ui_wa_pl_bot_menu")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="ui_webapps"),
         InlineKeyboardButton("❌ إلغاء", callback_data="ui_webapps")],
    ])


def ui_wa_inline_location_keyboard():
    """Step 3b: pick which message (only for inline placement)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👋 رسالة /start", callback_data="ui_wa_loc_start"),
         InlineKeyboardButton("❓ رسالة /help", callback_data="ui_wa_loc_help")],
        [InlineKeyboardButton("📢 رسالة الاشتراك", callback_data="ui_wa_loc_sub"),
         InlineKeyboardButton("📥 رسالة التحميل", callback_data="ui_wa_loc_download")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="ui_webapps"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_wa_detail_keyboard(wa_id: int, is_active: bool, placement: str):
    toggle_label = "❌ تعطيل" if is_active else "✅ تفعيل"
    toggle_cb = f"ui_wa_disable_{wa_id}" if is_active else f"ui_wa_enable_{wa_id}"
    rows = [
        [InlineKeyboardButton("✏️ تعديل العنوان", callback_data=f"ui_wa_edit_label_{wa_id}"),
         InlineKeyboardButton("✏️ تعديل الرابط", callback_data=f"ui_wa_edit_url_{wa_id}")],
        [InlineKeyboardButton(toggle_label, callback_data=toggle_cb),
         InlineKeyboardButton("🗑 حذف", callback_data=f"ui_wa_del_confirm_{wa_id}")],
    ]
    if placement == "menu_button":
        rows.append([InlineKeyboardButton("🔄 تطبيق Menu Button الآن", callback_data=f"ui_wa_apply_menu_{wa_id}")])
    rows.append([InlineKeyboardButton("🔙 للقائمة", callback_data="ui_wa_list_0"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
    return InlineKeyboardMarkup(rows)


def ui_wa_delete_confirm_keyboard(wa_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، احذف", callback_data=f"ui_wa_del_{wa_id}"),
         InlineKeyboardButton("❌ لا، تراجع", callback_data=f"ui_wa_detail_{wa_id}")],
    ])


def ui_wa_placement_manage_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 داخل الرسائل (Inline)", callback_data="ui_wa_pm_inline")],
        [InlineKeyboardButton("⌨️ لوحة المفاتيح (Reply)", callback_data="ui_wa_pm_reply_keyboard")],
        [InlineKeyboardButton("📱 شريط المدخلات (Menu Button)", callback_data="ui_wa_pm_menu_button")],
        [InlineKeyboardButton("📂 قائمة البوت (Bot Menu)", callback_data="ui_wa_pm_bot_menu")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="ui_webapps"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_wa_menu_button_keyboard(has_menu_btn: bool, wa_id: int = None):
    rows = []
    if has_menu_btn and wa_id:
        rows.append([InlineKeyboardButton(
            "🔄 تطبيق في تيليجرام الآن ✅",
            callback_data=f"ui_wa_apply_menu_{wa_id}"
        )])
        rows.append([InlineKeyboardButton(
            "❌ إزالة Menu Button من تيليجرام",
            callback_data="ui_wa_remove_menu_btn"
        )])
        rows.append([InlineKeyboardButton(
            "📋 عرض تفاصيل التطبيق",
            callback_data=f"ui_wa_detail_{wa_id}"
        )])
    else:
        rows.append([InlineKeyboardButton(
            "➕ إضافة تطبيق بموضع Menu Button",
            callback_data="ui_wa_add"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="ui_wa_placement_manage"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────────
# ACTIVITY
# ─────────────────────────────────────────────────────────────────────────────

def ui_activity_keyboard(current: str = "upload_video"):
    def mark(v): return "✅ " if current == v else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{mark('typing')}⌨️ يكتب…", callback_data="ui_act_typing"),
         InlineKeyboardButton(f"{mark('upload_video')}🎥 يرسل فيديو", callback_data="ui_act_upload_video")],
        [InlineKeyboardButton(f"{mark('upload_photo')}📷 يرسل صورة", callback_data="ui_act_upload_photo"),
         InlineKeyboardButton(f"{mark('upload_document')}📁 يرفع ملف", callback_data="ui_act_upload_document")],
        [InlineKeyboardButton(f"{mark('record_voice')}🎧 يسجل صوت", callback_data="ui_act_record_voice"),
         InlineKeyboardButton(f"{mark('choose_sticker')}🖼 يختار ملصق", callback_data="ui_act_choose_sticker")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# LANGUAGES
# ─────────────────────────────────────────────────────────────────────────────

def ui_langs_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 إدارة اللغات المتاحة (50 لغة)", callback_data="ui_avail_langs_0")],
        [InlineKeyboardButton("───── ترجمة الرسائل ─────", callback_data="btn_noop_sep")],
        [InlineKeyboardButton("🇸🇦 العربية", callback_data="ui_lang_edit_ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data="ui_lang_edit_en"),
         InlineKeyboardButton("🇷🇺 Русский", callback_data="ui_lang_edit_ru")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_lang_edit_keyboard(lang: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 رسالة البداية", callback_data=f"ui_lang_tr_start_{lang}"),
         InlineKeyboardButton("📄 رسالة المساعدة", callback_data=f"ui_lang_tr_help_{lang}")],
        [InlineKeyboardButton("📄 رسالة التحميل", callback_data=f"ui_lang_tr_download_{lang}"),
         InlineKeyboardButton("📄 رسالة الخطأ", callback_data=f"ui_lang_tr_error_{lang}")],
        [InlineKeyboardButton("📄 رسالة الاشتراك", callback_data=f"ui_lang_tr_sub_{lang}"),
         InlineKeyboardButton("📄 رسالة غير مدعوم", callback_data=f"ui_lang_tr_unsupported_{lang}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="ui_langs"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# FORMATTING
# ─────────────────────────────────────────────────────────────────────────────

def ui_format_keyboard(current: str = "none"):
    def mark(v): return "✅ " if current == v else ""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{mark('none')}عادي (None)", callback_data="ui_fmt_none"),
         InlineKeyboardButton(f"{mark('bold')}**Bold**", callback_data="ui_fmt_bold")],
        [InlineKeyboardButton(f"{mark('italic')}_Italic_", callback_data="ui_fmt_italic"),
         InlineKeyboardButton(f"{mark('code')}`Code`", callback_data="ui_fmt_code")],
        [InlineKeyboardButton(f"{mark('mono')}Mono", callback_data="ui_fmt_mono")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORMS
# ─────────────────────────────────────────────────────────────────────────────

def ui_platforms_keyboard(settings: dict):
    from bot.utils.platforms import PLATFORMS

    def st(k): return "✅" if settings.get(k, "false") == "true" else "❌"

    rows = []
    platform_list = list(PLATFORMS.items())
    for i in range(0, len(platform_list), 2):
        row = []
        for key, info in platform_list[i:i+2]:
            enabled_key = info["db_key"]
            label = f"{info['emoji']} {info['name']} {st(enabled_key)}"
            row.append(InlineKeyboardButton(label, callback_data=f"ui_plat_{key}"))
        rows.append(row)

    rows.append([InlineKeyboardButton("⚙️ ردود المنصات العامة", callback_data="ui_plat_responses")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
    return InlineKeyboardMarkup(rows)


def ui_platform_detail_keyboard(platform: str, enabled: bool):
    toggle_text = "❌ تعطيل المنصة" if enabled else "✅ تفعيل المنصة"
    toggle_cb = f"ui_plat_disable_{platform}" if enabled else f"ui_plat_enable_{platform}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_text, callback_data=toggle_cb)],
        [InlineKeyboardButton("✏️ تعديل رسالة التعطيل", callback_data=f"ui_plat_editmsg_{platform}"),
         InlineKeyboardButton("👁 معاينة الرسالة", callback_data=f"ui_plat_preview_{platform}")],
        [InlineKeyboardButton("📊 إحصائيات المنصة", callback_data=f"ui_plat_stats_{platform}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="ui_platforms"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


def ui_plat_responses_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ منصة غير مدعومة", callback_data="ui_plat_edit_unsupported"),
         InlineKeyboardButton("🚫 منصة معطّلة (عامة)", callback_data="ui_plat_edit_disabled_generic")],
        [InlineKeyboardButton("👁 معاينة الرسائل", callback_data="ui_plat_preview_responses")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="ui_platforms"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# CAPTION
# ─────────────────────────────────────────────────────────────────────────────

def ui_caption_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📹 Caption الفيديو", callback_data="ui_cap_video"),
         InlineKeyboardButton("🖼 Caption الصور", callback_data="ui_cap_photo")],
        [InlineKeyboardButton("👁 معاينة Caption", callback_data="ui_cap_preview")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# PREVIEW
# ─────────────────────────────────────────────────────────────────────────────

def ui_preview_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👋 رسالة /start", callback_data="ui_prev_start"),
         InlineKeyboardButton("📢 رسالة الاشتراك", callback_data="ui_prev_sub")],
        [InlineKeyboardButton("❓ رسالة /help", callback_data="ui_prev_help"),
         InlineKeyboardButton("📥 رسالة التحميل", callback_data="ui_prev_download")],
        [InlineKeyboardButton("🔘 الأزرار", callback_data="ui_prev_buttons"),
         InlineKeyboardButton("🌐 Web Apps", callback_data="ui_prev_webapps")],
        [InlineKeyboardButton("🎵 ردود المنصات", callback_data="ui_prev_platforms")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="adm_ui"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# RESET
# ─────────────────────────────────────────────────────────────────────────────

def ui_reset_confirm_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ تأكيد إعادة الضبط", callback_data="ui_reset_execute")],
        [InlineKeyboardButton("❌ إلغاء — العودة بأمان", callback_data="adm_ui")],
    ])

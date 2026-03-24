"""
Dynamic UI Manager - Engine for managing all bot messages, buttons, and platforms
All data is stored in the database, not in code files.
"""
import logging
import html as _html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


def _e(text: str) -> str:
    """Escape text for safe display inside HTML parse_mode (prevents BadRequest)."""
    return _html.escape(str(text or ""))


def _md(text: str) -> str:
    """Escape Markdown V1 special chars in user-supplied content."""
    for ch in ("_", "*", "`", "["):
        text = str(text or "").replace(ch, f"\\{ch}")
    return text

from bot.database import (
    SessionLocal, BotButton, WebAppButton, BotSettings, BotLanguage,
    get_setting, set_setting
)
from .ui_keyboards import (
    ui_main_keyboard, ui_back, ui_messages_keyboard, ui_single_message_keyboard,
    ui_buttons_keyboard, ui_btn_type_keyboard, ui_btn_location_keyboard,
    ui_btn_detail_keyboard, ui_btn_reorder_pick_keyboard, ui_btn_reorder_keyboard,
    ui_webapps_keyboard, ui_wa_placement_keyboard, ui_wa_inline_location_keyboard,
    ui_wa_detail_keyboard, ui_wa_placement_manage_keyboard, ui_wa_menu_button_keyboard,
    ui_activity_keyboard, ui_langs_keyboard,
    ui_lang_edit_keyboard, ui_format_keyboard, ui_platforms_keyboard,
    ui_platform_detail_keyboard, ui_plat_responses_keyboard, ui_caption_keyboard,
    ui_preview_keyboard, ui_reset_confirm_keyboard
)

logger = logging.getLogger(__name__)

def _get_platform_label(platform: str) -> str:
    from bot.utils.platforms import PLATFORMS
    info = PLATFORMS.get(platform, {})
    return f"{info.get('emoji', '📥')} {info.get('name', platform.title())}"


PLATFORM_LABELS: dict = {}

def _build_platform_labels():
    from bot.utils.platforms import PLATFORMS
    return {k: f"{v['emoji']} {v['name']}" for k, v in PLATFORMS.items()}


MESSAGE_LABELS = {
    "start": ("start_message", "👋 رسالة البداية", True),
    "sub": ("subscription_message", "📢 رسالة الاشتراك", True),
    "download": ("downloading_message", "📥 رسالة التحميل", False),
    "unsupported": ("unsupported_message", "⚠️ رسالة الرابط غير المدعوم", False),
    "help": ("help_message", "❓ رسالة المساعدة", True),
    "error": ("error_message", "❌ رسالة الخطأ", False),
}

LANG_LABELS = {"ar": "🇸🇦 Arabic", "en": "🇬🇧 English", "ru": "🇷🇺 Russian"}

LANG_MESSAGE_KEYS = {
    "start": "start_message",
    "help": "help_message",
    "download": "downloading_message",
    "error": "error_message",
    "sub": "subscription_message",
    "unsupported": "unsupported_message",
}

ACTIVITY_LABELS = {
    "typing": "⌨️ يكتب…",
    "upload_video": "🎥 يرسل فيديو",
    "upload_photo": "📷 يرسل صورة",
    "upload_document": "📁 يرفع ملف",
    "record_voice": "🎧 يسجل صوت",
    "choose_sticker": "🖼 يختار ملصق",
}

FORMAT_LABELS = {
    "none": "عادي",
    "bold": "**Bold**",
    "italic": "_Italic_",
    "code": "`Code`",
    "mono": "Mono",
}

DEFAULT_MESSAGES = {
    "start_message": "مرحبا بك يا {name} 👋\n\nيمكنني تنزيل الوسائط من عدة منصات مثل TikTok وYouTube وInstagram وReddit وGoogle Drive وLinkedIn حسب تفعيل الإدارة.\nأرسل الرابط للبدء.",
    "subscription_message": "لإستخدام البوت يرجى الإشتراك في القنوات التالية\n📢 اشترك في القنوات التالية",
    "help_message": "🤖 يمكنني تنزيل مقاطع فيديو من TikTok\n\nكيفية التنزيل:\n1. انتقل إلى تطبيق TikTok\n2. اختر مقطع فيديو\n3. انقر على زر ↪️ أو ثلاث نقاط\n4. انقر فوق نسخ الرابط\n5. أرسل الرابط هنا",
    "downloading_message": "⏰┇يرجى الانتظار، يتم قياس حجم التحميل...",
    "unsupported_message": "⚠️ الرابط غير مدعوم حالياً. يرجى إرسال رابط من منصة مدعومة ومفعّلة.",
    "error_message": "❌ حدث خطأ أثناء التحميل. يرجى المحاولة مجدداً.",
    "video_caption": "📥 تم التحميل بنجاح\n\n🤖 @{bot_name}",
    "photo_caption": "🖼 تم التحميل بنجاح\n\n🤖 @{bot_name}",
}


async def ui_main(query, context):
    await query.edit_message_text(
        "🧩 **إدارة واجهة المستخدم**\n\n"
        "هذا القسم يسمح لك بتعديل كل ما يراه المستخدم:\n"
        "الرسائل، الأزرار، المنصات، اللغات، وأكثر.\n"
        "جميع التغييرات تُحفظ في قاعدة البيانات فوراً.",
        reply_markup=ui_main_keyboard(),
        parse_mode="Markdown"
    )


async def ui_messages(query, context):
    await query.edit_message_text(
        "💬 **إدارة الرسائل**\n\n"
        "اختر الرسالة التي تريد تعديلها:",
        reply_markup=ui_messages_keyboard(),
        parse_mode="Markdown"
    )


async def ui_message_detail(query, context, msg_key: str):
    import html
    if msg_key not in MESSAGE_LABELS:
        await query.answer("مفتاح رسالة غير صحيح", show_alert=True)
        return
    db_key, label, has_btns = MESSAGE_LABELS[msg_key]
    current = get_setting(db_key, DEFAULT_MESSAGES.get(db_key, ""))
    preview = current[:300] + "..." if len(current) > 300 else current
    safe_preview = html.escape(preview)
    safe_label  = html.escape(label)
    await query.edit_message_text(
        f"{safe_label}\n\n"
        f"📝 <b>النص الحالي:</b>\n<code>{safe_preview}</code>\n\n"
        f"اختر الإجراء:",
        reply_markup=ui_single_message_keyboard(msg_key, has_btns),
        parse_mode="HTML"
    )


async def ui_edit_msg_start(query, context, msg_key: str):
    import html
    db_key, label, _ = MESSAGE_LABELS[msg_key]
    current = get_setting(db_key, DEFAULT_MESSAGES.get(db_key, ""))
    context.user_data["waiting_for"] = f"ui_msg_text_{msg_key}"
    context.user_data["ui_msg_key"] = db_key
    safe_current = html.escape(current)
    safe_label   = html.escape(label)
    await query.edit_message_text(
        f"✏️ <b>تعديل {safe_label}</b>\n\n"
        f"📝 <b>النص الحالي:</b>\n<code>{safe_current}</code>\n\n"
        f"أرسل النص الجديد الآن:\n"
        f"<i>يمكنك استخدام: {{name}} لاسم المستخدم, {{bot_name}} لاسم البوت</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"ui_msg_{msg_key}")]
        ]),
        parse_mode="HTML"
    )


async def ui_preview_msg(query, context, msg_key: str):
    db_key, label, _ = MESSAGE_LABELS[msg_key]
    current = get_setting(db_key, DEFAULT_MESSAGES.get(db_key, ""))
    bot_name = get_setting("bot_name", "SaveEliteBot")
    preview = current.replace("{name}", query.from_user.first_name or "المستخدم")
    preview = preview.replace("{bot_name}", bot_name)
    await query.answer()
    await query.message.reply_text(
        f"👁 معاينة: {label}\n\n{preview}",
    )


async def ui_msg_all(query, context, page: int = 0):
    import html
    lines = []
    for key, (db_key, label, _) in MESSAGE_LABELS.items():
        val = get_setting(db_key, DEFAULT_MESSAGES.get(db_key, ""))
        short = val[:80].replace("\n", " ") + ("..." if len(val) > 80 else "")
        lines.append(f"<b>{html.escape(label)}:</b>\n<code>{html.escape(short)}</code>")
    per_page = 3
    total_pages = (len(lines) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    chunk = lines[page * per_page:(page + 1) * per_page]
    text = f"📋 <b>جميع الرسائل</b> (صفحة {page + 1}/{total_pages})\n\n" + "\n\n".join(chunk)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"ui_msg_all_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️ التالي", callback_data=f"ui_msg_all_{page+1}"))
    kb = []
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔄 تحديث", callback_data=f"ui_msg_all_{page}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="ui_messages"),
               InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")


async def ui_buttons_main(query, context):
    db = SessionLocal()
    try:
        total = db.query(BotButton).count()
        active = db.query(BotButton).filter_by(is_active=True).count()
        disabled = total - active
    finally:
        db.close()
    await query.edit_message_text(
        f"🔘 **إدارة الأزرار**\n\n"
        f"📊 الملخص:\n"
        f"• إجمالي الأزرار: `{total}`\n"
        f"• نشطة: `{active}` | معطّلة: `{disabled}`\n\n"
        f"اختر الإجراء:",
        reply_markup=ui_buttons_keyboard(total, active),
        parse_mode="Markdown"
    )


async def ui_btn_add(query, context):
    await query.edit_message_text(
        "➕ **إضافة زر جديد**\n\nاختر نوع الزر:",
        reply_markup=ui_btn_type_keyboard(),
        parse_mode="Markdown"
    )


async def ui_btn_set_type(query, context, btn_type: str):
    from bot.utils.button_engine import BUTTON_TYPE_DESCRIPTIONS
    context.user_data["new_btn_type"] = btn_type
    info = BUTTON_TYPE_DESCRIPTIONS.get(btn_type, {})
    type_label = info.get("label", btn_type)
    desc = info.get("desc", "")
    placement = info.get("placement", "")

    text = (
        f"**{type_label}**\n\n"
        f"ℹ️ {desc}\n\n"
        f"{placement}\n\n"
        f"────────────────\n"
        f"اختر **مكان ظهور الزر** في البوت:"
    )
    await query.edit_message_text(
        text,
        reply_markup=ui_btn_location_keyboard(),
        parse_mode="Markdown"
    )


async def ui_btn_set_location(query, context, location: str):
    context.user_data["new_btn_location"] = location
    context.user_data["waiting_for"] = "ui_btn_label"
    loc_labels = {
        "start": "👋 /start", "help": "❓ /help",
        "sub": "📢 الاشتراك", "download": "📥 التحميل", "custom": "📌 مخصصة",
    }
    await query.edit_message_text(
        f"📍 المكان: **{loc_labels.get(location, location)}**\n\n"
        f"✏️ أرسل **عنوان الزر** الذي سيظهر للمستخدم:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="ui_buttons")]
        ]),
        parse_mode="Markdown"
    )


async def ui_btn_list(query, context, page: int = 0):
    db = SessionLocal()
    try:
        buttons = db.query(BotButton).order_by(BotButton.location, BotButton.position).all()
        if not buttons:
            await query.edit_message_text(
                "🔘 **قائمة الأزرار**\n\n📭 لا توجد أزرار مضافة بعد.\n\n"
                "اضغط «➕ إضافة زر جديد» للبدء.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ إضافة زر جديد", callback_data="ui_btn_add")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="ui_buttons")],
                ]),
                parse_mode="Markdown"
            )
            return
        per_page = 7
        total_pages = max(1, (len(buttons) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        chunk = buttons[page * per_page:(page + 1) * per_page]

        loc_map = {"start": "👋", "help": "❓", "sub": "📢", "download": "📥", "custom": "📌"}
        type_map = {"inline": "🔘", "reply": "⌨️", "url": "🔗", "callback": "⚙️",
                    "webapp": "🌐", "reply_webapp": "🌐⌨️"}

        active_count = sum(1 for b in buttons if b.is_active)
        lines = [
            f"🔘 **قائمة الأزرار**",
            f"📊 الإجمالي: `{len(buttons)}` | نشط: `{active_count}` | صفحة `{page+1}/{total_pages}`",
            "",
            "اضغط على الزر للإدارة والتعديل:",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        kb = []
        for b in chunk:
            status_icon = "✅" if b.is_active else "❌"
            t_icon = type_map.get(b.button_type, "?")
            l_icon = loc_map.get(b.location, "📍")
            label_short = b.label[:26] + "…" if len(b.label) > 26 else b.label
            kb.append([InlineKeyboardButton(
                f"{status_icon} {t_icon} {l_icon} {label_short}",
                callback_data=f"ui_btn_detail_{b.id}"
            )])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"ui_btn_list_{page-1}"))
        nav.append(InlineKeyboardButton("🔄 تحديث", callback_data=f"ui_btn_list_{page}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"ui_btn_list_{page+1}"))
        if nav:
            kb.append(nav)

        kb.append([
            InlineKeyboardButton("➕ إضافة جديد", callback_data="ui_btn_add"),
            InlineKeyboardButton("🗑 حذف", callback_data="ui_btn_delete_pick"),
        ])
        kb.append([
            InlineKeyboardButton("🔙 رجوع", callback_data="ui_buttons"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main"),
        ])
        await query.edit_message_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
    finally:
        db.close()


async def ui_btn_delete_pick(query, context):
    db = SessionLocal()
    try:
        buttons = db.query(BotButton).order_by(BotButton.location, BotButton.position).all()
        if not buttons:
            await query.edit_message_text(
                "🗑 **حذف زر**\n\n📭 لا توجد أزرار مضافة بعد.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع", callback_data="ui_buttons")]
                ]),
                parse_mode="Markdown"
            )
            return
        loc_map = {"start": "👋", "help": "❓", "sub": "📢", "download": "📥", "custom": "📌"}
        type_map = {"inline": "🔘", "reply": "⌨️", "url": "🔗", "callback": "⚙️", "webapp": "🌐"}
        kb = []
        for b in buttons:
            status = "✅" if b.is_active else "❌"
            t_icon = type_map.get(b.button_type, "?")
            l_icon = loc_map.get(b.location, "📍")
            label_short = b.label[:24] + "…" if len(b.label) > 24 else b.label
            kb.append([InlineKeyboardButton(
                f"{status} {t_icon} {l_icon} [{b.id}] {label_short}",
                callback_data=f"ui_btn_del_{b.id}"
            )])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="ui_buttons"),
                   InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
        await query.edit_message_text(
            "🗑 **حذف زر**\n\n"
            "اختر الزر الذي تريد حذفه:\n"
            "_(✅ = نشط، ❌ = معطّل)_",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    finally:
        db.close()


async def ui_btn_delete(query, context, btn_id: int):
    db = SessionLocal()
    try:
        btn = db.query(BotButton).filter_by(id=btn_id).first()
        if btn:
            db.delete(btn)
            db.commit()
            await query.answer("✅ تم حذف الزر بنجاح", show_alert=True)
        else:
            await query.answer("❌ الزر غير موجود", show_alert=True)
    finally:
        db.close()
    await ui_buttons_main(query, context)


async def ui_btn_detail(query, context, btn_id: int):
    loc_map = {
        "start": "👋 /start", "help": "❓ /help",
        "sub": "📢 الاشتراك", "download": "📥 التحميل", "custom": "📌 مخصص",
    }
    type_map = {
        "inline": "🔘 Inline", "reply": "⌨️ Reply",
        "url": "🔗 URL", "callback": "⚙️ Callback",
        "webapp": "🌐 Web App (Inline)", "reply_webapp": "🌐 Web App (Keyboard)",
    }
    db = SessionLocal()
    try:
        btn = db.query(BotButton).filter_by(id=btn_id).first()
        if not btn:
            await query.answer("❌ الزر غير موجود", show_alert=True)
            return
        status = "✅ نشط" if btn.is_active else "❌ معطّل"
        if btn.button_type == "reply" and btn.data:
            data_line = f"\n💬 رسالة الرد:\n<code>{_e(btn.data[:120])}</code>"
        elif btn.data:
            data_line = f"\n🔗 البيانات:   <code>{_e(btn.data[:60])}</code>"
        else:
            data_line = ""
        text = (
            f"🔘 <b>تفاصيل الزر #{btn.id}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷 العنوان:   <b>{_e(btn.label)}</b>\n"
            f"📌 النوع:     {_e(type_map.get(btn.button_type, btn.button_type))}\n"
            f"📍 المكان:    {_e(loc_map.get(btn.location, btn.location))}\n"
            f"📶 الترتيب:   {btn.position}\n"
            f"📊 الحالة:    {status}"
            f"{data_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(
            text,
            reply_markup=ui_btn_detail_keyboard(btn.id, btn.is_active),
            parse_mode="HTML"
        )
    finally:
        db.close()


async def ui_btn_toggle(query, context, btn_id: int, enable: bool):
    db = SessionLocal()
    try:
        btn = db.query(BotButton).filter_by(id=btn_id).first()
        if btn:
            btn.is_active = enable
            db.commit()
            state = "مُفعَّل ✅" if enable else "معطّل ❌"
            await query.answer(f"تم: الزر الآن {state}", show_alert=True)
    finally:
        db.close()
    await ui_btn_detail(query, context, btn_id)


async def ui_btn_edit_label_start(query, context, btn_id: int):
    context.user_data["waiting_for"] = f"ui_btn_new_label_{btn_id}"
    await query.edit_message_text(
        f"✏️ **تعديل عنوان الزر #{btn_id}**\n\n"
        f"✏️ أرسل العنوان الجديد للزر:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"ui_btn_detail_{btn_id}")]
        ]),
        parse_mode="Markdown"
    )


async def ui_btn_edit_data_start(query, context, btn_id: int):
    db = SessionLocal()
    try:
        btn = db.query(BotButton).filter_by(id=btn_id).first()
        if not btn:
            await query.answer("❌ الزر غير موجود", show_alert=True)
            return
        btn_type = btn.button_type
    finally:
        db.close()

    prompt_map = {
        "url": "🔗 أرسل الرابط الجديد (يبدأ بـ https://):",
        "webapp": "🌐 أرسل رابط Web App الجديد (يبدأ بـ https://):",
        "reply_webapp": "📱 أرسل رابط Web App الجديد (يبدأ بـ https://):",
        "callback": "⚙️ أرسل Callback Data الجديد:",
    }
    prompt = prompt_map.get(btn_type, "✏️ أرسل البيانات الجديدة:")
    context.user_data["waiting_for"] = f"ui_btn_new_data_{btn_id}"
    context.user_data["ui_btn_edit_type"] = btn_type
    await query.edit_message_text(
        f"✏️ **تعديل بيانات الزر #{btn_id}**\n\n{prompt}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"ui_btn_detail_{btn_id}")]
        ]),
        parse_mode="Markdown"
    )


async def ui_btn_edit_pick(query, context):
    db = SessionLocal()
    try:
        buttons = db.query(BotButton).filter_by(is_active=True).limit(20).all()
        if not buttons:
            await query.answer("لا توجد أزرار للتعديل", show_alert=True)
            return
        kb = [[InlineKeyboardButton(
            f"✏️ [{b.id}] {b.label[:30]}",
            callback_data=f"ui_btn_detail_{b.id}"
        )] for b in buttons]
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="ui_buttons")])
        await query.edit_message_text(
            "✏️ **تعديل زر**\n\nاختر الزر الذي تريد تعديله:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    finally:
        db.close()


async def ui_btn_reorder_pick(query, context):
    db = SessionLocal()
    try:
        locations = db.query(BotButton.location).filter_by(
            is_active=True
        ).distinct().all()
        locs = [l[0] for l in locations]
    finally:
        db.close()
    if not locs:
        await query.answer("لا توجد أزرار لإعادة ترتيبها", show_alert=True)
        return
    await query.edit_message_text(
        "🔄 **ترتيب الأزرار**\n\nاختر الموقع الذي تريد إعادة ترتيب أزراره:",
        reply_markup=ui_btn_reorder_pick_keyboard(locs),
        parse_mode="Markdown"
    )


async def ui_btn_reorder_location(query, context, location: str):
    loc_map = {
        "start": "👋 /start", "help": "❓ /help",
        "sub": "📢 الاشتراك", "download": "📥 التحميل", "custom": "📌 مخصص",
    }
    db = SessionLocal()
    try:
        buttons = db.query(BotButton).filter_by(
            location=location
        ).order_by(BotButton.position).all()
        if not buttons:
            await query.answer("لا توجد أزرار في هذا الموقع", show_alert=True)
            return
        await query.edit_message_text(
            f"🔄 **ترتيب أزرار: {loc_map.get(location, location)}**\n\n"
            f"استخدم ⬆️ ⬇️ لتغيير ترتيب الأزرار.\n"
            f"الترتيب يُحفظ تلقائياً عند كل ضغطة:",
            reply_markup=ui_btn_reorder_keyboard(location, buttons),
            parse_mode="Markdown"
        )
    finally:
        db.close()


async def ui_btn_move(query, context, btn_id: int, direction: str):
    db = SessionLocal()
    try:
        btn = db.query(BotButton).filter_by(id=btn_id).first()
        if not btn:
            await query.answer("❌ الزر غير موجود", show_alert=True)
            return
        location = btn.location
        siblings = db.query(BotButton).filter_by(
            location=location
        ).order_by(BotButton.position).all()
        idx = next((i for i, b in enumerate(siblings) if b.id == btn_id), None)
        if idx is None:
            return
        if direction == "up" and idx > 0:
            siblings[idx].position, siblings[idx - 1].position = (
                siblings[idx - 1].position, siblings[idx].position
            )
        elif direction == "dn" and idx < len(siblings) - 1:
            siblings[idx].position, siblings[idx + 1].position = (
                siblings[idx + 1].position, siblings[idx].position
            )
        db.commit()
    finally:
        db.close()
    await ui_btn_reorder_location(query, context, location)


async def ui_webapps_main(query, context):
    from bot.utils.button_engine import PLACEMENT_LABELS
    db = SessionLocal()
    try:
        total = db.query(WebAppButton).count()
        active = db.query(WebAppButton).filter_by(is_active=True).count()
        inactive = total - active
        inline_c = db.query(WebAppButton).filter_by(placement="inline", is_active=True).count()
        reply_c = db.query(WebAppButton).filter_by(placement="reply_keyboard", is_active=True).count()
        menu_c = db.query(WebAppButton).filter_by(placement="menu_button", is_active=True).count()
        bot_menu_c = db.query(WebAppButton).filter_by(placement="bot_menu", is_active=True).count()
    finally:
        db.close()
    text = (
        "🌐 **إدارة Web App Buttons**\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **الإحصائيات:**\n"
        f"   • الإجمالي:   `{total}` تطبيق\n"
        f"   • النشطة:    `{active}` ✅\n"
        f"   • المعطّلة:   `{inactive}` ❌\n\n"
        f"📍 **حسب الموضع (النشطة):**\n"
        f"   💬 Inline:         `{inline_c}`\n"
        f"   ⌨️ Reply Keyboard: `{reply_c}`\n"
        f"   📱 Menu Button:    `{menu_c}`\n"
        f"   📂 Bot Menu:       `{bot_menu_c}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "اختر إجراءً:"
    )
    await query.edit_message_text(
        text,
        reply_markup=ui_webapps_keyboard(),
        parse_mode="Markdown"
    )


async def ui_wa_add_start(query, context):
    context.user_data["waiting_for"] = "ui_wa_label"
    context.user_data.pop("new_wa_label", None)
    context.user_data.pop("new_wa_url", None)
    context.user_data.pop("new_wa_placement", None)
    context.user_data.pop("new_wa_location", None)
    await query.edit_message_text(
        "🌐 **إضافة Web App Button**\n"
        "الخطوة 1/3 — عنوان الزر\n\n"
        "✏️ أرسل **عنوان الزر** الذي سيظهر للمستخدم:\n\n"
        "_مثال: «🛒 المتجر» أو «🎮 العب الآن» أو «Open»_",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="ui_webapps")]
        ]),
        parse_mode="Markdown"
    )


async def ui_wa_list(query, context, page: int = 0):
    from bot.utils.button_engine import PLACEMENT_LABELS
    db = SessionLocal()
    try:
        apps = db.query(WebAppButton).order_by(WebAppButton.placement, WebAppButton.position).all()
        if not apps:
            await query.edit_message_text(
                "🌐 **قائمة Web App Buttons**\n\n"
                "📭 لا توجد تطبيقات مضافة بعد.\n\n"
                "اضغط «➕ إضافة Web App جديد» للبدء.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ إضافة Web App جديد", callback_data="ui_wa_add")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="ui_webapps")],
                ]),
                parse_mode="Markdown"
            )
            return

        per_page = 6
        total_pages = max(1, (len(apps) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        chunk = apps[page * per_page:(page + 1) * per_page]

        # ── Build header text ────────────────────────────────────
        active_count = sum(1 for a in apps if a.is_active)
        lines = [
            f"🌐 **قائمة Web App Buttons**",
            f"📊 الإجمالي: `{len(apps)}` | نشط: `{active_count}` | صفحة `{page+1}/{total_pages}`",
            "",
            "اضغط على التطبيق للإدارة والتعديل:",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        # ── Per-app clickable buttons ────────────────────────────
        kb = []
        for a in chunk:
            status_icon = "✅" if a.is_active else "❌"
            pl_icon = {"inline": "💬", "reply_keyboard": "⌨️",
                       "menu_button": "📱", "bot_menu": "📂"}.get(a.placement, "📍")
            label_short = a.label[:28] + "…" if len(a.label) > 28 else a.label
            kb.append([InlineKeyboardButton(
                f"{status_icon} {pl_icon} {label_short}",
                callback_data=f"ui_wa_detail_{a.id}"
            )])

        # ── Navigation ────────────────────────────────────────────
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"ui_wa_list_{page-1}"))
        nav.append(InlineKeyboardButton("🔄 تحديث", callback_data=f"ui_wa_list_{page}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"ui_wa_list_{page+1}"))
        if nav:
            kb.append(nav)

        kb.append([
            InlineKeyboardButton("➕ إضافة جديد", callback_data="ui_wa_add"),
            InlineKeyboardButton("🗑 حذف", callback_data="ui_wa_delete_pick"),
        ])
        kb.append([
            InlineKeyboardButton("🔙 رجوع", callback_data="ui_webapps"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main"),
        ])

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    finally:
        db.close()


async def ui_wa_delete_pick(query, context):
    db = SessionLocal()
    try:
        apps = db.query(WebAppButton).order_by(WebAppButton.placement, WebAppButton.position).all()
        if not apps:
            await query.edit_message_text(
                "🗑 **حذف تطبيق**\n\n📭 لا توجد تطبيقات مضافة بعد.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع", callback_data="ui_webapps")]
                ]),
                parse_mode="Markdown"
            )
            return

        pl_icon = {"inline": "💬", "reply_keyboard": "⌨️",
                   "menu_button": "📱", "bot_menu": "📂"}
        kb = []
        for a in apps:
            status = "✅" if a.is_active else "❌"
            icon = pl_icon.get(a.placement, "📍")
            label_short = a.label[:26] + "…" if len(a.label) > 26 else a.label
            kb.append([InlineKeyboardButton(
                f"{status} {icon} [{a.id}] {label_short}",
                callback_data=f"ui_wa_del_confirm_{a.id}"
            )])

        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="ui_webapps"),
                   InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")])
        await query.edit_message_text(
            "🗑 **حذف تطبيق Web App**\n\n"
            "اختر التطبيق الذي تريد حذفه:\n"
            "_(✅ = نشط، ❌ = معطّل — سيُطلب تأكيد قبل الحذف)_",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    finally:
        db.close()


async def ui_wa_del_confirm(query, context, wa_id: int):
    from bot.admin.ui_keyboards import ui_wa_delete_confirm_keyboard
    from bot.utils.button_engine import PLACEMENT_LABELS
    db = SessionLocal()
    try:
        wa = db.query(WebAppButton).filter_by(id=wa_id).first()
        if not wa:
            await query.answer("❌ التطبيق غير موجود", show_alert=True)
            return
        pl = PLACEMENT_LABELS.get(wa.placement, wa.placement)
        url_short = wa.url[:50] + "..." if len(wa.url) > 50 else wa.url
        status = "✅ نشط" if wa.is_active else "❌ معطّل"
        text = (
            f"⚠️ **تأكيد الحذف**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷 **{wa.label}**\n"
            f"📍 {pl}\n"
            f"🔗 `{url_short}`\n"
            f"📊 {status}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"هل أنت متأكد من حذف هذا التطبيق؟\n"
            f"⚠️ **هذا الإجراء لا يمكن التراجع عنه!**"
        )
    finally:
        db.close()
    await query.edit_message_text(
        text,
        reply_markup=ui_wa_delete_confirm_keyboard(wa_id),
        parse_mode="Markdown"
    )


async def ui_wa_delete(query, context, wa_id: int):
    from bot.utils.button_engine import remove_menu_button
    db = SessionLocal()
    try:
        wa = db.query(WebAppButton).filter_by(id=wa_id).first()
        if wa:
            was_menu_btn = wa.placement == "menu_button"
            label = wa.label
            db.delete(wa)
            db.commit()
            if was_menu_btn:
                await remove_menu_button(context.bot)
            await query.answer(f"✅ تم حذف «{label}» بنجاح", show_alert=True)
        else:
            await query.answer("❌ التطبيق غير موجود", show_alert=True)
    finally:
        db.close()
    await ui_wa_delete_pick(query, context)


async def ui_wa_detail(query, context, wa_id: int):
    from bot.utils.button_engine import PLACEMENT_LABELS
    db = SessionLocal()
    try:
        wa = db.query(WebAppButton).filter_by(id=wa_id).first()
        if not wa:
            await query.answer("❌ التطبيق غير موجود", show_alert=True)
            return
        status = "✅ نشط" if wa.is_active else "❌ معطّل"
        placement_label = PLACEMENT_LABELS.get(wa.placement, wa.placement)
        loc_map = {"start": "👋 /start", "help": "❓ /help",
                   "sub": "📢 الاشتراك", "download": "📥 التحميل",
                   "global": "🌐 عامة", "custom": "📌 مخصص"}
        url_short = wa.url[:50] + "..." if len(wa.url) > 50 else wa.url
        text = (
            f"🌐 <b>تفاصيل Web App #{wa.id}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷 العنوان:   <b>{_e(wa.label)}</b>\n"
            f"🔗 الرابط:    <code>{_e(url_short)}</code>\n"
            f"📍 الموضع:   {_e(placement_label)}\n"
        )
        if wa.placement == "inline":
            text += f"📋 الرسالة:   {_e(loc_map.get(wa.location, wa.location))}\n"
        text += (
            f"📶 الترتيب:   {wa.position}\n"
            f"📊 الحالة:    {status}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(
            text,
            reply_markup=ui_wa_detail_keyboard(wa.id, wa.is_active, wa.placement),
            parse_mode="HTML"
        )
    finally:
        db.close()


async def ui_wa_toggle(query, context, wa_id: int, enable: bool):
    db = SessionLocal()
    try:
        wa = db.query(WebAppButton).filter_by(id=wa_id).first()
        if wa:
            wa.is_active = enable
            db.commit()
            state = "مُفعَّل ✅" if enable else "معطّل ❌"
            await query.answer(f"تم: التطبيق الآن {state}", show_alert=True)
    finally:
        db.close()
    await ui_wa_detail(query, context, wa_id)


async def ui_wa_placement_manage(query, context):
    from bot.utils.button_engine import PLACEMENT_LABELS
    db = SessionLocal()
    try:
        inline_c = db.query(WebAppButton).filter_by(placement="inline", is_active=True).count()
        reply_c = db.query(WebAppButton).filter_by(placement="reply_keyboard", is_active=True).count()
        menu_c = db.query(WebAppButton).filter_by(placement="menu_button", is_active=True).count()
        bot_menu_c = db.query(WebAppButton).filter_by(placement="bot_menu", is_active=True).count()
    finally:
        db.close()
    text = (
        "📍 **إدارة مواضع Web App Buttons**\n\n"
        "كل موضع يحدد **أين يظهر الزر** للمستخدم داخل تيليجرام.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 **داخل الرسائل (Inline):**\n"
        f"   {inline_c} تطبيق نشط — يظهر أسفل رسالة محددة\n\n"
        f"⌨️ **لوحة المفاتيح (Reply Keyboard):**\n"
        f"   {reply_c} تطبيق نشط — يظهر دائماً أسفل الشاشة\n\n"
        f"📱 **شريط المدخلات (Menu Button):**\n"
        f"   {menu_c} تطبيق — يظهر بجانب حقل الكتابة ★\n\n"
        f"📂 **قائمة البوت (Bot Menu):**\n"
        f"   {bot_menu_c} تطبيق مضاف\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"★ = يتطلب ضبطاً مباشراً عبر Telegram API\n\n"
        f"اختر الموضع لإدارته:"
    )
    await query.edit_message_text(
        text,
        reply_markup=ui_wa_placement_manage_keyboard(),
        parse_mode="Markdown"
    )


async def ui_wa_pm_show(query, context, placement: str):
    from bot.utils.button_engine import PLACEMENT_LABELS
    loc_map = {"start": "👋 /start", "help": "❓ /help",
               "sub": "📢 الاشتراك", "download": "📥 التحميل",
               "global": "🌐 عامة", "custom": "📌 مخصص"}
    db = SessionLocal()
    try:
        apps = db.query(WebAppButton).filter_by(placement=placement, is_active=True).all()
        label = PLACEMENT_LABELS.get(placement, placement)
        if not apps:
            text = (
                f"📍 **{label}**\n\n"
                f"📭 لا توجد تطبيقات Web App في هذا الموضع بعد.\n\n"
                f"استخدم «➕ إضافة Web App جديد» واختر الموضع المناسب."
            )
        else:
            lines = [f"📍 **{label}** ({len(apps)} تطبيق)\n━━━━━━━━━━━━━━━━━━━━"]
            for wa in apps:
                url_s = wa.url[:35] + "..." if len(wa.url) > 35 else wa.url
                loc = loc_map.get(wa.location, wa.location) if placement == "inline" else ""
                lines.append(f"✅ `[{wa.id}]` **{wa.label}**\n   🔗 `{url_s}` {loc}")
            text = "\n".join(lines)
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة تطبيق في هذا الموضع", callback_data="ui_wa_add")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="ui_wa_placement_manage"),
                 InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
            ]),
            parse_mode="Markdown"
        )
    finally:
        db.close()


async def ui_wa_pm_menu_button(query, context):
    db = SessionLocal()
    try:
        # prefer active; fall back to any menu_button app
        menu_wa = db.query(WebAppButton).filter_by(
            placement="menu_button", is_active=True
        ).first()
        if not menu_wa:
            menu_wa = db.query(WebAppButton).filter_by(
                placement="menu_button"
            ).first()
    finally:
        db.close()

    if menu_wa:
        url_short = menu_wa.url[:50] + "..." if len(menu_wa.url) > 50 else menu_wa.url
        status_line = "✅ نشط" if menu_wa.is_active else "❌ معطّل"
        text = (
            "📱 **إدارة شريط المدخلات (Menu Button)**\n\n"
            "يظهر هذا الزر كأيقونة بجانب حقل الكتابة.\n"
            "الضغط عليه يفتح التطبيق / المتجر مباشرةً.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 التطبيق المُعيَّن:\n"
            f"🏷 **{menu_wa.label}**\n"
            f"🔗 `{url_short}`\n"
            f"📊 الحالة: {status_line}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "⬇️ اضغط **«تطبيق في تيليجرام الآن»** لتفعيله فعلياً في تيليجرام:"
        )
        wa_id = menu_wa.id
    else:
        text = (
            "📱 **إدارة شريط المدخلات (Menu Button)**\n\n"
            "📭 لا يوجد تطبيق بموضع «Menu Button» بعد.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "لإضافة زر:\n"
            "1️⃣ اضغط «➕ إضافة تطبيق بموضع Menu Button»\n"
            "2️⃣ أدخل العنوان والرابط\n"
            "3️⃣ اختر «📱 شريط المدخلات» كموضع\n"
            "4️⃣ ارجع هنا واضغط «تطبيق الآن»\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        wa_id = None

    await query.edit_message_text(
        text,
        reply_markup=ui_wa_menu_button_keyboard(
            has_menu_btn=(menu_wa is not None),
            wa_id=wa_id
        ),
        parse_mode="Markdown"
    )


async def ui_wa_apply_menu_button(query, context, wa_id: int):
    from bot.utils.button_engine import apply_menu_button
    db = SessionLocal()
    try:
        wa = db.query(WebAppButton).filter_by(id=wa_id).first()
        if not wa:
            await query.answer("❌ التطبيق غير موجود", show_alert=True)
            return
        success = await apply_menu_button(context.bot, wa.label, wa.url)
        came_from = context.user_data.get("menu_btn_source", "pm")
    finally:
        db.close()
    if success:
        await query.answer("✅ تم تفعيل Menu Button في تيليجرام!", show_alert=True)
    else:
        await query.answer("❌ فشل الضبط — تأكد أن الرابط مُسجَّل في Bot Domain", show_alert=True)
    # always return to the menu button management screen
    await ui_wa_pm_menu_button(query, context)


async def ui_wa_remove_menu_button(query, context):
    from bot.utils.button_engine import remove_menu_button
    success = await remove_menu_button(context.bot)
    if success:
        await query.answer("✅ تم إزالة Menu Button من تيليجرام", show_alert=True)
    else:
        await query.answer("❌ فشلت الإزالة — حاول مرة أخرى", show_alert=True)
    await ui_wa_pm_menu_button(query, context)


async def ui_wa_add_menu_btn(query, context):
    await query.edit_message_text(
        "📱 **إضافة Menu Button**\n\n"
        "استخدم «➕ إضافة Web App جديد» واختر\n"
        "الموضع «📱 شريط المدخلات (Menu Button)»\n"
        "ثم ارجع هنا واضغط «تطبيق الآن».",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة Web App جديد", callback_data="ui_wa_add")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="ui_wa_pm_menu_button"),
             InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
        ]),
        parse_mode="Markdown"
    )


async def ui_wa_select_placement(query, context, placement: str):
    context.user_data["new_wa_placement"] = placement
    from bot.utils.button_engine import PLACEMENT_LABELS
    label = PLACEMENT_LABELS.get(placement, placement)
    if placement == "inline":
        await query.edit_message_text(
            f"🌐 **إضافة Web App Button**\n"
            f"الخطوة 3b/3 — مكان الرسالة\n\n"
            f"الموضع المختار: **{label}**\n\n"
            f"في أي رسالة يظهر هذا الزر؟",
            reply_markup=ui_wa_inline_location_keyboard(),
            parse_mode="Markdown"
        )
    else:
        context.user_data["new_wa_location"] = "global"
        await _do_save_webapp(query, context)


async def ui_wa_select_location(query, context, location: str):
    context.user_data["new_wa_location"] = location
    await _do_save_webapp(query, context)


async def _do_save_webapp(query, context):
    from bot.utils.button_engine import PLACEMENT_LABELS, apply_menu_button
    label = context.user_data.get("new_wa_label", "Web App")
    url = context.user_data.get("new_wa_url", "")
    placement = context.user_data.get("new_wa_placement", "inline")
    location = context.user_data.get("new_wa_location", "start")
    placement_label = PLACEMENT_LABELS.get(placement, placement)
    loc_map = {"start": "👋 /start", "help": "❓ /help",
               "sub": "📢 الاشتراك", "download": "📥 التحميل",
               "global": "🌐 عامة (لوحة المفاتيح/القائمة)", "custom": "📌 مخصص"}
    db = SessionLocal()
    try:
        max_pos = db.query(WebAppButton).filter_by(placement=placement).count()
        wa = WebAppButton(
            label=label, url=url,
            placement=placement, location=location,
            position=max_pos
        )
        db.add(wa)
        db.commit()
        wa_id = wa.id
    finally:
        db.close()
    for k in ("new_wa_label", "new_wa_url", "new_wa_placement", "new_wa_location", "waiting_for"):
        context.user_data.pop(k, None)
    menu_note = ""
    if placement == "menu_button":
        applied = await apply_menu_button(context.bot, label, url)
        menu_note = (
            "\n\n✅ تم ضبط Menu Button في تيليجرام فوراً!" if applied
            else "\n\n⚠️ احتجت ضبط Menu Button يدوياً من «إدارة المواضع»"
        )
    text = (
        f"✅ **تم إضافة Web App Button بنجاح!**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷 العنوان:   **{label}**\n"
        f"🔗 الرابط:    `{url[:50]}`\n"
        f"📍 الموضع:   {placement_label}\n"
        f"📋 المكان:    {loc_map.get(location, location)}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
        f"{menu_note}"
    )
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 عرض التطبيقات", callback_data="ui_wa_list_0")],
            [InlineKeyboardButton("➕ إضافة آخر", callback_data="ui_wa_add"),
             InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main")],
        ]),
        parse_mode="Markdown"
    )


async def ui_wa_edit_label_start(query, context, wa_id: int):
    context.user_data["waiting_for"] = f"ui_wa_new_label_{wa_id}"
    await query.edit_message_text(
        f"✏️ **تعديل عنوان Web App #{wa_id}**\n\n"
        f"✏️ أرسل العنوان الجديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"ui_wa_detail_{wa_id}")]
        ]),
        parse_mode="Markdown"
    )


async def ui_wa_edit_url_start(query, context, wa_id: int):
    context.user_data["waiting_for"] = f"ui_wa_new_url_{wa_id}"
    await query.edit_message_text(
        f"✏️ **تعديل رابط Web App #{wa_id}**\n\n"
        f"🌐 أرسل الرابط الجديد (يجب أن يبدأ بـ https://):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"ui_wa_detail_{wa_id}")]
        ]),
        parse_mode="Markdown"
    )


async def ui_activity_main(query, context):
    current = get_setting("activity_status", "upload_video")
    label = ACTIVITY_LABELS.get(current, current)
    await query.edit_message_text(
        f"⚡ **حالة نشاط البوت**\n\n"
        f"الحالة الحالية: **{label}**\n\n"
        f"اختر الحالة الجديدة:\n"
        f"_(هذا ما يظهر تحت اسم البوت أثناء معالجة الروابط)_",
        reply_markup=ui_activity_keyboard(current),
        parse_mode="Markdown"
    )


async def ui_activity_set(query, context, activity: str):
    set_setting("activity_status", activity)
    label = ACTIVITY_LABELS.get(activity, activity)
    await query.answer(f"✅ تم تغيير حالة النشاط إلى: {label}", show_alert=True)
    await ui_activity_main(query, context)


async def ui_langs_main(query, context):
    db = SessionLocal()
    try:
        enabled_count = db.query(BotLanguage).filter_by(is_enabled=True).count()
        total_count = db.query(BotLanguage).count()
    finally:
        db.close()
    await query.edit_message_text(
        "🌍 **إدارة اللغات**\n\n"
        f"🟢 اللغات المفعّلة للمستخدمين: **{enabled_count}** من {total_count}\n\n"
        "📝 **ترجمة الرسائل** — تخصيص نصوص البوت\n"
        "🔧 **اللغات المتاحة** — تفعيل/تعطيل اللغات للمستخدمين",
        reply_markup=ui_langs_keyboard(),
        parse_mode="Markdown"
    )


async def ui_avail_langs(query, context, page: int = 0):
    """Show 50-language grid with enable/disable toggles, paginated 10 per page."""
    db = SessionLocal()
    try:
        all_langs = db.query(BotLanguage).order_by(BotLanguage.position).all()
        total = len(all_langs)
        per_page = 10
        total_pages = (total + per_page - 1) // per_page
        page = max(0, min(page, total_pages - 1))
        chunk = all_langs[page * per_page: (page + 1) * per_page]

        enabled_codes = {l.code for l in all_langs if l.is_enabled}
        lines = [
            f"🌐 **اللغات المتاحة** (صفحة {page+1}/{total_pages})\n\n"
            f"🟢 المفعّل: {len(enabled_codes)} لغة | المجموع: {total}\n\n"
            "اضغط على لغة لتفعيلها أو تعطيلها:"
        ]

        rows = []
        pair = []
        for lang in chunk:
            icon = "✅" if lang.is_enabled else "❌"
            lock = " 🔒" if lang.is_builtin else ""
            label = f"{icon} {lang.flag} {lang.name}{lock}"
            pair.append(InlineKeyboardButton(label, callback_data=f"ui_avail_toggle_{lang.code}_{page}"))
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            rows.append(pair)

        # Pagination
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"ui_avail_langs_{page-1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"ui_avail_langs_{page+1}"))
        if nav:
            rows.append(nav)

        rows.append([
            InlineKeyboardButton("🔙 رجوع", callback_data="ui_langs"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main"),
        ])

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="Markdown"
        )
    finally:
        db.close()


async def ui_avail_toggle(query, context, code: str, page: int = 0):
    """Toggle enable/disable for a language (builtin languages are protected)."""
    db = SessionLocal()
    try:
        lang = db.query(BotLanguage).filter_by(code=code).first()
        if not lang:
            await query.answer("⚠️ اللغة غير موجودة", show_alert=True)
            return
        if lang.is_builtin:
            await query.answer("🔒 اللغات المدمجة لا يمكن تعطيلها", show_alert=True)
            return
        lang.is_enabled = not lang.is_enabled
        db.commit()
        status = "✅ مفعّلة" if lang.is_enabled else "❌ معطّلة"
        await query.answer(f"{lang.flag} {lang.name} {status}")
    finally:
        db.close()
    await ui_avail_langs(query, context, page)


async def ui_lang_edit(query, context, lang: str):
    label = LANG_LABELS.get(lang, lang)
    await query.edit_message_text(
        f"🌍 **تعديل ترجمات {label}**\n\n"
        f"اختر الرسالة التي تريد تعديل ترجمتها:",
        reply_markup=ui_lang_edit_keyboard(lang),
        parse_mode="Markdown"
    )


async def ui_lang_translate(query, context, msg_type: str, lang: str):
    db_key_base = LANG_MESSAGE_KEYS.get(msg_type, msg_type)
    db_key = f"{db_key_base}_{lang}"
    current = get_setting(db_key, "")
    if not current:
        current = get_setting(db_key_base, "")
    lang_label = LANG_LABELS.get(lang, lang)
    context.user_data["waiting_for"] = f"ui_lang_tr_{db_key}"
    context.user_data["ui_lang_db_key"] = db_key
    await query.edit_message_text(
        f"✏️ <b>ترجمة {_e(lang_label)}</b>\n\n"
        f"الرسالة: <b>{_e(msg_type)}</b>\n\n"
        f"📝 النص الحالي:\n<code>{_e(current or '(لم يُعيَّن)')}</code>\n\n"
        f"أرسل الترجمة الجديدة:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"ui_lang_edit_{lang}")]
        ]),
        parse_mode="HTML"
    )


async def ui_format_main(query, context):
    current = get_setting("text_format", "none")
    await query.edit_message_text(
        f"🎨 **تنسيق النصوص**\n\n"
        f"التنسيق الحالي: **{FORMAT_LABELS.get(current, current)}**\n\n"
        f"اختر تنسيق الرسائل:",
        reply_markup=ui_format_keyboard(current),
        parse_mode="Markdown"
    )


async def ui_format_set(query, context, fmt: str):
    set_setting("text_format", fmt)
    label = FORMAT_LABELS.get(fmt, fmt)
    await query.answer(f"✅ تم تغيير تنسيق النص إلى: {label}", show_alert=True)
    await ui_format_main(query, context)


async def ui_platforms_main(query, context):
    from bot.utils.platforms import PLATFORMS
    settings = {}
    for key, info in PLATFORMS.items():
        db_key = info["db_key"]
        default = "true" if info.get("default_enabled", False) else "false"
        settings[db_key] = get_setting(db_key, default)
    await query.edit_message_text(
        "🎵 **إدارة منصات التحميل**\n\n"
        "✅ = مفعّل  |  ❌ = معطّل\n\n"
        "اختر منصة لتفعيلها أو تعطيلها وتعديل رسالة ردها:",
        reply_markup=ui_platforms_keyboard(settings),
        parse_mode="Markdown"
    )


async def ui_platform_detail(query, context, platform: str):
    from bot.utils.platforms import PLATFORMS
    label = _get_platform_label(platform)
    info = PLATFORMS.get(platform, {})
    default_enabled = "true" if info.get("default_enabled", False) else "false"
    enabled_val = get_setting(f"{platform}_enabled", default_enabled)
    enabled = enabled_val == "true"
    disabled_msg = get_setting(f"{platform}_disabled_msg", f"عذراً، {label} غير مدعوم حالياً.")
    db = SessionLocal()
    try:
        from bot.database import Download
        count = db.query(Download).filter_by(platform=platform, success=True).count()
    finally:
        db.close()
    status_txt = "✅ مفعّل" if enabled else "❌ معطّل"
    msg_preview = disabled_msg[:100] + "..." if len(disabled_msg) > 100 else disabled_msg
    await query.edit_message_text(
        f"{label}\n\n"
        f"الحالة: **{status_txt}**\n"
        f"رسالة التعطيل: `{msg_preview}`\n"
        f"التحميلات الكلية: **{count}**\n\n"
        f"اختر الإجراء:",
        reply_markup=ui_platform_detail_keyboard(platform, enabled),
        parse_mode="Markdown"
    )


async def ui_platform_toggle(query, context, platform: str, enable: bool):
    label = _get_platform_label(platform)
    set_setting(f"{platform}_enabled", "true" if enable else "false")
    action = "تفعيل" if enable else "تعطيل"
    await query.answer(f"✅ تم {action} {label}", show_alert=True)
    await ui_platform_detail(query, context, platform)


async def ui_platform_editmsg(query, context, platform: str):
    label = _get_platform_label(platform)
    current = get_setting(f"{platform}_disabled_msg", f"عذراً، {label} غير مدعوم حالياً.")
    context.user_data["waiting_for"] = f"ui_plat_msg_{platform}"
    context.user_data["ui_plat_db_key"] = f"{platform}_disabled_msg"
    await query.edit_message_text(
        f"✏️ <b>تعديل رسالة {_e(label)}</b>\n\n"
        f"📝 <b>النص الحالي:</b>\n<code>{_e(current)}</code>\n\n"
        f"أرسل النص الجديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"ui_plat_{platform}")]
        ]),
        parse_mode="HTML"
    )


async def ui_platform_stats(query, context, platform: str):
    label = _get_platform_label(platform)
    db = SessionLocal()
    try:
        from bot.database import Download
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        total = db.query(Download).filter_by(platform=platform, success=True).count()
        today = db.query(Download).filter(
            Download.platform == platform,
            Download.success == True,
            Download.downloaded_at >= now - timedelta(days=1)
        ).count()
        week = db.query(Download).filter(
            Download.platform == platform,
            Download.success == True,
            Download.downloaded_at >= now - timedelta(days=7)
        ).count()
        month = db.query(Download).filter(
            Download.platform == platform,
            Download.success == True,
            Download.downloaded_at >= now - timedelta(days=30)
        ).count()
        users = db.query(Download.user_id).filter_by(platform=platform, success=True).distinct().count()
    finally:
        db.close()
    await query.edit_message_text(
        f"📊 **إحصائيات {label}**\n\n"
        f"📥 إجمالي التحميلات: **{total}**\n"
        f"👥 مستخدمين فريدين: **{users}**\n\n"
        f"📅 اليوم: **{today}**\n"
        f"📅 هذا الأسبوع: **{week}**\n"
        f"📅 هذا الشهر: **{month}**",
        reply_markup=ui_back(f"ui_plat_{platform}"),
        parse_mode="Markdown"
    )


async def ui_plat_responses_main(query, context):
    unsup = get_setting("unsupported_platform_msg", "⚠️ هذه المنصة غير مدعومة حالياً.")
    await query.edit_message_text(
        "⚙️ <b>إعدادات ردود المنصات</b>\n\n"
        f"رسالة منصة غير مدعومة:\n<code>{_e(unsup)}</code>\n\n"
        "اختر الرد الذي تريد تعديله:",
        reply_markup=ui_plat_responses_keyboard(),
        parse_mode="HTML"
    )


async def ui_plat_edit_unsupported(query, context):
    current = get_setting("unsupported_platform_msg", "⚠️ هذه المنصة غير مدعومة حالياً.")
    context.user_data["waiting_for"] = "ui_plat_msg_unsupported_generic"
    context.user_data["ui_plat_db_key"] = "unsupported_platform_msg"
    await query.edit_message_text(
        f"⚠️ <b>رسالة المنصة غير المدعومة</b>\n\n"
        f"📝 <b>النص الحالي:</b>\n<code>{_e(current)}</code>\n\n"
        f"أرسل النص الجديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="ui_plat_responses")]
        ]),
        parse_mode="HTML"
    )


async def ui_plat_edit_disabled_generic(query, context):
    current = get_setting("disabled_platform_generic_msg",
                          "عذراً، هذه المنصة غير مفعلة حالياً في البوت.")
    context.user_data["waiting_for"] = "ui_plat_msg_disabled_generic"
    context.user_data["ui_plat_db_key"] = "disabled_platform_generic_msg"
    await query.edit_message_text(
        f"🚫 <b>رسالة المنصة المعطلة (عامة)</b>\n\n"
        f"📝 <b>النص الحالي:</b>\n<code>{_e(current)}</code>\n\n"
        f"أرسل النص الجديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="ui_plat_responses")]
        ]),
        parse_mode="HTML"
    )


async def ui_caption_main(query, context):
    vid_cap = get_setting("video_caption", DEFAULT_MESSAGES["video_caption"])
    photo_cap = get_setting("photo_caption", DEFAULT_MESSAGES["photo_caption"])
    await query.edit_message_text(
        "📦 <b>إدارة Caption الوسائط</b>\n\n"
        f"📹 Caption الفيديو:\n<code>{_e(vid_cap)}</code>\n\n"
        f"🖼 Caption الصور:\n<code>{_e(photo_cap)}</code>\n\n"
        "اختر ما تريد تعديله:",
        reply_markup=ui_caption_keyboard(),
        parse_mode="HTML"
    )


async def ui_caption_edit(query, context, cap_type: str):
    db_key = "video_caption" if cap_type == "video" else "photo_caption"
    default = DEFAULT_MESSAGES[db_key]
    current = get_setting(db_key, default)
    label = "📹 Caption الفيديو" if cap_type == "video" else "🖼 Caption الصور"
    context.user_data["waiting_for"] = f"ui_caption_{cap_type}"
    context.user_data["ui_cap_db_key"] = db_key
    await query.edit_message_text(
        f"✏️ <b>تعديل {_e(label)}</b>\n\n"
        f"📝 <b>النص الحالي:</b>\n<code>{_e(current)}</code>\n\n"
        f"يمكنك استخدام: <code>{{bot_name}}</code> لاسم البوت\n\n"
        f"أرسل النص الجديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="ui_caption")]
        ]),
        parse_mode="HTML"
    )


async def ui_preview_main(query, context):
    await query.edit_message_text(
        "👁 **معاينة الواجهة**\n\nاختر ما تريد معاينته:",
        reply_markup=ui_preview_keyboard(),
        parse_mode="Markdown"
    )


async def ui_preview_item(query, context, item: str):
    bot_name = get_setting("bot_name", "SaveEliteBot")
    user_name = query.from_user.first_name or "المستخدم"

    previews = {
        "start": ("start_message", f"👋 **معاينة رسالة البداية**"),
        "sub": ("subscription_message", f"📢 **معاينة رسالة الاشتراك**"),
        "help": ("help_message", f"❓ **معاينة رسالة المساعدة**"),
        "download": ("downloading_message", f"📥 **معاينة رسالة التحميل**"),
    }

    if item in previews:
        db_key, title = previews[item]
        default = DEFAULT_MESSAGES.get(db_key, "")
        text = get_setting(db_key, default)
        text = text.replace("{name}", user_name).replace("{bot_name}", bot_name)
        await query.answer()
        await query.message.reply_text(
            f"{title}\n\n{'─' * 20}\n{text}\n{'─' * 20}",
            parse_mode="Markdown"
        )
        return

    if item == "buttons":
        db = SessionLocal()
        try:
            buttons = db.query(BotButton).filter_by(is_active=True).limit(10).all()
            webapps = db.query(WebAppButton).filter_by(is_active=True).limit(5).all()
        finally:
            db.close()
        type_map = {"inline": "🔘 Inline", "reply": "⌨️ Reply", "url": "🔗 URL",
                    "callback": "⚙️ Callback", "webapp": "🌐 WebApp"}
        lines = [f"🔘 **معاينة الأزرار** ({len(buttons)} زر، {len(webapps)} WebApp)\n"]
        for b in buttons:
            lines.append(f"  {type_map.get(b.button_type, '?')} [{b.location}] **{b.label}**")
        if webapps:
            lines.append(f"\n🌐 **Web Apps:**")
            for w in webapps:
                lines.append(f"  🌐 [{w.location}] **{w.label}** → {w.url[:30]}...")
        await query.answer()
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif item == "platforms":
        from bot.utils.platforms import PLATFORMS
        lines = ["🎵 **حالة المنصات**\n"]
        for p, info in PLATFORMS.items():
            db_key = info["db_key"]
            default = "true" if info.get("default_enabled", False) else "false"
            status = "✅" if get_setting(db_key, default) == "true" else "❌"
            label = _get_platform_label(p)
            lines.append(f"  {status} {label}")
        await query.answer()
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def ui_reset_confirm(query, context):
    await query.edit_message_text(
        "⚠️ **إعادة ضبط الواجهة**\n\n"
        "سيتم إعادة جميع الرسائل والإعدادات إلى القيم الافتراضية.\n"
        "لن يتم حذف الأزرار المضافة.\n\n"
        "**هل أنت متأكد؟**",
        reply_markup=ui_reset_confirm_keyboard(),
        parse_mode="Markdown"
    )


async def ui_reset_execute(query, context):
    for key, value in DEFAULT_MESSAGES.items():
        set_setting(key, value)
    set_setting("activity_status", "upload_video")
    set_setting("text_format", "none")
    await query.answer("✅ تم إعادة ضبط الواجهة بنجاح", show_alert=True)
    await ui_main(query, context)


async def ui_handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Called from admin_message_handler to handle UI-related text inputs.
    Returns True if handled, False otherwise.
    """
    waiting = context.user_data.get("waiting_for", "")
    text = update.message.text.strip()

    if waiting.startswith("ui_msg_text_"):
        msg_key = waiting.replace("ui_msg_text_", "")
        db_key = context.user_data.get("ui_msg_key", "")
        if db_key:
            set_setting(db_key, text)
            _, label, _ = MESSAGE_LABELS.get(msg_key, (db_key, msg_key, False))
            await update.message.reply_text(
                f"✅ **تم تحديث {label}**\n\n📝 النص الجديد:\n`{text[:200]}`",
                parse_mode="Markdown"
            )
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("ui_msg_key", None)
        return True

    if waiting == "ui_btn_label":
        context.user_data["new_btn_label"] = text
        btn_type = context.user_data.get("new_btn_type", "url")
        if btn_type == "url":
            context.user_data["waiting_for"] = "ui_btn_data_url"
            await update.message.reply_text(
                f"✅ العنوان: **{text}**\n\n"
                f"🔗 أرسل الآن **رابط URL** (يبدأ بـ https://):\n"
                f"_مثال: https://t.me/channel_",
                parse_mode="Markdown"
            )
        elif btn_type == "webapp":
            context.user_data["waiting_for"] = "ui_btn_data_webapp"
            await update.message.reply_text(
                f"✅ العنوان: **{text}**\n\n"
                f"🌐 أرسل **رابط Web App** (يبدأ بـ https://):\n"
                f"_سيفتح داخل تيليجرام كـ Mini App_",
                parse_mode="Markdown"
            )
        elif btn_type == "reply_webapp":
            context.user_data["waiting_for"] = "ui_btn_data_reply_webapp"
            await update.message.reply_text(
                f"✅ العنوان: **{text}**\n\n"
                f"📱 أرسل **رابط Web App** (يبدأ بـ https://):\n"
                f"_سيظهر كلوحة مفاتيح أسفل الشاشة ويفتح Mini App_",
                parse_mode="Markdown"
            )
        elif btn_type == "callback":
            context.user_data["waiting_for"] = "ui_btn_data_callback"
            await update.message.reply_text(
                f"✅ العنوان: **{text}**\n\n"
                f"⚙️ أرسل **Callback Data** للزر:\n"
                f"_مثال: my\\_action\\_here_",
                parse_mode="Markdown"
            )
        elif btn_type == "reply":
            context.user_data["waiting_for"] = "ui_btn_data_reply"
            await update.message.reply_text(
                f"✅ اسم الزر في لوحة المفاتيح: **{text}**\n\n"
                f"💬 الخطوة 2/2 — رسالة الرد\n\n"
                f"أرسل الآن **نص الرد** الذي سيظهر للمستخدم عند ضغط هذا الزر:\n\n"
                f"_يمكنك استخدام \\{{name\\}} لاسم المستخدم و \\{{bot\\_name\\}} لاسم البوت_",
                parse_mode="Markdown"
            )
        else:
            await _save_button(update, context, text, "")
        return True

    if waiting == "ui_btn_data_reply":
        label = context.user_data.get("new_btn_label", "زر")
        await _save_button(update, context, label, text)
        return True

    if waiting in ("ui_btn_data_url", "ui_btn_data_callback",
                   "ui_btn_data_webapp", "ui_btn_data_reply_webapp"):
        if waiting in ("ui_btn_data_url", "ui_btn_data_webapp", "ui_btn_data_reply_webapp"):
            if not text.startswith("http"):
                await update.message.reply_text(
                    "❌ الرابط يجب أن يبدأ بـ **https://**\n\nأعد إرسال الرابط:",
                    parse_mode="Markdown"
                )
                return True
        await _save_button(update, context, context.user_data.get("new_btn_label", "زر"), text)
        return True

    if waiting == "ui_wa_label":
        context.user_data["new_wa_label"] = text
        context.user_data["waiting_for"] = "ui_wa_url"
        await update.message.reply_text(
            f"✅ العنوان: **{text}**\n\n"
            f"🌐 الخطوة 2/3 — الرابط\n\n"
            f"أرسل **رابط Web App** (يجب أن يبدأ بـ https://):\n"
            f"_تأكد أن الرابط مُسجَّل في Bot Domain عند @BotFather_",
            parse_mode="Markdown"
        )
        return True

    if waiting == "ui_wa_url":
        if not text.startswith("http"):
            await update.message.reply_text(
                "❌ **الرابط غير صالح**\n\n"
                "الرابط يجب أن يبدأ بـ **https://**\n\n"
                "✏️ أرسل رابطاً صحيحاً:",
                parse_mode="Markdown"
            )
            return True
        context.user_data["new_wa_url"] = text
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ الرابط: `{text[:50]}`\n\n"
            f"📍 **الخطوة 3/3 — موضع الظهور ★**\n\n"
            f"أين يظهر زر التطبيق للمستخدم؟\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 **داخل الرسالة** — زر أسفل رسالة محددة\n"
            f"⌨️ **لوحة المفاتيح** — زر دائم أسفل الشاشة\n"
            f"📱 **شريط المدخلات** — أيقونة بجانب حقل الكتابة\n"
            f"📂 **قائمة البوت** — في قائمة منسدلة\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            reply_markup=ui_wa_placement_keyboard(),
            parse_mode="Markdown"
        )
        return True

    if waiting.startswith("ui_wa_new_label_"):
        try:
            wa_id = int(waiting.replace("ui_wa_new_label_", ""))
        except ValueError:
            return True
        db = SessionLocal()
        try:
            wa = db.query(WebAppButton).filter_by(id=wa_id).first()
            if wa:
                wa.label = text
                db.commit()
        finally:
            db.close()
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ **تم تحديث عنوان التطبيق #{wa_id}**\n\nالعنوان الجديد: **{text}**",
            parse_mode="Markdown"
        )
        return True

    if waiting.startswith("ui_wa_new_url_"):
        try:
            wa_id = int(waiting.replace("ui_wa_new_url_", ""))
        except ValueError:
            return True
        if not text.startswith("http"):
            await update.message.reply_text("❌ الرابط يجب أن يبدأ بـ https://")
            return True
        db = SessionLocal()
        try:
            wa = db.query(WebAppButton).filter_by(id=wa_id).first()
            if wa:
                wa.url = text
                db.commit()
        finally:
            db.close()
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ **تم تحديث رابط التطبيق #{wa_id}**",
            parse_mode="Markdown"
        )
        return True

    if waiting.startswith("ui_btn_new_label_"):
        try:
            btn_id = int(waiting.replace("ui_btn_new_label_", ""))
        except ValueError:
            return True
        db = SessionLocal()
        try:
            btn = db.query(BotButton).filter_by(id=btn_id).first()
            if btn:
                btn.label = text
                btn.name = text
                db.commit()
        finally:
            db.close()
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ **تم تحديث عنوان الزر #{btn_id}**\n\nالعنوان الجديد: **{text}**",
            parse_mode="Markdown"
        )
        return True

    if waiting.startswith("ui_btn_new_data_"):
        try:
            btn_id = int(waiting.replace("ui_btn_new_data_", ""))
        except ValueError:
            return True
        btn_type = context.user_data.get("ui_btn_edit_type", "url")
        if btn_type in ("url", "webapp", "reply_webapp") and not text.startswith("http"):
            await update.message.reply_text("❌ الرابط يجب أن يبدأ بـ https://")
            return True
        db = SessionLocal()
        try:
            btn = db.query(BotButton).filter_by(id=btn_id).first()
            if btn:
                btn.data = text
                db.commit()
        finally:
            db.close()
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("ui_btn_edit_type", None)
        await update.message.reply_text(
            f"✅ **تم تحديث بيانات الزر #{btn_id}**",
            parse_mode="Markdown"
        )
        return True

    if waiting.startswith("ui_lang_tr_"):
        db_key = context.user_data.get("ui_lang_db_key", "")
        if db_key:
            set_setting(db_key, text)
            await update.message.reply_text(
                f"✅ **تم حفظ الترجمة**\n\n`{text[:200]}`",
                parse_mode="Markdown"
            )
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("ui_lang_db_key", None)
        return True

    if waiting.startswith("ui_plat_msg_"):
        db_key = context.user_data.get("ui_plat_db_key", "")
        if db_key:
            set_setting(db_key, text)
            await update.message.reply_text(
                f"✅ **تم تحديث رسالة المنصة**\n\n`{text[:200]}`",
                parse_mode="Markdown"
            )
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("ui_plat_db_key", None)
        return True

    if waiting.startswith("ui_caption_"):
        db_key = context.user_data.get("ui_cap_db_key", "")
        if db_key:
            set_setting(db_key, text)
            await update.message.reply_text(
                f"✅ **تم تحديث Caption**\n\n`{text[:200]}`",
                parse_mode="Markdown"
            )
        context.user_data.pop("waiting_for", None)
        context.user_data.pop("ui_cap_db_key", None)
        return True

    return False


async def _save_button(update, context, label: str, data: str):
    btn_type = context.user_data.get("new_btn_type", "url")
    location = context.user_data.get("new_btn_location", "start")
    db = SessionLocal()
    try:
        max_pos = db.query(BotButton).filter_by(location=location).count()
        btn = BotButton(
            name=label,
            button_type=btn_type,
            label=label,
            data=data,
            location=location,
            position=max_pos
        )
        db.add(btn)
        db.commit()
    finally:
        db.close()
    for key in ("waiting_for", "new_btn_type", "new_btn_location", "new_btn_label"):
        context.user_data.pop(key, None)
    from bot.utils.button_engine import BUTTON_TYPE_DESCRIPTIONS
    type_label = BUTTON_TYPE_DESCRIPTIONS.get(btn_type, {}).get("label", btn_type)
    placement = BUTTON_TYPE_DESCRIPTIONS.get(btn_type, {}).get("placement", "")
    loc_labels = {
        "start": "👋 /start", "help": "❓ /help",
        "sub": "📢 الاشتراك", "download": "📥 التحميل", "custom": "📌 مخصص",
    }
    if btn_type == "reply" and data:
        data_display = f"\n💬 رسالة الرد:\n`{data[:120]}`"
    elif data:
        data_display = f"\n🔗 البيانات: `{data[:60]}`"
    else:
        data_display = ""

    await update.message.reply_text(
        f"✅ **تم إضافة الزر بنجاح**\n\n"
        f"🏷 اسم الزر: **{label}**\n"
        f"📌 النوع: **{type_label}**\n"
        f"📍 المكان: **{loc_labels.get(location, location)}**\n"
        f"{placement}"
        f"{data_display}",
        parse_mode="Markdown"
    )


async def dispatch_ui_callback(query, context, data: str) -> bool:
    """
    Main dispatcher for all ui_ callback data.
    Returns True if handled.
    """
    if data == "adm_ui":
        await ui_main(query, context)
        return True

    if data == "ui_messages":
        await ui_messages(query, context)
        return True

    if data.startswith("ui_msg_") and not data.startswith("ui_msg_all"):
        part = data[len("ui_msg_"):]
        if part in MESSAGE_LABELS:
            await ui_message_detail(query, context, part)
            return True

    if data.startswith("ui_edit_msg_"):
        msg_key = data[len("ui_edit_msg_"):]
        await ui_edit_msg_start(query, context, msg_key)
        return True

    if data.startswith("ui_preview_msg_"):
        msg_key = data[len("ui_preview_msg_"):]
        await ui_preview_msg(query, context, msg_key)
        return True

    if data == "ui_msg_all":
        await ui_msg_all(query, context, 0)
        return True

    if data.startswith("ui_msg_all_"):
        try:
            page = int(data.split("_")[-1])
        except ValueError:
            page = 0
        await ui_msg_all(query, context, page)
        return True

    if data == "ui_buttons":
        await ui_buttons_main(query, context)
        return True

    if data == "ui_btn_add":
        await ui_btn_add(query, context)
        return True

    if data.startswith("ui_btn_type_"):
        btn_type = data[len("ui_btn_type_"):]
        await ui_btn_set_type(query, context, btn_type)
        return True

    if data.startswith("ui_btn_loc_"):
        location = data[len("ui_btn_loc_"):]
        await ui_btn_set_location(query, context, location)
        return True

    if data.startswith("ui_btn_list_"):
        try:
            page = int(data.split("_")[-1])
        except ValueError:
            page = 0
        await ui_btn_list(query, context, page)
        return True

    if data == "ui_btn_delete_pick":
        await ui_btn_delete_pick(query, context)
        return True

    if data.startswith("ui_btn_del_"):
        try:
            btn_id = int(data[len("ui_btn_del_"):])
            await ui_btn_delete(query, context, btn_id)
        except ValueError:
            pass
        return True

    # ── Button Management (new screens) ──────────────────────────────────────
    if data == "ui_btn_edit_pick":
        await ui_btn_edit_pick(query, context)
        return True

    if data.startswith("ui_btn_detail_"):
        try:
            btn_id = int(data[len("ui_btn_detail_"):])
            await ui_btn_detail(query, context, btn_id)
        except ValueError:
            pass
        return True

    if data.startswith("ui_btn_enable_"):
        try:
            btn_id = int(data[len("ui_btn_enable_"):])
            await ui_btn_toggle(query, context, btn_id, True)
        except ValueError:
            pass
        return True

    if data.startswith("ui_btn_disable_"):
        try:
            btn_id = int(data[len("ui_btn_disable_"):])
            await ui_btn_toggle(query, context, btn_id, False)
        except ValueError:
            pass
        return True

    if data.startswith("ui_btn_edit_label_"):
        try:
            btn_id = int(data[len("ui_btn_edit_label_"):])
            await ui_btn_edit_label_start(query, context, btn_id)
        except ValueError:
            pass
        return True

    if data.startswith("ui_btn_edit_data_"):
        try:
            btn_id = int(data[len("ui_btn_edit_data_"):])
            await ui_btn_edit_data_start(query, context, btn_id)
        except ValueError:
            pass
        return True

    if data == "ui_btn_reorder_pick":
        await ui_btn_reorder_pick(query, context)
        return True

    if data.startswith("ui_btn_reorder_loc_"):
        location = data[len("ui_btn_reorder_loc_"):]
        await ui_btn_reorder_location(query, context, location)
        return True

    if data.startswith("ui_btn_up_"):
        try:
            btn_id = int(data[len("ui_btn_up_"):])
            await ui_btn_move(query, context, btn_id, "up")
        except ValueError:
            pass
        return True

    if data.startswith("ui_btn_dn_"):
        try:
            btn_id = int(data[len("ui_btn_dn_"):])
            await ui_btn_move(query, context, btn_id, "dn")
        except ValueError:
            pass
        return True

    # ── Web App Manager ───────────────────────────────────────────────────────
    if data == "ui_webapps":
        await ui_webapps_main(query, context)
        return True

    if data == "ui_wa_add":
        await ui_wa_add_start(query, context)
        return True

    if data.startswith("ui_wa_list_"):
        try:
            page = int(data.split("_")[-1])
        except ValueError:
            page = 0
        await ui_wa_list(query, context, page)
        return True

    if data == "ui_wa_delete_pick":
        await ui_wa_delete_pick(query, context)
        return True

    if data.startswith("ui_wa_del_confirm_"):
        try:
            wa_id = int(data[len("ui_wa_del_confirm_"):])
            await ui_wa_del_confirm(query, context, wa_id)
        except ValueError:
            pass
        return True

    if data.startswith("ui_wa_del_"):
        try:
            wa_id = int(data[len("ui_wa_del_"):])
            await ui_wa_delete(query, context, wa_id)
        except ValueError:
            pass
        return True

    if data.startswith("ui_wa_detail_"):
        try:
            wa_id = int(data[len("ui_wa_detail_"):])
            await ui_wa_detail(query, context, wa_id)
        except ValueError:
            pass
        return True

    if data.startswith("ui_wa_enable_"):
        try:
            wa_id = int(data[len("ui_wa_enable_"):])
            await ui_wa_toggle(query, context, wa_id, True)
        except ValueError:
            pass
        return True

    if data.startswith("ui_wa_disable_"):
        try:
            wa_id = int(data[len("ui_wa_disable_"):])
            await ui_wa_toggle(query, context, wa_id, False)
        except ValueError:
            pass
        return True

    if data == "ui_wa_placement_manage":
        await ui_wa_placement_manage(query, context)
        return True

    if data.startswith("ui_wa_pm_menu_button"):
        await ui_wa_pm_menu_button(query, context)
        return True

    if data.startswith("ui_wa_pm_"):
        placement = data[len("ui_wa_pm_"):]
        await ui_wa_pm_show(query, context, placement)
        return True

    if data.startswith("ui_wa_pl_"):
        placement = data[len("ui_wa_pl_"):]
        await ui_wa_select_placement(query, context, placement)
        return True

    if data.startswith("ui_wa_loc_"):
        location = data[len("ui_wa_loc_"):]
        await ui_wa_select_location(query, context, location)
        return True

    if data.startswith("ui_wa_apply_menu_"):
        try:
            wa_id = int(data[len("ui_wa_apply_menu_"):])
            await ui_wa_apply_menu_button(query, context, wa_id)
        except ValueError:
            pass
        return True

    if data == "ui_wa_remove_menu_btn":
        await ui_wa_remove_menu_button(query, context)
        return True

    if data == "ui_wa_add_menu_btn":
        await ui_wa_add_menu_btn(query, context)
        return True

    if data.startswith("ui_wa_edit_label_"):
        try:
            wa_id = int(data[len("ui_wa_edit_label_"):])
            await ui_wa_edit_label_start(query, context, wa_id)
        except ValueError:
            pass
        return True

    if data.startswith("ui_wa_edit_url_"):
        try:
            wa_id = int(data[len("ui_wa_edit_url_"):])
            await ui_wa_edit_url_start(query, context, wa_id)
        except ValueError:
            pass
        return True

    if data.startswith("ui_wa_change_placement_"):
        await query.answer("لتغيير الموضع: احذف هذا التطبيق وأضف جديداً بالموضع المطلوب", show_alert=True)
        return True

    if data == "ui_activity":
        await ui_activity_main(query, context)
        return True

    if data.startswith("ui_act_"):
        activity = data[len("ui_act_"):]
        await ui_activity_set(query, context, activity)
        return True

    if data == "ui_langs":
        await ui_langs_main(query, context)
        return True

    if data.startswith("ui_avail_langs_"):
        try:
            page = int(data[len("ui_avail_langs_"):])
        except ValueError:
            page = 0
        await ui_avail_langs(query, context, page)
        return True

    if data.startswith("ui_avail_toggle_"):
        rest = data[len("ui_avail_toggle_"):]          # e.g. "fr_0"
        parts = rest.rsplit("_", 1)
        code = parts[0]
        page = int(parts[1]) if len(parts) > 1 else 0
        await ui_avail_toggle(query, context, code, page)
        return True

    if data.startswith("ui_lang_edit_") and not data.startswith("ui_lang_tr_"):
        lang = data[len("ui_lang_edit_"):]
        await ui_lang_edit(query, context, lang)
        return True

    if data.startswith("ui_lang_tr_"):
        parts = data[len("ui_lang_tr_"):].rsplit("_", 1)
        if len(parts) == 2:
            msg_type, lang = parts
            await ui_lang_translate(query, context, msg_type, lang)
        return True

    if data == "ui_format":
        await ui_format_main(query, context)
        return True

    if data.startswith("ui_fmt_"):
        fmt = data[len("ui_fmt_"):]
        await ui_format_set(query, context, fmt)
        return True

    if data == "ui_platforms":
        await ui_platforms_main(query, context)
        return True

    if data.startswith("ui_plat_enable_"):
        platform = data[len("ui_plat_enable_"):]
        await ui_platform_toggle(query, context, platform, True)
        return True

    if data.startswith("ui_plat_disable_"):
        platform = data[len("ui_plat_disable_"):]
        await ui_platform_toggle(query, context, platform, False)
        return True

    if data.startswith("ui_plat_editmsg_"):
        platform = data[len("ui_plat_editmsg_"):]
        await ui_platform_editmsg(query, context, platform)
        return True

    if data.startswith("ui_plat_stats_"):
        platform = data[len("ui_plat_stats_"):]
        await ui_platform_stats(query, context, platform)
        return True

    if data.startswith("ui_plat_") and not any(data.startswith(p) for p in [
        "ui_plat_enable_", "ui_plat_disable_", "ui_plat_editmsg_",
        "ui_plat_stats_", "ui_plat_responses", "ui_plat_edit_",
        "ui_plat_preview_"
    ]):
        platform = data[len("ui_plat_"):]
        from bot.utils.platforms import PLATFORMS
        if platform in PLATFORMS:
            await ui_platform_detail(query, context, platform)
            return True

    if data == "ui_plat_responses":
        await ui_plat_responses_main(query, context)
        return True

    if data == "ui_plat_edit_unsupported":
        await ui_plat_edit_unsupported(query, context)
        return True

    if data == "ui_plat_edit_disabled_generic":
        await ui_plat_edit_disabled_generic(query, context)
        return True

    if data == "ui_plat_preview_responses":
        unsup = get_setting("unsupported_platform_msg", "⚠️ هذه المنصة غير مدعومة حالياً.")
        disabled = get_setting("disabled_platform_generic_msg", "عذراً، هذه المنصة غير مفعلة حالياً.")
        await query.answer()
        await query.message.reply_text(
            f"👁 **معاينة رسائل المنصات**\n\n"
            f"⚠️ غير مدعومة:\n`{unsup}`\n\n"
            f"🚫 معطلة (عامة):\n`{disabled}`",
            parse_mode="Markdown"
        )
        return True

    if data == "ui_caption":
        await ui_caption_main(query, context)
        return True

    if data.startswith("ui_cap_"):
        cap_type = data[len("ui_cap_"):]
        await ui_caption_edit(query, context, cap_type)
        return True

    if data == "ui_preview":
        await ui_preview_main(query, context)
        return True

    if data.startswith("ui_prev_"):
        item = data[len("ui_prev_"):]
        await ui_preview_item(query, context, item)
        return True

    if data == "ui_reset_confirm":
        await ui_reset_confirm(query, context)
        return True

    if data == "ui_reset_execute":
        await ui_reset_execute(query, context)
        return True

    if data.startswith("ui_plat_preview_"):
        platform = data[len("ui_plat_preview_"):]
        from bot.utils.platforms import PLATFORMS
        if platform in PLATFORMS:
            info = PLATFORMS[platform]
            disabled_msg = get_setting(
                f"{platform}_disabled_msg",
                f"عذراً، {info['name']} غير مفعل حالياً."
            )
            await query.answer()
            await query.message.reply_text(
                f"👁 **معاينة رسالة تعطيل {info['emoji']} {info['name']}**\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{disabled_msg}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"_هذا ما يراه المستخدم عند إرسال رابط هذه المنصة وهي معطّلة_",
                parse_mode="Markdown"
            )
        return True

    if data == "ui_cap_preview":
        video_cap = get_setting("video_caption", "📥 تم التحميل\n🤖 @{bot_name}")
        photo_cap = get_setting("photo_caption", "🖼 تم التحميل\n🤖 @{bot_name}")
        bot_name = get_setting("bot_name", "Bot")
        video_cap = video_cap.replace("{bot_name}", bot_name)
        photo_cap = photo_cap.replace("{bot_name}", bot_name)
        await query.answer()
        await query.message.reply_text(
            f"👁 **معاينة Caption**\n\n"
            f"📹 **Caption الفيديو:**\n`{video_cap}`\n\n"
            f"🖼 **Caption الصور:**\n`{photo_cap}`",
            parse_mode="Markdown"
        )
        return True

    if data.startswith("btn_noop"):
        await query.answer()
        return True

    return False

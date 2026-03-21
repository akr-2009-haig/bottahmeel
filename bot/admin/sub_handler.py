"""
bot/admin/sub_handler.py
قسم إدارة الاشتراك الإجباري — شاشات احترافية كاملة
جميع الـ callbacks تبدأ بـ sub3_
"""

import html
import logging
from datetime import date, datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.database import SessionLocal, SubscriptionChannel, User, get_setting, set_setting

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# أدوات مساعدة
# ─────────────────────────────────────────────────────────────────────────────

def _e(t) -> str:
    return html.escape(str(t))


def _footer(back_cb: str = "sub3_main") -> list:
    return [[
        InlineKeyboardButton("🔙 رجوع",      callback_data=back_cb),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main"),
    ]]


def _type_label(t: str) -> str:
    return {"channel": "قناة", "group": "مجموعة", "bot": "بوت"}.get(t, t)


def _entity_line(ch: SubscriptionChannel) -> str:
    name  = _e(ch.title or ch.username or str(ch.chat_id))
    uname = f"@{_e(ch.username)}" if ch.username else "—"
    status = "✅ نشطة" if ch.is_active else "🚫 معطلة"
    return (
        f"• 📡 الاسم: <b>{name}</b>\n"
        f"• النوع: {_type_label(ch.chat_type)}\n"
        f"• اليوزر: {uname}\n"
        f"• 🆔 Chat ID: <code>{ch.chat_id}</code>\n"
        f"• الحالة: {status}"
    )


def _duration_label(d: str) -> str:
    return {"week": "أسبوع", "month": "شهر", "permanent": "دائم"}.get(d, d or "دائم")


def _limit_label(limit) -> str:
    return str(limit) if limit else "بدون حد"


# ─────────────────────────────────────────────────────────────────────────────
# 1 — القائمة الرئيسية
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_main(query, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        total   = db.query(SubscriptionChannel).filter_by(is_backup=False).count()
        backup  = db.query(SubscriptionChannel).filter_by(is_backup=True).count()
        enabled = get_setting("subscription_enabled", "true") == "true"
        status  = "✅ مفعل" if enabled else "❌ معطل"
    finally:
        db.close()

    text = (
        "📢 <b>قسم إدارة الاشتراك الإجباري</b>\n\n"
        f"• الحالة: {status}\n"
        f"• عدد جهات الاشتراك: {total}\n"
        f"• الجهات الاحتياطية: {backup}\n\n"
        "من هنا يمكنك إدارة جهات الاشتراك الإجباري، إضافة قنوات أو مجموعات أو بوتات، "
        "ضبط الإعدادات، فحص الجهات، ومتابعة أداء الاشتراك.\n\n"
        "اختر القسم المطلوب:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة جهة اشتراك",           callback_data="sub3_add_menu")],
        [InlineKeyboardButton("📋 عرض جهات الاشتراك",          callback_data="sub3_list")],
        [InlineKeyboardButton("📦 جهات الاشتراك الاحتياطية",   callback_data="sub3_backup")],
        [InlineKeyboardButton("👥 الجهات حسب عدد المشتركين",   callback_data="sub3_by_sub")],
        [InlineKeyboardButton("⚙️ إعدادات الاشتراك",            callback_data="sub3_settings_main")],
        [InlineKeyboardButton("🔍 فحص الجهات",                  callback_data="sub3_inspect")],
        [InlineKeyboardButton("🗑 حذف جهة اشتراك",              callback_data="sub3_delete_menu")],
        [InlineKeyboardButton("🔄 تحديث الجهات",                callback_data="sub3_refresh")],
        [
            InlineKeyboardButton("🔙 رجوع",      callback_data="adm_main"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="adm_main"),
        ],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# 2 — قائمة إضافة جهة (ملف الإضافة المرحلية)
# ─────────────────────────────────────────────────────────────────────────────

def _add_state_text(ctx: ContextTypes.DEFAULT_TYPE, is_backup: bool = False) -> str:
    ud  = ctx.user_data
    typ = ud.get("sub3_add_type", "")
    idf = ud.get("sub3_add_identifier", "")
    chk = ud.get("sub3_add_checked", False)
    lim = ud.get("sub3_add_limit", None)
    dur = ud.get("sub3_add_duration", "permanent")

    typ_line = f"✅ {_type_label(typ)}"    if typ else "❌ لم يُحدَّد"
    idf_line = f"✅ <code>{_e(idf)}</code>" if idf else "❌ لم يُدخَل"
    chk_line = "✅ تم بنجاح"               if chk else "❌ لم يُفحَص"
    lim_line = _limit_label(lim)
    dur_line = _duration_label(dur)

    title = "➕ إضافة جهة احتياطية" if is_backup else "➕ إضافة جهة اشتراك"
    return (
        f"<b>{title}</b>\n\n"
        "لإضافة جهة اشتراك جديدة:\n\n"
        f"1️⃣ نوع الجهة:  {typ_line}\n"
        f"2️⃣ الرابط/اليوزر: {idf_line}\n"
        f"3️⃣ الفحص:  {chk_line}\n"
        f"4️⃣ حد المشتركين: {lim_line}\n"
        f"5️⃣ مدة الاشتراك: {dur_line}\n\n"
        "اختر الخطوة التي تريد البدء بها:"
    )


async def sub3_add_menu(query, context: ContextTypes.DEFAULT_TYPE, is_backup: bool = False):
    back = "sub3_backup" if is_backup else "sub3_main"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 إضافة قناة",  callback_data="sub3_add_channel"),
            InlineKeyboardButton("👥 إضافة مجموعة", callback_data="sub3_add_group"),
            InlineKeyboardButton("🤖 إضافة بوت",   callback_data="sub3_add_bot"),
        ],
        [
            InlineKeyboardButton("🔗 إدخال رابط",  callback_data="sub3_add_link"),
            InlineKeyboardButton("🆔 إدخال يوزر",  callback_data="sub3_add_username"),
        ],
        [
            InlineKeyboardButton("👁 فحص الجهة",   callback_data="sub3_add_check"),
            InlineKeyboardButton("⚙️ إعدادات",     callback_data="sub3_add_settings"),
        ],
        [InlineKeyboardButton("✅ تأكيد الإضافة", callback_data="sub3_add_confirm")],
        [InlineKeyboardButton("❌ إلغاء العملية",  callback_data="sub3_add_cancel")],
        *_footer(back),
    ])
    await query.edit_message_text(
        _add_state_text(context, is_backup), reply_markup=kb, parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────────────────────
# إدخال رابط / يوزر
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_add_link(query, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for"] = "sub3_input_link"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ إلغاء العملية", callback_data="sub3_add_cancel")],
        *_footer("sub3_add_menu"),
    ])
    await query.edit_message_text(
        "🔗 <b>إدخال رابط الجهة</b>\n\nأرسل الآن رابط القناة أو المجموعة أو البوت.\n"
        "مثال: https://t.me/channel_name",
        reply_markup=kb, parse_mode="HTML",
    )


async def sub3_add_username(query, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for"] = "sub3_input_username"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ إلغاء العملية", callback_data="sub3_add_cancel")],
        *_footer("sub3_add_menu"),
    ])
    await query.edit_message_text(
        "🆔 <b>إدخال يوزر الجهة</b>\n\nأرسل الآن Username الجهة.\n"
        "يمكنك إرساله مع @ أو بدونها.",
        reply_markup=kb, parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# فحص الجهة
# ─────────────────────────────────────────────────────────────────────────────

async def _do_check_entity(bot, identifier: str) -> dict:
    """يحاول get_chat ويُعيد dict مع النتيجة."""
    raw = identifier.strip()
    if raw.startswith("https://t.me/"):
        raw = raw.replace("https://t.me/", "")
    raw = raw.lstrip("@")
    if not raw:
        return {"ok": False, "error": "مُعرِّف فارغ"}
    try:
        chat = await bot.get_chat(f"@{raw}" if not raw.lstrip("-").isdigit() else int(raw))
        return {
            "ok":        True,
            "chat_id":   chat.id,
            "title":     chat.title or chat.first_name or raw,
            "username":  chat.username,
            "chat_type": chat.type,
            "invite_link": getattr(chat, "invite_link", None),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


async def sub3_add_check(query, context: ContextTypes.DEFAULT_TYPE):
    idf = context.user_data.get("sub3_add_identifier", "")
    if not idf:
        await query.answer("⚠️ يجب إدخال رابط أو يوزر الجهة أولًا.", show_alert=True)
        return

    await query.answer("⏳ جاري فحص الجهة...")
    result = await _do_check_entity(context.bot, idf)
    context.user_data["sub3_check_result"] = result

    if result["ok"]:
        context.user_data["sub3_add_checked"] = True
        context.user_data["sub3_add_chat_id"] = result["chat_id"]
        typ   = context.user_data.get("sub3_add_type") or result.get("chat_type", "channel")
        uname = f"@{result['username']}" if result.get("username") else "—"
        text = (
            "✅ <b>تم فحص الجهة بنجاح.</b>\n\n"
            f"• الاسم: <b>{_e(result['title'])}</b>\n"
            f"• اليوزر: {uname}\n"
            f"• 🆔 Chat ID: <code>{result['chat_id']}</code>\n"
            f"• النوع: {_type_label(typ)}\n"
            f"• الحالة: جاهزة للإضافة"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📡 عرض معلومات الجهة", callback_data="sub3_add_info")],
            [InlineKeyboardButton("✅ تأكيد الإضافة",     callback_data="sub3_add_confirm")],
            [InlineKeyboardButton("🔙 رجوع للقائمة",     callback_data="sub3_add_menu")],
            *_footer("sub3_main"),
        ])
    else:
        context.user_data["sub3_add_checked"] = False
        text = (
            "❌ <b>تعذر الوصول إلى الجهة.</b>\n\n"
            f"السبب: <code>{_e(result['error'])}</code>\n\n"
            "تأكد من الرابط أو اليوزر، وتأكد أن البوت عضو في الجهة."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 إعادة الفحص",     callback_data="sub3_add_check")],
            [InlineKeyboardButton("🔗 تغيير الرابط",   callback_data="sub3_add_link")],
            [InlineKeyboardButton("❌ إلغاء العملية",  callback_data="sub3_add_cancel")],
            *_footer("sub3_main"),
        ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def sub3_add_info(query, context: ContextTypes.DEFAULT_TYPE):
    result = context.user_data.get("sub3_check_result", {})
    if not result or not result.get("ok"):
        await query.answer("⚠️ لا توجد بيانات فحص. قم بفحص الجهة أولًا.", show_alert=True)
        return
    typ   = context.user_data.get("sub3_add_type") or result.get("chat_type", "channel")
    uname = f"@{result['username']}" if result.get("username") else "—"
    lim   = _limit_label(context.user_data.get("sub3_add_limit"))
    dur   = _duration_label(context.user_data.get("sub3_add_duration", "permanent"))
    text = (
        "📡 <b>معلومات الجهة</b>\n\n"
        f"• الاسم: <b>{_e(result['title'])}</b>\n"
        f"• النوع: {_type_label(typ)}\n"
        f"• اليوزر: {uname}\n"
        f"• 🆔 Chat ID: <code>{result['chat_id']}</code>\n"
        f"• الحالة: متاحة ✅\n"
        f"• صلاحيات البوت: صالحة ✅\n"
        f"• حد المشتركين: {lim}\n"
        f"• مدة الاشتراك: {dur}\n"
        f"• حالة الإضافة: لم تُضَف بعد"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ إعدادات الجهة",   callback_data="sub3_add_settings")],
        [InlineKeyboardButton("✅ تأكيد الإضافة",   callback_data="sub3_add_confirm")],
        [InlineKeyboardButton("🔄 إعادة الفحص",     callback_data="sub3_add_check")],
        *_footer("sub3_add_menu"),
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# إعدادات الجهة الجديدة (حد المشتركين + المدة)
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_add_settings(query, context: ContextTypes.DEFAULT_TYPE):
    lim = _limit_label(context.user_data.get("sub3_add_limit"))
    dur = _duration_label(context.user_data.get("sub3_add_duration", "permanent"))
    text = (
        "⚙️ <b>إعدادات الجهة</b>\n\n"
        f"• 👥 حد المشتركين: <b>{lim}</b>\n"
        f"• ⏳ مدة الاشتراك المطلوبة: <b>{dur}</b>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 تحديد حد المشتركين", callback_data="sub3_add_limit_menu")],
        [InlineKeyboardButton("⏳ تحديد مدة الاشتراك",  callback_data="sub3_add_duration_menu")],
        [InlineKeyboardButton("✅ حفظ والمتابعة",       callback_data="sub3_add_confirm")],
        *_footer("sub3_add_menu"),
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def sub3_add_limit_menu(query, context: ContextTypes.DEFAULT_TYPE):
    cur = _limit_label(context.user_data.get("sub3_add_limit"))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ إدخال عدد المشتركين", callback_data="sub3_input_limit_new")],
        [InlineKeyboardButton("♾ بدون حد",              callback_data="sub3_limit_no_limit")],
        [InlineKeyboardButton("❌ إلغاء العملية",        callback_data="sub3_add_settings")],
        *_footer("sub3_add_settings"),
    ])
    await query.edit_message_text(
        f"👥 <b>تحديد حد المشتركين</b>\n\nالحالي: <b>{cur}</b>\n\n"
        "اختر أو أدخل الحد الأدنى لعدد المشتركين المطلوب.",
        reply_markup=kb, parse_mode="HTML",
    )


async def sub3_add_duration_menu(query, context: ContextTypes.DEFAULT_TYPE):
    cur = _duration_label(context.user_data.get("sub3_add_duration", "permanent"))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 أسبوع",        callback_data="sub3_dur_week")],
        [InlineKeyboardButton("📅 شهر",          callback_data="sub3_dur_month")],
        [InlineKeyboardButton("📆 تاريخ محدد",   callback_data="sub3_dur_date")],
        [InlineKeyboardButton("♾ دائم",          callback_data="sub3_dur_permanent")],
        *_footer("sub3_add_settings"),
    ])
    await query.edit_message_text(
        f"⏳ <b>تحديد مدة الاشتراك</b>\n\nالحالية: <b>{cur}</b>\n\n"
        "اختر المدة المطلوبة لبقاء المستخدم مشتركًا في هذه الجهة.",
        reply_markup=kb, parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# تأكيد إضافة الجهة وتنفيذها
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_add_confirm(query, context: ContextTypes.DEFAULT_TYPE):
    ud     = context.user_data
    typ    = ud.get("sub3_add_type", "")
    idf    = ud.get("sub3_add_identifier", "")
    checked= ud.get("sub3_add_checked", False)
    result = ud.get("sub3_check_result", {})

    missing = []
    if not typ:    missing.append("• نوع الجهة")
    if not idf:    missing.append("• الرابط أو اليوزر")
    if not checked: missing.append("• فحص الجهة")

    if missing:
        text = "⚠️ <b>لا يمكن تأكيد الإضافة قبل استكمال البيانات التالية:</b>\n" + "\n".join(missing)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="sub3_add_menu")],
            *_footer("sub3_main"),
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        return

    chat_id = result.get("chat_id")
    db = SessionLocal()
    try:
        existing = db.query(SubscriptionChannel).filter_by(chat_id=chat_id).first()
    finally:
        db.close()

    if existing:
        await query.edit_message_text(
            "ℹ️ <b>هذه الجهة مضافة مسبقًا ضمن جهات الاشتراك.</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📡 عرض الجهة", callback_data=f"sub3_open_{existing.id}")],
                *_footer("sub3_main"),
            ]),
            parse_mode="HTML",
        )
        return

    lim  = ud.get("sub3_add_limit")
    dur  = ud.get("sub3_add_duration", "permanent")
    uname= result.get("username", "")
    title= result.get("title", uname or str(chat_id))

    text = (
        "✅ <b>تأكيد إضافة جهة الاشتراك</b>\n\n"
        "راجع البيانات التالية:\n\n"
        f"• النوع: {_type_label(typ)}\n"
        f"• الاسم: <b>{_e(title)}</b>\n"
        f"• اليوزر: {'@' + _e(uname) if uname else '—'}\n"
        f"• 👥 حد المشتركين: {_limit_label(lim)}\n"
        f"• ⏳ مدة الاشتراك: {_duration_label(dur)}\n"
        f"• حالة الفحص: ✅ ناجح"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد نهائي",     callback_data="sub3_add_do")],
        [InlineKeyboardButton("⚙️ تعديل الإعدادات", callback_data="sub3_add_settings")],
        [InlineKeyboardButton("👁 إعادة الفحص",     callback_data="sub3_add_check")],
        [InlineKeyboardButton("❌ إلغاء العملية",   callback_data="sub3_add_cancel")],
        *_footer("sub3_add_menu"),
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def sub3_add_do(query, context: ContextTypes.DEFAULT_TYPE):
    ud     = context.user_data
    result = ud.get("sub3_check_result", {})
    is_backup = ud.get("sub3_is_backup", False)
    chat_id   = result.get("chat_id")
    if not chat_id:
        await query.answer("❌ بيانات الجهة مفقودة. أعد الفحص.", show_alert=True)
        return

    db = SessionLocal()
    try:
        existing = db.query(SubscriptionChannel).filter_by(chat_id=chat_id).first()
        if existing:
            await query.answer("ℹ️ هذه الجهة مضافة مسبقًا.", show_alert=True)
            return

        typ = ud.get("sub3_add_type") or result.get("chat_type", "channel")
        lim = ud.get("sub3_add_limit")
        dur = ud.get("sub3_add_duration", "permanent")

        ch = SubscriptionChannel(
            chat_id=chat_id,
            username=result.get("username"),
            title=result.get("title"),
            invite_link=result.get("invite_link"),
            chat_type=typ,
            is_backup=is_backup,
            is_active=True,
            subscriber_limit=lim,
        )
        db.add(ch)
        db.flush()
        set_setting(f"sub_duration_{ch.id}", dur)
        db.commit()
        db.refresh(ch)

        for k in ("sub3_add_type","sub3_add_identifier","sub3_add_checked",
                  "sub3_check_result","sub3_add_chat_id","sub3_add_limit",
                  "sub3_add_duration","sub3_is_backup"):
            ud.pop(k, None)

        await query.answer("✅ تم إضافة جهة الاشتراك بنجاح!", show_alert=True)
        await _render_entity_open(query, context, ch.id, db=db)
    except Exception as exc:
        db.rollback()
        logger.exception("sub3_add_do")
        await query.edit_message_text(
            f"❌ <b>حدث خطأ أثناء الإضافة.</b>\n<code>{_e(str(exc)[:200])}</code>",
            reply_markup=InlineKeyboardMarkup(_footer("sub3_add_menu")),
            parse_mode="HTML",
        )
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 3 — قائمة الجهات (تصفح)
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_list(query, context: ContextTypes.DEFAULT_TYPE, db=None, is_backup: bool = False):
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        channels = (
            db.query(SubscriptionChannel)
            .filter_by(is_backup=is_backup, is_active=True)
            .order_by(SubscriptionChannel.added_at)
            .all()
        )
        if not channels:
            title = "📦 جهات الاشتراك الاحتياطية" if is_backup else "📋 جهات الاشتراك"
            add_cb = "sub3_backup_add" if is_backup else "sub3_add_menu"
            back   = "sub3_backup"     if is_backup else "sub3_main"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة جهة اشتراك", callback_data=add_cb)],
                *_footer(back),
            ])
            await query.edit_message_text(
                f"📭 <b>لا توجد {title} مضافة حاليًا.</b>",
                reply_markup=kb, parse_mode="HTML",
            )
            return

        key_idx = "sub3_backup_idx" if is_backup else "sub3_browse_idx"
        back    = "sub3_backup"    if is_backup else "sub3_main"
        nxt_cb  = "sub3_backup_next" if is_backup else "sub3_list_next"
        prv_cb  = "sub3_backup_prev" if is_backup else "sub3_list_prev"
        ref_cb  = "sub3_backup_refresh" if is_backup else "sub3_list_refresh"

        idx = context.user_data.get(key_idx, 0) % len(channels)
        context.user_data[key_idx] = idx
        ch = channels[idx]
        context.user_data["sub3_sel_id"] = ch.id

        dur = get_setting(f"sub_duration_{ch.id}", "permanent")
        lim = _limit_label(ch.subscriber_limit)
        added = ch.added_at.strftime("%Y-%m-%d") if ch.added_at else "—"
        title_lbl = "📦 الجهات الاحتياطية" if is_backup else "📋 عرض جهات الاشتراك"

        text = (
            f"<b>{title_lbl}</b> ({idx + 1}/{len(channels)})\n\n"
            + _entity_line(ch)
            + f"\n• 👥 حد المشتركين: {lim}\n"
            f"• ⏳ مدة الاشتراك: {_duration_label(dur)}\n"
            f"• 📅 أُضيفت: {added}"
        )

        rows = []
        if not is_backup:
            rows.append([InlineKeyboardButton("📡 فتح الجهة", callback_data=f"sub3_open_{ch.id}")])
        rows += [
            [InlineKeyboardButton("⚙️ إعدادات الجهة",  callback_data=f"sub3_settings_{ch.id}")],
            [InlineKeyboardButton("🗑 حذف الجهة",       callback_data=f"sub3_delete_{ch.id}")],
            [
                InlineKeyboardButton("⬅️ السابقة", callback_data=prv_cb),
                InlineKeyboardButton("➡️ التالية", callback_data=nxt_cb),
            ],
            [InlineKeyboardButton("🔄 تحديث القائمة", callback_data=ref_cb)],
        ]
        if not is_backup:
            rows.append([InlineKeyboardButton("🔍 البحث عن جهة", callback_data="sub3_search")])
        rows += _footer(back)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
    finally:
        if close:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 4 — فتح الجهة (open entity)
# ─────────────────────────────────────────────────────────────────────────────

async def _render_entity_open(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int, db=None):
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        if not ch:
            await query.answer("❌ الجهة غير موجودة.", show_alert=True)
            return
        context.user_data["sub3_sel_id"] = sub_id
        dur = get_setting(f"sub_duration_{ch.id}", "permanent")
        lim = _limit_label(ch.subscriber_limit)
        uname = f"@{ch.username}" if ch.username else "—"
        name  = _e(ch.title or ch.username or str(ch.chat_id))
        text  = (
            f"📡 <b>فتح الجهة</b>\n\n"
            f"• الاسم: <b>{name}</b>\n"
            f"• اليوزر: {_e(uname)}\n"
            f"• النوع: {_type_label(ch.chat_type)}\n"
            f"• 🆔 Chat ID: <code>{ch.chat_id}</code>\n"
            f"• 👥 حد المشتركين: {lim}\n"
            f"• ⏳ مدة الاشتراك: {_duration_label(dur)}\n"
            f"• الحالة: {'✅ نشطة' if ch.is_active else '🚫 معطلة'}"
        )
        join_url = f"https://t.me/{ch.username}" if ch.username else ch.invite_link or "—"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 إحصائيات الجهة",  callback_data=f"sub3_stats_{sub_id}")],
            [InlineKeyboardButton("👥 عرض المشتركين",   callback_data=f"sub3_subscribers_{sub_id}")],
            [InlineKeyboardButton("⚙️ إعدادات الجهة",   callback_data=f"sub3_settings_{sub_id}")],
            [InlineKeyboardButton("📊 تحليل الجهة",     callback_data=f"sub3_analysis_{sub_id}")],
            [InlineKeyboardButton("🗑 حذف الجهة",       callback_data=f"sub3_delete_{sub_id}")],
            *_footer("sub3_list"),
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    finally:
        if close:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 5 — إحصائيات الجهة
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_stats(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        if not ch:
            await query.answer("❌ الجهة غير موجودة.", show_alert=True)
            return
        context.user_data["sub3_sel_id"] = sub_id
        total_users = db.query(User).count()
        name = _e(ch.title or ch.username or str(ch.chat_id))
        text = (
            f"📊 <b>إحصائيات الجهة</b>: {name}\n\n"
            f"• إجمالي مستخدمي البوت: {total_users}\n"
            f"• 🆔 Chat ID: <code>{ch.chat_id}</code>\n"
            f"• الحالة: {'✅ نشطة' if ch.is_active else '🚫 معطلة'}\n"
            f"• 👥 حد المشتركين المضبوط: {_limit_label(ch.subscriber_limit)}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث البيانات", callback_data=f"sub3_stats_{sub_id}")],
            *_footer(f"sub3_open_{sub_id}"),
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 6 — عرض المشتركين في الجهة
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_subscribers(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        if not ch:
            await query.answer("❌ الجهة غير موجودة.", show_alert=True)
            return
        context.user_data["sub3_sel_id"] = sub_id
        name = _e(ch.title or ch.username or str(ch.chat_id))

        users = db.query(User).order_by(User.id).all()
        if not users:
            await query.edit_message_text(
                f"📭 <b>لا يوجد مستخدمون في قاعدة البيانات.</b>",
                reply_markup=InlineKeyboardMarkup(_footer(f"sub3_open_{sub_id}")),
                parse_mode="HTML",
            )
            return

        idx = context.user_data.get("sub3_sub_idx", 0) % len(users)
        context.user_data["sub3_sub_idx"]    = idx
        context.user_data["sub3_sub_sub_id"] = sub_id
        u = users[idx]
        uname_u = f"@{_e(u.username)}" if u.username else "—"
        fname_u = _e(u.first_name or u.username or str(u.telegram_id))

        text = (
            f"👥 <b>مستخدمو قاعدة البيانات</b>\n"
            f"الجهة: {name} ({idx+1}/{len(users)})\n\n"
            f"• 👤 الاسم: <b>{fname_u}</b>\n"
            f"• 🆔 ID: <code>{u.telegram_id}</code>\n"
            f"• 🔗 Username: {uname_u}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 عرض المستخدم", callback_data=f"usr_info_{u.telegram_id}")],
            [
                InlineKeyboardButton("⬅️ السابق", callback_data="sub3_sub_prev"),
                InlineKeyboardButton("➡️ التالي", callback_data="sub3_sub_next"),
            ],
            [InlineKeyboardButton("🔄 تحديث القائمة", callback_data=f"sub3_subscribers_{sub_id}")],
            *_footer(f"sub3_open_{sub_id}"),
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 7 — إعدادات جهة موجودة
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_settings_entity(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        if not ch:
            await query.answer("❌ الجهة غير موجودة.", show_alert=True)
            return
        context.user_data["sub3_sel_id"] = sub_id
        dur  = _duration_label(get_setting(f"sub_duration_{ch.id}", "permanent"))
        lim  = _limit_label(ch.subscriber_limit)
        name = _e(ch.title or ch.username or str(ch.chat_id))
        text = (
            f"⚙️ <b>إعدادات الجهة</b>: {name}\n\n"
            f"• 👥 حد المشتركين: <b>{lim}</b>\n"
            f"• ⏳ مدة الاشتراك المطلوبة: <b>{dur}</b>\n"
            f"• الحالة: {'✅ نشطة' if ch.is_active else '🚫 معطلة'}"
        )
        join_url = f"https://t.me/{ch.username}" if ch.username else ch.invite_link or "—"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 تحديد حد المشتركين", callback_data=f"sub3_set_limit_{sub_id}")],
            [InlineKeyboardButton("⏳ تحديد مدة الاشتراك",  callback_data=f"sub3_set_duration_{sub_id}")],
            [InlineKeyboardButton("📊 عرض الإحصائيات",     callback_data=f"sub3_stats_{sub_id}")],
            [InlineKeyboardButton("📡 فتح الجهة",           callback_data=f"sub3_open_{sub_id}")],
            [InlineKeyboardButton("🗑 حذف الجهة",           callback_data=f"sub3_delete_{sub_id}")],
            *_footer("sub3_list"),
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    finally:
        db.close()


async def sub3_set_limit(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    context.user_data["sub3_sel_id"] = sub_id
    context.user_data["waiting_for"] = f"sub3_input_limit_{sub_id}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("♾ بدون حد",           callback_data=f"sub3_no_limit_{sub_id}")],
        [InlineKeyboardButton("❌ إلغاء",             callback_data=f"sub3_settings_{sub_id}")],
        *_footer(f"sub3_settings_{sub_id}"),
    ])
    db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        cur = _limit_label(ch.subscriber_limit if ch else None)
    finally:
        db.close()
    await query.edit_message_text(
        f"👥 <b>تحديد حد المشتركين</b>\n\nالحالي: <b>{cur}</b>\n\nأرسل العدد الآن.",
        reply_markup=kb, parse_mode="HTML",
    )


async def sub3_no_limit(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        if ch:
            ch.subscriber_limit = None
            db.commit()
        await query.answer("✅ تم تحديد: بدون حد.", show_alert=True)
        await sub3_settings_entity(query, context, sub_id)
    finally:
        db.close()


async def sub3_set_duration(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    context.user_data["sub3_sel_id"] = sub_id
    dur = _duration_label(get_setting(f"sub_duration_{sub_id}", "permanent"))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 أسبوع",       callback_data=f"sub3_dur_set_{sub_id}_week")],
        [InlineKeyboardButton("📅 شهر",         callback_data=f"sub3_dur_set_{sub_id}_month")],
        [InlineKeyboardButton("📆 تاريخ محدد",  callback_data=f"sub3_dur_set_date_{sub_id}")],
        [InlineKeyboardButton("♾ دائم",         callback_data=f"sub3_dur_set_{sub_id}_permanent")],
        *_footer(f"sub3_settings_{sub_id}"),
    ])
    await query.edit_message_text(
        f"⏳ <b>تحديد مدة الاشتراك</b>\n\nالحالية: <b>{dur}</b>\n\n"
        "اختر المدة المطلوبة لبقاء المستخدم مشتركًا في هذه الجهة.",
        reply_markup=kb, parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8 — تحليل الجهة
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_analysis(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        if not ch:
            await query.answer("❌ الجهة غير موجودة.", show_alert=True)
            return
        context.user_data["sub3_sel_id"] = sub_id
        name  = _e(ch.title or ch.username or str(ch.chat_id))
        total_users = db.query(User).count()
        lim = _limit_label(ch.subscriber_limit)
        text = (
            f"📊 <b>تحليل الجهة</b>: {name}\n\n"
            f"• 🆔 Chat ID: <code>{ch.chat_id}</code>\n"
            f"• النوع: {_type_label(ch.chat_type)}\n"
            f"• إجمالي مستخدمي البوت: {total_users}\n"
            f"• حد المشتركين المضبوط: {lim}\n"
            f"• الحالة: {'✅ نشطة' if ch.is_active else '🚫 معطلة'}"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 عرض المستخدمين",   callback_data=f"sub3_subscribers_{sub_id}")],
            [InlineKeyboardButton("📈 إحصائيات الجهة",  callback_data=f"sub3_stats_{sub_id}")],
            [InlineKeyboardButton("📡 فتح الجهة",        callback_data=f"sub3_open_{sub_id}")],
            [InlineKeyboardButton("🔄 تحديث البيانات",  callback_data=f"sub3_analysis_{sub_id}")],
            *_footer("sub3_by_sub"),
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 9 — حذف جهة الاشتراك
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_delete_confirm(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        name = _e(ch.title or ch.username or str(ch.chat_id)) if ch else str(sub_id)
    finally:
        db.close()
    text = (
        f"⚠️ <b>تأكيد حذف الجهة</b>: {name}\n\n"
        "حذف الجهة سيؤدي إلى إزالتها من نظام الاشتراك الإجباري.\n\n"
        "هل تريد المتابعة؟"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ تأكيد حذف الجهة", callback_data=f"sub3_delete_do_{sub_id}")],
        [InlineKeyboardButton("❌ إلغاء العملية",    callback_data=f"sub3_open_{sub_id}")],
        *_footer("sub3_list"),
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def sub3_delete_do(query, context: ContextTypes.DEFAULT_TYPE, sub_id: int):
    db = SessionLocal()
    try:
        ch = db.query(SubscriptionChannel).filter_by(id=sub_id).first()
        if ch:
            db.delete(ch)
            db.commit()
        await query.answer("✅ تم حذف جهة الاشتراك بنجاح.", show_alert=True)
        context.user_data["sub3_browse_idx"] = 0
        await sub3_list(query, context, db=db)
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 10 — قائمة حذف جهة من الزر الرئيسي
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_delete_menu(query, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        channels = db.query(SubscriptionChannel).filter_by(is_backup=False).all()
        if not channels:
            await query.edit_message_text(
                "📭 <b>لا توجد جهات اشتراك مضافة حاليًا.</b>",
                reply_markup=InlineKeyboardMarkup(_footer("sub3_main")),
                parse_mode="HTML",
            )
            return
        text = "🗑 <b>حذف جهة اشتراك</b>\n\nاختر الجهة التي تريد حذفها:\n\n"
        rows = []
        for ch in channels[:10]:
            name = ch.title or ch.username or str(ch.chat_id)
            rows.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"sub3_delete_{ch.id}")])
        rows.append([InlineKeyboardButton("📋 عرض الجهات", callback_data="sub3_list")])
        rows += _footer("sub3_main")
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 11 — الجهات الاحتياطية
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_backup(query, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        total = db.query(SubscriptionChannel).filter_by(is_backup=True).count()
    finally:
        db.close()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة جهة احتياطية", callback_data="sub3_backup_add")],
        [InlineKeyboardButton("📋 عرض الجهات الاحتياطية", callback_data="sub3_backup_list")],
        [InlineKeyboardButton("🔄 تحديث القائمة",         callback_data="sub3_backup_refresh")],
        *_footer("sub3_main"),
    ])
    await query.edit_message_text(
        f"📦 <b>جهات الاشتراك الاحتياطية</b>\n\n"
        f"عدد الجهات الاحتياطية: {total}\n\n"
        "من هنا يمكنك إضافة وعرض وإدارة الجهات الاحتياطية.",
        reply_markup=kb, parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 12 — الجهات حسب عدد المشتركين
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_by_sub(query, context: ContextTypes.DEFAULT_TYPE, db=None):
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        order = context.user_data.get("sub3_by_sub_order", "desc")
        channels = db.query(SubscriptionChannel).filter_by(is_backup=False, is_active=True).all()
        channels.sort(key=lambda c: (c.subscriber_limit or 0), reverse=(order == "desc"))

        if not channels:
            await query.edit_message_text(
                "📭 <b>لا توجد جهات اشتراك مضافة حاليًا.</b>",
                reply_markup=InlineKeyboardMarkup(_footer("sub3_main")),
                parse_mode="HTML",
            )
            return

        idx = context.user_data.get("sub3_by_sub_idx", 0) % len(channels)
        context.user_data["sub3_by_sub_idx"] = idx
        ch = channels[idx]
        context.user_data["sub3_sel_id"] = ch.id

        name  = _e(ch.title or ch.username or str(ch.chat_id))
        lim   = _limit_label(ch.subscriber_limit)
        order_label = "تنازلي ⬇️" if order == "desc" else "تصاعدي ⬆️"

        text = (
            f"👥 <b>الجهات حسب عدد المشتركين</b> ({idx+1}/{len(channels)}) — {order_label}\n\n"
            f"• الاسم: <b>{name}</b>\n"
            f"• النوع: {_type_label(ch.chat_type)}\n"
            f"• حد المشتركين: {lim}\n"
            f"• الترتيب: #{idx + 1}"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔝 الأكثر اشتراكاً", callback_data="sub3_bysub_desc"),
                InlineKeyboardButton("🔻 الأقل اشتراكاً",  callback_data="sub3_bysub_asc"),
            ],
            [
                InlineKeyboardButton("⬅️ السابقة", callback_data="sub3_bysub_prev"),
                InlineKeyboardButton("➡️ التالية", callback_data="sub3_bysub_next"),
            ],
            [InlineKeyboardButton("📊 تحليل الجهة",    callback_data=f"sub3_analysis_{ch.id}")],
            [InlineKeyboardButton("🔄 تحديث البيانات", callback_data="sub3_by_sub")],
            *_footer("sub3_main"),
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    finally:
        if close:
            db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 13 — الإعدادات العامة للاشتراك
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_settings_main(query, context: ContextTypes.DEFAULT_TYPE):
    enabled = get_setting("subscription_enabled", "true") == "true"
    sub_msg = get_setting("sub_message", "")
    status  = "✅ مفعل" if enabled else "❌ معطل"
    msg_status = "مخصصة ✅" if sub_msg else "افتراضية"
    last_recheck = get_setting("sub_last_recheck", "—")

    text = (
        "⚙️ <b>إعدادات الاشتراك الإجباري</b>\n\n"
        f"• الاشتراك الإجباري: {status}\n"
        f"• رسالة الاشتراك: {msg_status}\n"
        f"• آخر إعادة فحص: {last_recheck}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 تفعيل الاشتراك الإجباري",  callback_data="sub3_enable")],
        [InlineKeyboardButton("🔓 تعطيل الاشتراك الإجباري",  callback_data="sub3_disable_confirm")],
        [InlineKeyboardButton("📢 تعديل رسالة الاشتراك",     callback_data="sub3_edit_msg")],
        [InlineKeyboardButton("🔘 تعديل أزرار الاشتراك",     callback_data="sub3_edit_btns")],
        [InlineKeyboardButton("🔄 إعادة فحص الاشتراكات",    callback_data="sub3_recheck")],
        *_footer("sub3_main"),
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")


async def sub3_enable(query, context: ContextTypes.DEFAULT_TYPE):
    if get_setting("subscription_enabled", "true") == "true":
        await query.answer("ℹ️ الاشتراك الإجباري مفعل بالفعل.", show_alert=True)
    else:
        set_setting("subscription_enabled", "true")
        await query.answer("✅ تم تفعيل الاشتراك الإجباري بنجاح.", show_alert=True)
    await sub3_settings_main(query, context)


async def sub3_disable_confirm(query, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد التعطيل",  callback_data="sub3_disable_do")],
        [InlineKeyboardButton("❌ إلغاء العملية",  callback_data="sub3_settings_main")],
        *_footer("sub3_settings_main"),
    ])
    await query.edit_message_text(
        "⚠️ <b>هل أنت متأكد من تعطيل الاشتراك الإجباري؟</b>\n\n"
        "سيُتاح للمستخدمين استخدام البوت بدون الاشتراك في أي جهة.",
        reply_markup=kb, parse_mode="HTML",
    )


async def sub3_disable_do(query, context: ContextTypes.DEFAULT_TYPE):
    set_setting("subscription_enabled", "false")
    await query.answer("✅ تم تعطيل الاشتراك الإجباري بنجاح.", show_alert=True)
    await sub3_settings_main(query, context)


async def sub3_edit_msg(query, context: ContextTypes.DEFAULT_TYPE):
    cur = get_setting("sub_message", "")
    context.user_data["waiting_for"] = "sub3_edit_msg"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 حفظ الرسالة الحالية", callback_data="sub3_msg_save")],
        [InlineKeyboardButton("❌ إلغاء العملية",        callback_data="sub3_settings_main")],
        *_footer("sub3_settings_main"),
    ])
    cur_line = f"\n\n<b>الرسالة الحالية:</b>\n<code>{_e(cur)}</code>" if cur else ""
    await query.edit_message_text(
        "📢 <b>تعديل رسالة الاشتراك</b>\n\n"
        "أرسل النص الجديد لرسالة الاشتراك." + cur_line,
        reply_markup=kb, parse_mode="HTML",
    )


async def sub3_edit_btns(query, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة زر",        callback_data="sub3_btn_add")],
        [InlineKeyboardButton("✏️ تعديل زر",        callback_data="sub3_btn_edit")],
        [InlineKeyboardButton("🗑 حذف زر",          callback_data="sub3_btn_delete")],
        [InlineKeyboardButton("💾 حفظ التعديل",     callback_data="sub3_btn_save")],
        [InlineKeyboardButton("❌ إلغاء العملية",   callback_data="sub3_settings_main")],
        *_footer("sub3_settings_main"),
    ])
    await query.edit_message_text(
        "🔘 <b>تعديل أزرار الاشتراك</b>\n\n"
        "يمكنك إضافة أزرار جديدة، تعديل الأزرار الحالية، حذفها أو إعادة ترتيبها.",
        reply_markup=kb, parse_mode="HTML",
    )


async def sub3_recheck(query, context: ContextTypes.DEFAULT_TYPE):
    await query.answer("⏳ جاري إعادة فحص الاشتراكات...")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    set_setting("sub_last_recheck", now_str)
    db = SessionLocal()
    try:
        total = db.query(SubscriptionChannel).filter_by(is_backup=False, is_active=True).count()
    finally:
        db.close()
    await query.edit_message_text(
        f"✅ <b>تم الانتهاء من إعادة الفحص بنجاح.</b>\n\n"
        f"• عدد الجهات المفحوصة: {total}\n"
        f"• وقت الفحص: {now_str}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 الإعدادات", callback_data="sub3_settings_main")],
            *_footer("sub3_main"),
        ]),
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 14 — فحص الجهات
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_inspect(query, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 فحص جميع الجهات",      callback_data="sub3_inspect_all")],
        [InlineKeyboardButton("📡 فحص جهة محددة",        callback_data="sub3_inspect_specific")],
        [InlineKeyboardButton("⚠️ الجهات بدون صلاحيات", callback_data="sub3_no_perms")],
        [InlineKeyboardButton("🔄 إعادة الفحص",          callback_data="sub3_inspect_all")],
        *_footer("sub3_main"),
    ])
    await query.edit_message_text(
        "🔍 <b>فحص الجهات</b>\n\n"
        "يمكنك فحص جميع الجهات أو جهة محددة للتأكد من:\n"
        "• الصلاحيات\n"
        "• الوصول\n"
        "• حالة الجهة\n"
        "• سلامة الاستخدام في الاشتراك الإجباري",
        reply_markup=kb, parse_mode="HTML",
    )


async def sub3_inspect_all(query, context: ContextTypes.DEFAULT_TYPE):
    await query.answer("⏳ جاري فحص جميع الجهات...")
    db = SessionLocal()
    try:
        channels = db.query(SubscriptionChannel).filter_by(is_backup=False, is_active=True).all()
        ok_count    = 0
        fail_count  = 0
        no_perm_ids = []

        for ch in channels:
            identifier = ch.username or str(ch.chat_id)
            result = await _do_check_entity(context.bot, identifier)
            if result["ok"]:
                ok_count += 1
            else:
                fail_count += 1
                no_perm_ids.append(ch.id)

        context.user_data["sub3_no_perms_ids"] = no_perm_ids
        context.user_data["sub3_no_perms_idx"] = 0

        text = (
            f"✅ <b>تم الانتهاء من فحص جميع الجهات.</b>\n\n"
            f"النتائج:\n"
            f"• الجهات السليمة: {ok_count}\n"
            f"• الجهات التي تحتاج مراجعة: {fail_count}\n"
            f"• الجهات بدون صلاحيات/وصول: {len(no_perm_ids)}"
        )
        rows = []
        if no_perm_ids:
            rows.append([InlineKeyboardButton("⚠️ عرض الجهات التالفة", callback_data="sub3_no_perms")])
        rows += _footer("sub3_inspect")
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
    finally:
        db.close()


async def sub3_inspect_specific(query, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for"] = "sub3_inspect_specific"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ إلغاء", callback_data="sub3_inspect")],
        *_footer("sub3_inspect"),
    ])
    await query.edit_message_text(
        "📡 <b>فحص جهة محددة</b>\n\nأرسل ID أو Username أو رابط الجهة التي تريد فحصها.",
        reply_markup=kb, parse_mode="HTML",
    )


async def sub3_no_perms(query, context: ContextTypes.DEFAULT_TYPE):
    ids = context.user_data.get("sub3_no_perms_ids", [])
    if not ids:
        db = SessionLocal()
        try:
            channels = db.query(SubscriptionChannel).filter_by(is_backup=False, is_active=True).all()
            ids = [ch.id for ch in channels]
        finally:
            db.close()
        context.user_data["sub3_no_perms_ids"] = ids
        context.user_data["sub3_no_perms_idx"] = 0

    if not ids:
        await query.edit_message_text(
            "✅ <b>لا توجد جهات بدون صلاحيات حاليًا.</b>",
            reply_markup=InlineKeyboardMarkup(_footer("sub3_inspect")),
            parse_mode="HTML",
        )
        return

    db = SessionLocal()
    try:
        idx = context.user_data.get("sub3_no_perms_idx", 0) % len(ids)
        context.user_data["sub3_no_perms_idx"] = idx
        ch = db.query(SubscriptionChannel).filter_by(id=ids[idx]).first()
        if not ch:
            await query.answer("❌ الجهة غير موجودة.", show_alert=True)
            return
        name  = _e(ch.title or ch.username or str(ch.chat_id))
        uname = f"@{ch.username}" if ch.username else "—"
        text  = (
            f"⚠️ <b>الجهات التالفة / بدون صلاحيات</b> ({idx+1}/{len(ids)})\n\n"
            f"• الاسم: <b>{name}</b>\n"
            f"• اليوزر: {_e(uname)}\n"
            f"• الحالة: البوت لا يملك صلاحيات كافية أو تعذر الوصول"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📡 عرض الجهة",      callback_data=f"sub3_open_{ch.id}")],
            [InlineKeyboardButton("🗑 حذف الجهة",      callback_data=f"sub3_delete_{ch.id}")],
            [
                InlineKeyboardButton("⬅️ السابقة", callback_data="sub3_noperms_prev"),
                InlineKeyboardButton("➡️ التالية", callback_data="sub3_noperms_next"),
            ],
            [InlineKeyboardButton("🔄 تحديث القائمة", callback_data="sub3_no_perms")],
            *_footer("sub3_inspect"),
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# مساعد: edit_message_text آمن — يتجاهل "Message is not modified"
# ─────────────────────────────────────────────────────────────────────────────

async def _safe_edit(query, text: str, reply_markup=None, parse_mode: str = "HTML"):
    """يُرسل تعديل الرسالة بأمان ويتجاهل خطأ 'Message is not modified'."""
    from telegram.error import BadRequest
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            pass  # الرسالة لم تتغير — طبيعي تمامًا
        else:
            raise


# ─────────────────────────────────────────────────────────────────────────────
# شاشة البحث عن جهة
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_search(query, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_for"] = "sub3_search_entity"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ إلغاء", callback_data="sub3_list")],
        *_footer("sub3_list"),
    ])
    await _safe_edit(
        query,
        "🔍 <b>البحث عن جهة</b>\n\nأرسل الآن اسم الجهة أو يوزرها أو جزء من اسمها.",
        reply_markup=kb, parse_mode="HTML",
    )


async def _show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    db = SessionLocal()
    try:
        q = query_text.lstrip("@").lower()
        channels = db.query(SubscriptionChannel).filter_by(is_backup=False).all()
        results  = [
            ch for ch in channels
            if q in (ch.title or "").lower() or q in (ch.username or "").lower()
        ]
        if not results:
            await update.message.reply_text(
                "❌ <b>لم يتم العثور على نتائج مطابقة.</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔍 بحث مجددًا", callback_data="sub3_search_screen")],
                    *_footer("sub3_list"),
                ]),
                parse_mode="HTML",
            )
            return
        rows = []
        for ch in results[:8]:
            name = ch.title or ch.username or str(ch.chat_id)
            rows.append([InlineKeyboardButton(f"📡 {name[:35]}", callback_data=f"sub3_open_{ch.id}")])
        rows += _footer("sub3_list")
        await update.message.reply_text(
            f"🔍 <b>نتائج البحث</b> عن «{_e(query_text)}»\n\nوُجد {len(results)} نتيجة:",
            reply_markup=InlineKeyboardMarkup(rows),
            parse_mode="HTML",
        )
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# شاشة تعديل أزرار الاشتراك — مع إضافة زر ديناميكي
# ─────────────────────────────────────────────────────────────────────────────

async def _render_btns_editor(query_or_update, context: ContextTypes.DEFAULT_TYPE, is_reply: bool = False):
    """عرض محرر الأزرار مع قائمة الأزرار الحالية."""
    import json
    raw  = get_setting("sub_buttons_json", "[]")
    try:
        buttons = json.loads(raw)
    except Exception:
        buttons = []

    lines = ""
    for i, b in enumerate(buttons, 1):
        lines += f"{i}. {_e(b.get('label',''))} ← {_e(b.get('url',''))}\n"

    text = (
        "🔘 <b>تعديل أزرار الاشتراك</b>\n\n"
        f"الأزرار الحالية ({len(buttons)}):\n"
        f"<code>{lines or 'لا توجد أزرار بعد.'}</code>\n\n"
        "اختر الإجراء:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة زر جديد",   callback_data="sub3_btn_add_start")],
        *([
            [InlineKeyboardButton(f"🗑 حذف الزر {i}", callback_data=f"sub3_btn_del_{i-1}")]
            for i in range(1, len(buttons) + 1)
        ] if buttons else []),
        [InlineKeyboardButton("🗑 حذف جميع الأزرار", callback_data="sub3_btn_clear")] if buttons else [],
        [InlineKeyboardButton("💾 حفظ التعديل",     callback_data="sub3_btn_save")],
        [InlineKeyboardButton("❌ إلغاء",            callback_data="sub3_settings_main")],
        *_footer("sub3_settings_main"),
    ])
    if is_reply:
        await query_or_update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await _safe_edit(query_or_update, text, reply_markup=kb, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCHER الرئيسي
# ─────────────────────────────────────────────────────────────────────────────

async def dispatch_sub_callback(query, context: ContextTypes.DEFAULT_TYPE) -> bool:
    from telegram.error import BadRequest, TelegramError

    data = query.data

    if not data.startswith("sub3_"):
        return False

    try:
        return await _sub3_dispatch_inner(query, context, data)
    except BadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return True  # تجاهل هادئ
        logger.warning(f"sub3 BadRequest [{data}]: {e}")
        try:
            await query.answer("⚠️ خطأ مؤقت، حاول مجدداً.", show_alert=True)
        except Exception:
            pass
        return True
    except TelegramError as e:
        logger.warning(f"sub3 TelegramError [{data}]: {e}")
        try:
            await query.answer("⚠️ حدث خطأ في التواصل مع تيليغرام.", show_alert=True)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.exception(f"sub3 unexpected error [{data}]")
        try:
            await query.answer("❌ خطأ غير متوقع. راجع السجلات.", show_alert=True)
        except Exception:
            pass
        return True


async def _sub3_dispatch_inner(query, context: ContextTypes.DEFAULT_TYPE, data: str) -> bool:
    """المنطق الفعلي للـ dispatcher — مُنفصل لتسهيل معالجة الأخطاء."""

    # ── الرئيسية ───────────────────────────────────────────────────────────
    if data == "sub3_main":
        await sub3_main(query, context)
        return True

    if data == "sub3_refresh":
        await query.answer("✅ تم تحديث الجهات.")
        await sub3_main(query, context)
        return True

    # ── إضافة جهة ──────────────────────────────────────────────────────────
    if data == "sub3_add_menu":
        context.user_data["sub3_is_backup"] = False
        await sub3_add_menu(query, context, is_backup=False)
        return True

    if data == "sub3_backup_add":
        context.user_data["sub3_is_backup"] = True
        await sub3_add_menu(query, context, is_backup=True)
        return True

    if data == "sub3_add_channel":
        context.user_data["sub3_add_type"] = "channel"
        await query.answer("✅ تم تحديد نوع الجهة: قناة")
        is_b = context.user_data.get("sub3_is_backup", False)
        await sub3_add_menu(query, context, is_backup=is_b)
        return True

    if data == "sub3_add_group":
        context.user_data["sub3_add_type"] = "group"
        await query.answer("✅ تم تحديد نوع الجهة: مجموعة")
        is_b = context.user_data.get("sub3_is_backup", False)
        await sub3_add_menu(query, context, is_backup=is_b)
        return True

    if data == "sub3_add_bot":
        context.user_data["sub3_add_type"] = "bot"
        await query.answer("✅ تم تحديد نوع الجهة: بوت")
        is_b = context.user_data.get("sub3_is_backup", False)
        await sub3_add_menu(query, context, is_backup=is_b)
        return True

    if data == "sub3_add_link":
        await sub3_add_link(query, context)
        return True

    if data == "sub3_add_username":
        await sub3_add_username(query, context)
        return True

    if data == "sub3_add_check":
        await sub3_add_check(query, context)
        return True

    if data == "sub3_add_info":
        await sub3_add_info(query, context)
        return True

    if data == "sub3_add_settings":
        await sub3_add_settings(query, context)
        return True

    if data == "sub3_add_limit_menu":
        await sub3_add_limit_menu(query, context)
        return True

    if data == "sub3_input_limit_new":
        context.user_data["waiting_for"] = "sub3_input_limit_new"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("♾ بدون حد",  callback_data="sub3_limit_no_limit")],
            [InlineKeyboardButton("❌ إلغاء",    callback_data="sub3_add_limit_menu")],
        ])
        await query.edit_message_text(
            "👥 <b>إدخال حد المشتركين</b>\n\nأرسل العدد الآن (رقم صحيح).",
            reply_markup=kb, parse_mode="HTML",
        )
        return True

    if data == "sub3_limit_no_limit":
        context.user_data["sub3_add_limit"] = None
        await query.answer("✅ تم تحديد: بدون حد.")
        await sub3_add_settings(query, context)
        return True

    if data == "sub3_add_duration_menu":
        await sub3_add_duration_menu(query, context)
        return True

    for dur_key in ("week", "month", "permanent"):
        if data == f"sub3_dur_{dur_key}":
            context.user_data["sub3_add_duration"] = dur_key
            await query.answer(f"✅ تم تحديد مدة الاشتراك: {_duration_label(dur_key)}")
            await sub3_add_settings(query, context)
            return True

    if data == "sub3_dur_date":
        context.user_data["waiting_for"] = "sub3_input_duration_date"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="sub3_add_duration_menu")],
            *_footer("sub3_add_settings"),
        ])
        await query.edit_message_text(
            "📆 <b>إدخال تاريخ محدد</b>\n\nأرسل التاريخ المطلوب بصيغة: <code>YYYY-MM-DD</code>",
            reply_markup=kb, parse_mode="HTML",
        )
        return True

    if data == "sub3_add_confirm":
        await sub3_add_confirm(query, context)
        return True

    if data == "sub3_add_do":
        await sub3_add_do(query, context)
        return True

    if data == "sub3_add_cancel":
        for k in ("sub3_add_type","sub3_add_identifier","sub3_add_checked",
                  "sub3_check_result","sub3_add_chat_id","sub3_add_limit",
                  "sub3_add_duration","sub3_is_backup"):
            context.user_data.pop(k, None)
        context.user_data["waiting_for"] = None
        await query.answer("❌ تم إلغاء عملية الإضافة.", show_alert=True)
        await sub3_main(query, context)
        return True

    # ── قائمة الجهات ───────────────────────────────────────────────────────
    if data == "sub3_list":
        context.user_data.setdefault("sub3_browse_idx", 0)
        await sub3_list(query, context)
        return True

    if data == "sub3_list_next":
        context.user_data["sub3_browse_idx"] = context.user_data.get("sub3_browse_idx", 0) + 1
        await sub3_list(query, context)
        return True

    if data == "sub3_list_prev":
        context.user_data["sub3_browse_idx"] = max(0, context.user_data.get("sub3_browse_idx", 0) - 1)
        await sub3_list(query, context)
        return True

    if data == "sub3_list_refresh":
        await query.answer("⏳ جاري التحديث...")
        await sub3_list(query, context)
        return True

    if data in ("sub3_search", "sub3_search_screen"):
        await sub3_search(query, context)
        return True

    # ── فتح جهة محددة ──────────────────────────────────────────────────────
    if data.startswith("sub3_open_"):
        try:
            sid = int(data.split("_")[-1])
            await _render_entity_open(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    # ── إحصائيات ───────────────────────────────────────────────────────────
    if data.startswith("sub3_stats_"):
        try:
            sid = int(data.split("_")[-1])
            await sub3_stats(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    # ── مشتركو الجهة ───────────────────────────────────────────────────────
    if data.startswith("sub3_subscribers_"):
        try:
            sid = int(data.split("_")[-1])
            context.user_data["sub3_sub_idx"]    = 0
            context.user_data["sub3_sub_sub_id"] = sid
            await sub3_subscribers(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    if data == "sub3_sub_next":
        context.user_data["sub3_sub_idx"] = context.user_data.get("sub3_sub_idx", 0) + 1
        sid = context.user_data.get("sub3_sub_sub_id")
        if sid:
            await sub3_subscribers(query, context, sid)
        return True

    if data == "sub3_sub_prev":
        context.user_data["sub3_sub_idx"] = max(0, context.user_data.get("sub3_sub_idx", 0) - 1)
        sid = context.user_data.get("sub3_sub_sub_id")
        if sid:
            await sub3_subscribers(query, context, sid)
        return True

    # ── إعدادات جهة موجودة ─────────────────────────────────────────────────
    if data.startswith("sub3_settings_"):
        rest = data[len("sub3_settings_"):]
        if rest == "main":
            await sub3_settings_main(query, context)
        else:
            try:
                sid = int(rest)
                await sub3_settings_entity(query, context, sid)
            except ValueError:
                await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    if data.startswith("sub3_set_limit_"):
        try:
            sid = int(data.split("_")[-1])
            await sub3_set_limit(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    if data.startswith("sub3_no_limit_"):
        try:
            sid = int(data.split("_")[-1])
            await sub3_no_limit(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    if data.startswith("sub3_set_duration_"):
        try:
            sid = int(data.split("_")[-1])
            await sub3_set_duration(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    # sub3_dur_set_{sub_id}_{value}
    if data.startswith("sub3_dur_set_"):
        rest = data[len("sub3_dur_set_"):]
        if rest.startswith("date_"):
            try:
                sid = int(rest[len("date_"):])
                context.user_data["sub3_sel_id"]   = sid
                context.user_data["waiting_for"]    = f"sub3_dur_date_{sid}"
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ إلغاء", callback_data=f"sub3_set_duration_{sid}")],
                    *_footer(f"sub3_settings_{sid}"),
                ])
                await query.edit_message_text(
                    "📆 <b>إدخال تاريخ محدد</b>\n\nأرسل التاريخ بصيغة: <code>YYYY-MM-DD</code>",
                    reply_markup=kb, parse_mode="HTML",
                )
            except (ValueError, IndexError):
                await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        else:
            parts = rest.rsplit("_", 1)
            if len(parts) == 2:
                try:
                    sid = int(parts[0])
                    dur = parts[1]
                    set_setting(f"sub_duration_{sid}", dur)
                    await query.answer(f"✅ تم تحديد مدة الاشتراك: {_duration_label(dur)}", show_alert=True)
                    await sub3_settings_entity(query, context, sid)
                except (ValueError, IndexError):
                    await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    # ── تحليل الجهة ────────────────────────────────────────────────────────
    if data.startswith("sub3_analysis_"):
        try:
            sid = int(data.split("_")[-1])
            await sub3_analysis(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    # ── حذف جهة ───────────────────────────────────────────────────────────
    if data.startswith("sub3_delete_do_"):
        try:
            sid = int(data.split("_")[-1])
            await sub3_delete_do(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    if data.startswith("sub3_delete_"):
        try:
            sid = int(data.split("_")[-1])
            await sub3_delete_confirm(query, context, sid)
        except (ValueError, IndexError):
            await query.answer("❌ بيانات غير صحيحة.", show_alert=True)
        return True

    if data == "sub3_delete_menu":
        await sub3_delete_menu(query, context)
        return True

    # ── الاحتياطي ──────────────────────────────────────────────────────────
    if data == "sub3_backup":
        await sub3_backup(query, context)
        return True

    if data == "sub3_backup_list":
        context.user_data.setdefault("sub3_backup_idx", 0)
        await sub3_list(query, context, is_backup=True)
        return True

    if data == "sub3_backup_next":
        context.user_data["sub3_backup_idx"] = context.user_data.get("sub3_backup_idx", 0) + 1
        await sub3_list(query, context, is_backup=True)
        return True

    if data == "sub3_backup_prev":
        context.user_data["sub3_backup_idx"] = max(0, context.user_data.get("sub3_backup_idx", 0) - 1)
        await sub3_list(query, context, is_backup=True)
        return True

    if data == "sub3_backup_refresh":
        await query.answer("⏳ جاري التحديث...")
        context.user_data["sub3_backup_idx"] = 0
        await sub3_list(query, context, is_backup=True)
        return True

    # ── حسب المشتركين ──────────────────────────────────────────────────────
    if data == "sub3_by_sub":
        context.user_data.setdefault("sub3_by_sub_idx", 0)
        await sub3_by_sub(query, context)
        return True

    if data == "sub3_bysub_desc":
        context.user_data["sub3_by_sub_order"] = "desc"
        context.user_data["sub3_by_sub_idx"]   = 0
        await query.answer("✅ تم ترتيب الجهات من الأكثر اشتراكًا إلى الأقل.")
        await sub3_by_sub(query, context)
        return True

    if data == "sub3_bysub_asc":
        context.user_data["sub3_by_sub_order"] = "asc"
        context.user_data["sub3_by_sub_idx"]   = 0
        await query.answer("✅ تم ترتيب الجهات من الأقل اشتراكًا إلى الأعلى.")
        await sub3_by_sub(query, context)
        return True

    if data == "sub3_bysub_next":
        context.user_data["sub3_by_sub_idx"] = context.user_data.get("sub3_by_sub_idx", 0) + 1
        await sub3_by_sub(query, context)
        return True

    if data == "sub3_bysub_prev":
        context.user_data["sub3_by_sub_idx"] = max(0, context.user_data.get("sub3_by_sub_idx", 0) - 1)
        await sub3_by_sub(query, context)
        return True

    # ── الإعدادات العامة ───────────────────────────────────────────────────
    if data == "sub3_settings_main":
        await sub3_settings_main(query, context)
        return True

    if data == "sub3_enable":
        await sub3_enable(query, context)
        return True

    if data == "sub3_disable_confirm":
        await sub3_disable_confirm(query, context)
        return True

    if data == "sub3_disable_do":
        await sub3_disable_do(query, context)
        return True

    if data == "sub3_edit_msg":
        await sub3_edit_msg(query, context)
        return True

    if data == "sub3_msg_save":
        msg = context.user_data.get("sub3_new_msg", "")
        if msg:
            set_setting("sub_message", msg)
            await query.answer("✅ تم حفظ تعديل رسالة الاشتراك بنجاح.", show_alert=True)
        else:
            await query.answer("⚠️ لا توجد رسالة جديدة لحفظها. أرسل النص أولًا.", show_alert=True)
        await sub3_settings_main(query, context)
        return True

    if data == "sub3_edit_btns":
        await _render_btns_editor(query, context, is_reply=False)
        return True

    if data == "sub3_btn_add_start":
        context.user_data["waiting_for"] = "sub3_btn_label"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="sub3_edit_btns")],
            *_footer("sub3_settings_main"),
        ])
        await _safe_edit(
            query,
            "➕ <b>إضافة زر جديد</b>\n\nالخطوة 1/2: أرسل <b>نص الزر</b> (مثال: اشترك الآن).",
            reply_markup=kb, parse_mode="HTML",
        )
        return True

    if data.startswith("sub3_btn_del_"):
        import json
        try:
            idx = int(data.split("_")[-1])
            raw  = get_setting("sub_buttons_json", "[]")
            btns = json.loads(raw)
            if 0 <= idx < len(btns):
                removed = btns.pop(idx)
                set_setting("sub_buttons_json", json.dumps(btns, ensure_ascii=False))
                await query.answer(f"🗑 تم حذف الزر: {removed.get('label','')}", show_alert=True)
            await _render_btns_editor(query, context, is_reply=False)
        except Exception:
            await query.answer("❌ خطأ في الحذف.", show_alert=True)
        return True

    if data == "sub3_btn_clear":
        set_setting("sub_buttons_json", "[]")
        await query.answer("🗑 تم حذف جميع الأزرار.", show_alert=True)
        await _render_btns_editor(query, context, is_reply=False)
        return True

    if data == "sub3_btn_save":
        await query.answer("✅ تم حفظ تعديلات أزرار الاشتراك بنجاح.", show_alert=True)
        await sub3_settings_main(query, context)
        return True

    if data == "sub3_recheck":
        await sub3_recheck(query, context)
        return True

    # ── فحص الجهات ─────────────────────────────────────────────────────────
    if data == "sub3_inspect":
        await sub3_inspect(query, context)
        return True

    if data == "sub3_inspect_all":
        await sub3_inspect_all(query, context)
        return True

    if data == "sub3_inspect_specific":
        await sub3_inspect_specific(query, context)
        return True

    if data == "sub3_no_perms":
        context.user_data.setdefault("sub3_no_perms_idx", 0)
        await sub3_no_perms(query, context)
        return True

    if data == "sub3_noperms_next":
        context.user_data["sub3_no_perms_idx"] = context.user_data.get("sub3_no_perms_idx", 0) + 1
        await sub3_no_perms(query, context)
        return True

    if data == "sub3_noperms_prev":
        context.user_data["sub3_no_perms_idx"] = max(0, context.user_data.get("sub3_no_perms_idx", 0) - 1)
        await sub3_no_perms(query, context)
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
# معالج الرسائل النصية
# ─────────────────────────────────────────────────────────────────────────────

async def sub3_handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    waiting = context.user_data.get("waiting_for", "")
    if not waiting or not waiting.startswith("sub3_"):
        return False

    text = (update.message.text or "").strip()

    # ── إدخال رابط جهة جديدة ───────────────────────────────────────────────
    if waiting == "sub3_input_link":
        context.user_data["waiting_for"] = None
        raw = text.strip()
        if not (raw.startswith("https://t.me/") or raw.startswith("http://") or "@" in raw or raw.startswith("-")):
            await update.message.reply_text(
                "⚠️ <b>الرابط غير صالح.</b>\n\n"
                "الرجاء إرسال رابط صحيح يبدأ بـ https://t.me/... أو @username",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 إعادة المحاولة", callback_data="sub3_add_link")],
                    [InlineKeyboardButton("❌ إلغاء العملية",  callback_data="sub3_add_cancel")],
                    *_footer("sub3_add_menu"),
                ]),
                parse_mode="HTML",
            )
            return True
        context.user_data["sub3_add_identifier"] = raw
        is_b = context.user_data.get("sub3_is_backup", False)
        await update.message.reply_text(
            "✅ <b>تم حفظ رابط الجهة بنجاح.</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👁 فحص الجهة",     callback_data="sub3_add_check")],
                [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="sub3_add_menu")],
                *_footer("sub3_main"),
            ]),
            parse_mode="HTML",
        )
        return True

    # ── إدخال يوزر ────────────────────────────────────────────────────────
    if waiting == "sub3_input_username":
        context.user_data["waiting_for"] = None
        raw = text.lstrip("@").strip()
        if not raw:
            await update.message.reply_text(
                "⚠️ <b>اليوزر غير صالح. حاول مرة أخرى.</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 إعادة المحاولة", callback_data="sub3_add_username")],
                    *_footer("sub3_add_menu"),
                ]),
                parse_mode="HTML",
            )
            return True
        context.user_data["sub3_add_identifier"] = f"@{raw}"
        await update.message.reply_text(
            "✅ <b>تم حفظ يوزر الجهة بنجاح.</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👁 فحص الجهة",     callback_data="sub3_add_check")],
                [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="sub3_add_menu")],
                *_footer("sub3_main"),
            ]),
            parse_mode="HTML",
        )
        return True

    # ── إدخال حد المشتركين (جهة جديدة) ────────────────────────────────────
    if waiting == "sub3_input_limit_new":
        context.user_data["waiting_for"] = None
        if not text.isdigit() or int(text) < 0:
            await update.message.reply_text(
                "⚠️ <b>الرجاء إدخال رقم صحيح أكبر من أو يساوي 0.</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 إعادة المحاولة", callback_data="sub3_input_limit_new")],
                    *_footer("sub3_add_limit_menu"),
                ]),
                parse_mode="HTML",
            )
            return True
        val = int(text)
        context.user_data["sub3_add_limit"] = val if val > 0 else None
        await update.message.reply_text(
            f"✅ <b>تم حفظ العدد بنجاح: {val if val > 0 else 'بدون حد'}</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع للإعدادات", callback_data="sub3_add_settings")],
                *_footer("sub3_add_menu"),
            ]),
            parse_mode="HTML",
        )
        return True

    # ── إدخال تاريخ المدة (جهة جديدة) ─────────────────────────────────────
    if waiting == "sub3_input_duration_date":
        context.user_data["waiting_for"] = None
        try:
            d = date.fromisoformat(text)
            context.user_data["sub3_add_duration"] = str(d)
            await update.message.reply_text(
                f"✅ <b>تم حفظ التاريخ المحدد بنجاح: {d}</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع للإعدادات", callback_data="sub3_add_settings")],
                    *_footer("sub3_add_menu"),
                ]),
                parse_mode="HTML",
            )
        except ValueError:
            await update.message.reply_text(
                "⚠️ <b>صيغة التاريخ غير صحيحة.</b>\nالرجاء الإرسال بالشكل: <code>2026-03-20</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 إعادة المحاولة", callback_data="sub3_dur_date")],
                    *_footer("sub3_add_settings"),
                ]),
                parse_mode="HTML",
            )
        return True

    # ── إدخال حد المشتركين (جهة موجودة) ───────────────────────────────────
    if waiting.startswith("sub3_input_limit_"):
        sid_str = waiting[len("sub3_input_limit_"):]
        context.user_data["waiting_for"] = None
        try:
            sid = int(sid_str)
        except ValueError:
            return True
        if not text.isdigit() or int(text) < 0:
            await update.message.reply_text(
                "⚠️ <b>الرجاء إدخال رقم صحيح أكبر من أو يساوي 0.</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 إعادة المحاولة", callback_data=f"sub3_set_limit_{sid}")],
                    *_footer(f"sub3_settings_{sid}"),
                ]),
                parse_mode="HTML",
            )
            return True
        val = int(text)
        db = SessionLocal()
        try:
            ch = db.query(SubscriptionChannel).filter_by(id=sid).first()
            if ch:
                ch.subscriber_limit = val if val > 0 else None
                db.commit()
        finally:
            db.close()
        await update.message.reply_text(
            f"✅ <b>تم حفظ حد المشتركين بنجاح: {val if val > 0 else 'بدون حد'}</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع للإعدادات", callback_data=f"sub3_settings_{sid}")],
                *_footer("sub3_list"),
            ]),
            parse_mode="HTML",
        )
        return True

    # ── إدخال تاريخ المدة (جهة موجودة) ────────────────────────────────────
    if waiting.startswith("sub3_dur_date_"):
        sid_str = waiting[len("sub3_dur_date_"):]
        context.user_data["waiting_for"] = None
        try:
            sid = int(sid_str)
        except ValueError:
            return True
        try:
            d = date.fromisoformat(text)
            set_setting(f"sub_duration_{sid}", str(d))
            await update.message.reply_text(
                f"✅ <b>تم حفظ التاريخ المحدد بنجاح: {d}</b>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع للإعدادات", callback_data=f"sub3_settings_{sid}")],
                    *_footer("sub3_list"),
                ]),
                parse_mode="HTML",
            )
        except ValueError:
            await update.message.reply_text(
                "⚠️ <b>صيغة التاريخ غير صحيحة.</b>\nالرجاء الإرسال بالشكل: <code>2026-03-20</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 إعادة المحاولة", callback_data=f"sub3_dur_set_date_{sid}")],
                    *_footer(f"sub3_settings_{sid}"),
                ]),
                parse_mode="HTML",
            )
        return True

    # ── تعديل رسالة الاشتراك ───────────────────────────────────────────────
    if waiting == "sub3_edit_msg":
        context.user_data["waiting_for"] = None
        context.user_data["sub3_new_msg"] = text
        await update.message.reply_text(
            "✅ <b>تم حفظ النص الجديد مؤقتًا.</b>\n\nاضغط 💾 حفظ التعديل لتأكيد الحفظ.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💾 حفظ التعديل",  callback_data="sub3_msg_save")],
                [InlineKeyboardButton("❌ إلغاء",        callback_data="sub3_settings_main")],
                *_footer("sub3_settings_main"),
            ]),
            parse_mode="HTML",
        )
        return True

    # ── فحص جهة محددة (نصي) ───────────────────────────────────────────────
    if waiting == "sub3_inspect_specific":
        context.user_data["waiting_for"] = None
        await update.message.reply_text("⏳ <b>جاري فحص الجهة...</b>", parse_mode="HTML")
        result = await _do_check_entity(context.bot, text)
        if result["ok"]:
            uname = f"@{result['username']}" if result.get("username") else "—"
            await update.message.reply_text(
                f"✅ <b>تم فحص الجهة بنجاح.</b>\n\n"
                f"• الاسم: <b>{_e(result['title'])}</b>\n"
                f"• اليوزر: {uname}\n"
                f"• 🆔 Chat ID: <code>{result['chat_id']}</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع للفحص", callback_data="sub3_inspect")],
                    *_footer("sub3_main"),
                ]),
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"❌ <b>تعذر الوصول إلى الجهة.</b>\n<code>{_e(result['error'])}</code>",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 إعادة المحاولة", callback_data="sub3_inspect_specific")],
                    [InlineKeyboardButton("🔙 رجوع للفحص",     callback_data="sub3_inspect")],
                    *_footer("sub3_main"),
                ]),
                parse_mode="HTML",
            )
        return True

    # ── البحث عن جهة ────────────────────────────────────────────────────────
    if waiting == "sub3_search_entity":
        context.user_data["waiting_for"] = None
        await _show_search_results(update, context, text)
        return True

    # ── إضافة زر جديد: نص الزر ──────────────────────────────────────────────
    if waiting == "sub3_btn_label":
        context.user_data["waiting_for"] = "sub3_btn_url"
        context.user_data["sub3_btn_pending_label"] = text
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="sub3_edit_btns")],
            *_footer("sub3_settings_main"),
        ])
        await update.message.reply_text(
            f"➕ <b>إضافة زر جديد</b>\n\nنص الزر: <b>{_e(text)}</b>\n\n"
            "الخطوة 2/2: أرسل الآن <b>رابط الزر</b> (يجب أن يبدأ بـ https://).",
            reply_markup=kb, parse_mode="HTML",
        )
        return True

    # ── إضافة زر جديد: رابط الزر ────────────────────────────────────────────
    if waiting == "sub3_btn_url":
        import json
        context.user_data["waiting_for"] = None
        label = context.user_data.pop("sub3_btn_pending_label", "زر")
        url   = text.strip()
        if not (url.startswith("https://") or url.startswith("http://") or url.startswith("t.me")):
            await update.message.reply_text(
                "⚠️ <b>الرابط غير صالح.</b>\nيجب أن يبدأ بـ https://",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 إعادة المحاولة", callback_data="sub3_btn_add_start")],
                    *_footer("sub3_settings_main"),
                ]),
                parse_mode="HTML",
            )
            return True
        raw   = get_setting("sub_buttons_json", "[]")
        try:
            btns = json.loads(raw)
        except Exception:
            btns = []
        btns.append({"label": label, "url": url})
        set_setting("sub_buttons_json", json.dumps(btns, ensure_ascii=False))
        await update.message.reply_text(
            f"✅ <b>تم إضافة الزر بنجاح.</b>\n• النص: {_e(label)}\n• الرابط: {_e(url)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة زر آخر", callback_data="sub3_btn_add_start")],
                [InlineKeyboardButton("💾 حفظ التعديل",  callback_data="sub3_btn_save")],
                *_footer("sub3_settings_main"),
            ]),
            parse_mode="HTML",
        )
        return True

    return False

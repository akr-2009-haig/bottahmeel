STRINGS = {
    "ar": {
        "welcome": "مرحبا بك يا {name} 👋",
        "subscribe_required": "لإستخدام البوت يرجى الإشتراك في القنوات التالية\n📢 اشترك في القنوات التالية",
        "check_subscription": "✅ تحقق من الاشتراك",
        "subscribed": "✅ تم التحقق من اشتراكك! يمكنك الآن استخدام البوت.",
        "not_subscribed": "❌ لم يتم التحقق من اشتراكك. يرجى الاشتراك في جميع القنوات أولاً.",
        "downloading": "⏰┇يرجى الانتظار، يتم قياس حجم التحميل...",
        "unsupported": "⚠️ الرابط غير مدعوم حالياً. يرجى إرسال رابط من منصة مدعومة ومفعّلة.",
        "error": "❌ حدث خطأ أثناء التحميل. يرجى المحاولة مجدداً.",
        "success_caption": "📥 تم التحميل بنجاح\n\n🤖 @{bot_name}",
        "help_text": "🤖 {bot_name} يمكنه تنزيل الوسائط من عدة منصات مدعومة.\n\nطريقة الاستخدام:\n   1. انسخ رابط المنشور أو الملف العام من منصة مدعومة.\n   2. أرسل الرابط إلى البوت.\n   3. سيُضاف الطلب إلى قائمة المعالجة ثم تصلك النتيجة عند اكتماله.",
        "lang_select": "🌍 اختر لغة البوت:",
        "lang_changed": "✅ تم تغيير اللغة بنجاح إلى العربية",
        "add_to_chat": "➕ أضفني إلى الدردشة",
        "main_menu": "📱 القائمة الرئيسية",
        "banned": "🚫 تم حظرك من استخدام هذا البوت.",
        "send_link": "📎 أرسل رابطاً مدعوماً للتحميل",
        "back": "🔙 رجوع",
        "back_home": "🏠 الرئيسية",
    },
    "en": {
        "welcome": "Welcome {name} 👋",
        "subscribe_required": "To use the bot, please subscribe to the following channels\n📢 Subscribe to channels",
        "check_subscription": "✅ Check Subscription",
        "subscribed": "✅ Subscription verified! You can now use the bot.",
        "not_subscribed": "❌ Subscription not verified. Please subscribe to all channels first.",
        "downloading": "⏰┇Please wait, measuring download size...",
        "unsupported": "⚠️ Unsupported link right now. Please send a link from a supported and enabled platform.",
        "error": "❌ An error occurred while downloading. Please try again.",
        "success_caption": "📥 Downloaded successfully\n\n🤖 @{bot_name}",
        "help_text": "🤖 {bot_name} can download media from multiple supported platforms.\n\nHow to use it:\n   1. Copy the post or public file link from a supported platform.\n   2. Send the link to the bot.\n   3. The request will be queued and the result will be delivered when processing finishes.",
        "lang_select": "🌍 Select bot language:",
        "lang_changed": "✅ Language successfully changed to English",
        "add_to_chat": "➕ Add me to chat",
        "main_menu": "📱 Main Menu",
        "banned": "🚫 You have been banned from using this bot.",
        "send_link": "📎 Send a supported link to download",
        "back": "🔙 Back",
        "back_home": "🏠 Home",
    },
    "ru": {
        "welcome": "Добро пожаловать {name} 👋",
        "subscribe_required": "Для использования бота подпишитесь на следующие каналы\n📢 Подпишитесь на каналы",
        "check_subscription": "✅ Проверить подписку",
        "subscribed": "✅ Подписка подтверждена! Теперь вы можете использовать бота.",
        "not_subscribed": "❌ Подписка не подтверждена. Сначала подпишитесь на все каналы.",
        "downloading": "⏰┇Пожалуйста подождите, измеряется размер загрузки...",
        "unsupported": "⚠️ Эта ссылка сейчас не поддерживается. Отправьте ссылку с поддерживаемой и включённой платформы.",
        "error": "❌ Произошла ошибка при загрузке. Попробуйте еще раз.",
        "success_caption": "📥 Загружено успешно\n\n🤖 @{bot_name}",
        "help_text": "🤖 {bot_name} может скачивать медиа с нескольких поддерживаемых платформ.\n\nКак использовать:\n   1. Скопируйте ссылку на пост или публичный файл с поддерживаемой платформы.\n   2. Отправьте ссылку боту.\n   3. Запрос будет поставлен в очередь, а результат придёт после обработки.",
        "lang_select": "🌍 Выберите язык бота:",
        "lang_changed": "✅ Язык успешно изменён на Русский",
        "add_to_chat": "➕ Добавить в чат",
        "main_menu": "📱 Главное меню",
        "banned": "🚫 Вы заблокированы.",
        "send_link": "📎 Отправьте поддерживаемую ссылку для загрузки",
        "back": "🔙 Назад",
        "back_home": "🏠 Главная",
    }
}


def get_string(key: str, lang: str = "ar", **kwargs) -> str:
    lang_strings = STRINGS.get(lang, STRINGS["ar"])
    text = lang_strings.get(key, STRINGS["ar"].get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text

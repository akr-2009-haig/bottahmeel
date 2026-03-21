STRINGS = {
    "ar": {
        "welcome": "مرحبا بك يا {name} 👋",
        "subscribe_required": "لإستخدام البوت يرجى الإشتراك في القنوات التالية\n📢 اشترك في القنوات التالية",
        "check_subscription": "✅ تحقق من الاشتراك",
        "subscribed": "✅ تم التحقق من اشتراكك! يمكنك الآن استخدام البوت.",
        "not_subscribed": "❌ لم يتم التحقق من اشتراكك. يرجى الاشتراك في جميع القنوات أولاً.",
        "downloading": "⏰┇يرجى الانتظار، يتم قياس حجم التحميل...",
        "unsupported": "⚠️ الرابط غير مدعوم. يرجى إرسال رابط TikTok صحيح.",
        "error": "❌ حدث خطأ أثناء التحميل. يرجى المحاولة مجدداً.",
        "success_caption": "📥 تم التحميل بنجاح\n\n🤖 @{bot_name}",
        "help_text": "🤖 {bot_name} يمكنه تنزيل مقاطع فيديو لك من TikTok\n\nكيفية تنزيل مقطع فيديو:\n   1. انتقل إلى تطبيق TikTok\n   2. اختر مقطع فيديو يثير اهتمامك\n   3. انقر على زر ↪️ أو ثلاث نقاط في الزاوية اليمنى العليا.\n   4. انقر فوق الزر \"نسخ\".\n   5. أرسل الرابط إلى الروبوت وفي غضون ثوانٍ ستتلقى مقطع فيديو/صورة.",
        "lang_select": "🌍 اختر لغة البوت:",
        "lang_changed": "✅ تم تغيير اللغة بنجاح إلى العربية",
        "add_to_chat": "➕ أضفني إلى الدردشة",
        "main_menu": "📱 القائمة الرئيسية",
        "banned": "🚫 تم حظرك من استخدام هذا البوت.",
        "send_link": "📎 أرسل رابط TikTok للتحميل",
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
        "unsupported": "⚠️ Unsupported link. Please send a valid TikTok link.",
        "error": "❌ An error occurred while downloading. Please try again.",
        "success_caption": "📥 Downloaded successfully\n\n🤖 @{bot_name}",
        "help_text": "🤖 {bot_name} can download videos for you from TikTok\n\nHow to download a video:\n   1. Go to the TikTok app\n   2. Choose a video that interests you\n   3. Click the ↪️ button or three dots in the top right corner.\n   4. Click the \"Copy\" button.\n   5. Send the link to the bot and within seconds you'll receive a video/image.",
        "lang_select": "🌍 Select bot language:",
        "lang_changed": "✅ Language successfully changed to English",
        "add_to_chat": "➕ Add me to chat",
        "main_menu": "📱 Main Menu",
        "banned": "🚫 You have been banned from using this bot.",
        "send_link": "📎 Send a TikTok link to download",
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
        "unsupported": "⚠️ Ссылка не поддерживается. Отправьте корректную ссылку TikTok.",
        "error": "❌ Произошла ошибка при загрузке. Попробуйте еще раз.",
        "success_caption": "📥 Загружено успешно\n\n🤖 @{bot_name}",
        "help_text": "🤖 {bot_name} может скачивать видео для вас из TikTok\n\nКак скачать видео:\n   1. Откройте приложение TikTok\n   2. Выберите видео\n   3. Нажмите кнопку ↪️ или три точки.\n   4. Нажмите \"Копировать\".\n   5. Отправьте ссылку боту.",
        "lang_select": "🌍 Выберите язык бота:",
        "lang_changed": "✅ Язык успешно изменён на Русский",
        "add_to_chat": "➕ Добавить в чат",
        "main_menu": "📱 Главное меню",
        "banned": "🚫 Вы заблокированы.",
        "send_link": "📎 Отправьте ссылку TikTok для загрузки",
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

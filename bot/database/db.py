import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from .models import Base, BotSettings, AntiFloodSettings, AdminUser, BotLanguage
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


WORLD_LANGUAGES = [
    # code,  name (native),        flag,  builtin
    ("ar",  "العربية",             "🇸🇦",  True),
    ("en",  "English",             "🇬🇧",  True),
    ("ru",  "Русский",             "🇷🇺",  True),
    ("fr",  "Français",            "🇫🇷",  False),
    ("de",  "Deutsch",             "🇩🇪",  False),
    ("es",  "Español",             "🇪🇸",  False),
    ("pt",  "Português",           "🇵🇹",  False),
    ("it",  "Italiano",            "🇮🇹",  False),
    ("nl",  "Nederlands",          "🇳🇱",  False),
    ("pl",  "Polski",              "🇵🇱",  False),
    ("tr",  "Türkçe",              "🇹🇷",  False),
    ("id",  "Indonesia",           "🇮🇩",  False),
    ("ms",  "Melayu",              "🇲🇾",  False),
    ("th",  "ภาษาไทย",             "🇹🇭",  False),
    ("vi",  "Tiếng Việt",          "🇻🇳",  False),
    ("zh",  "中文",                 "🇨🇳",  False),
    ("ja",  "日本語",               "🇯🇵",  False),
    ("ko",  "한국어",               "🇰🇷",  False),
    ("hi",  "हिन्दी",              "🇮🇳",  False),
    ("bn",  "বাংলা",               "🇧🇩",  False),
    ("ur",  "اردو",                "🇵🇰",  False),
    ("fa",  "فارسی",               "🇮🇷",  False),
    ("he",  "עברית",               "🇮🇱",  False),
    ("uk",  "Українська",          "🇺🇦",  False),
    ("cs",  "Čeština",             "🇨🇿",  False),
    ("sk",  "Slovenčina",          "🇸🇰",  False),
    ("ro",  "Română",              "🇷🇴",  False),
    ("hu",  "Magyar",              "🇭🇺",  False),
    ("sv",  "Svenska",             "🇸🇪",  False),
    ("no",  "Norsk",               "🇳🇴",  False),
    ("da",  "Dansk",               "🇩🇰",  False),
    ("fi",  "Suomi",               "🇫🇮",  False),
    ("el",  "Ελληνικά",            "🇬🇷",  False),
    ("bg",  "Български",           "🇧🇬",  False),
    ("hr",  "Hrvatski",            "🇭🇷",  False),
    ("sr",  "Српски",              "🇷🇸",  False),
    ("lt",  "Lietuvių",            "🇱🇹",  False),
    ("lv",  "Latviešu",            "🇱🇻",  False),
    ("et",  "Eesti",               "🇪🇪",  False),
    ("az",  "Azərbaycan",          "🇦🇿",  False),
    ("ka",  "ქართული",             "🇬🇪",  False),
    ("am",  "አማርኛ",               "🇪🇹",  False),
    ("sw",  "Kiswahili",           "🇹🇿",  False),
    ("af",  "Afrikaans",           "🇿🇦",  False),
    ("kk",  "Қазақша",             "🇰🇿",  False),
    ("uz",  "O'zbek",              "🇺🇿",  False),
    ("ky",  "Кыргызча",            "🇰🇬",  False),
    ("tg",  "Тоҷикӣ",              "🇹🇯",  False),
    ("mn",  "Монгол",              "🇲🇳",  False),
    ("my",  "မြန်မာ",              "🇲🇲",  False),
]


def init_db():
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _seed_defaults()
    _seed_languages()
    logger.info("Database initialized successfully")


def _run_migrations():
    """Run incremental DB migrations safely."""
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE webapp_buttons ADD COLUMN IF NOT EXISTS "
                "placement VARCHAR(30) NOT NULL DEFAULT 'inline'"
            ))
            conn.commit()
    except Exception as e:
        logger.warning(f"Migration warning (safe to ignore if column exists): {e}")


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        db.close()
        raise e


def _seed_defaults():
    db = SessionLocal()
    try:
        default_settings = [
            ("subscription_enabled", "true"),
            ("bot_name", "SaveEliteBot"),
            ("start_message", "مرحبا بك يا {name} 👋\n\nيمكنني تنزيل الوسائط من TikTok.\nأرسل رابط الفيديو للبدء."),
            ("subscription_message", "لإستخدام البوت يرجى الإشتراك في القنوات التالية\n📢 اشترك في القنوات التالية"),
            ("help_message", "🤖 يمكنني تنزيل مقاطع فيديو من TikTok\n\nكيفية التنزيل:\n1. انتقل إلى تطبيق TikTok\n2. اختر مقطع فيديو\n3. انقر على زر ↪️ أو ثلاث نقاط\n4. انقر فوق نسخ الرابط\n5. أرسل الرابط هنا"),
            ("downloading_message", "⏰┇يرجى الانتظار، يتم قياس حجم التحميل..."),
            ("unsupported_message", "⚠️ الرابط غير مدعوم. يرجى إرسال رابط TikTok صحيح."),
            ("error_message", "❌ حدث خطأ أثناء التحميل. يرجى المحاولة مجدداً."),
            ("video_caption", "📥 تم التحميل بنجاح\n\n🤖 @{bot_name}"),
            ("photo_caption", "🖼 تم التحميل بنجاح\n\n🤖 @{bot_name}"),
            ("activity_status", "upload_video"),
            ("tiktok_enabled", "true"),
            ("youtube_enabled", "true"),
            ("instagram_enabled", "true"),
            ("twitter_enabled", "true"),
            ("facebook_enabled", "true"),
            ("pinterest_enabled", "true"),
            ("likee_enabled", "true"),
            ("snapchat_enabled", "false"),
            ("reddit_enabled", "false"),
            ("vimeo_enabled", "false"),
            ("dailymotion_enabled", "false"),
            ("tiktok_disabled_msg", "عذراً، TikTok غير مفعل حالياً."),
            ("youtube_disabled_msg", "عذراً، YouTube غير مفعل حالياً."),
            ("instagram_disabled_msg", "عذراً، Instagram غير مفعل حالياً."),
            ("twitter_disabled_msg", "عذراً، Twitter/X غير مفعل حالياً."),
            ("facebook_disabled_msg", "عذراً، Facebook غير مفعل حالياً."),
            ("pinterest_disabled_msg", "عذراً، Pinterest غير مفعل حالياً."),
            ("likee_disabled_msg", "عذراً، Likee غير مفعل حالياً."),
            ("snapchat_disabled_msg", "عذراً، Snapchat غير مفعل حالياً."),
            ("reddit_disabled_msg", "عذراً، Reddit غير مفعل حالياً."),
            ("vimeo_disabled_msg", "عذراً، Vimeo غير مفعل حالياً."),
            ("dailymotion_disabled_msg", "عذراً، Dailymotion غير مفعل حالياً."),
            ("disabled_platform_generic_msg", "عذراً، هذه المنصة غير مفعلة حالياً في البوت."),
            ("unsupported_platform_msg", "⚠️ هذه المنصة غير مدعومة حالياً. يرجى إرسال رابط من منصة مدعومة."),
            ("text_format", "none"),
        ]
        for key, value in default_settings:
            existing = db.query(BotSettings).filter_by(key=key).first()
            if not existing:
                db.add(BotSettings(key=key, value=value))

        antiflood = db.query(AntiFloodSettings).first()
        if not antiflood:
            db.add(AntiFloodSettings())

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding defaults: {e}")
    finally:
        db.close()


def _seed_languages():
    """Seed the 50 world languages — builtin 3 enabled by default."""
    db = SessionLocal()
    try:
        for i, (code, name, flag, builtin) in enumerate(WORLD_LANGUAGES):
            existing = db.query(BotLanguage).filter_by(code=code).first()
            if not existing:
                db.add(BotLanguage(
                    code=code,
                    name=name,
                    flag=flag,
                    is_enabled=builtin,
                    is_builtin=builtin,
                    position=i,
                ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding languages: {e}")
    finally:
        db.close()


def get_setting(key: str, default: str = "") -> str:
    db = SessionLocal()
    try:
        setting = db.query(BotSettings).filter_by(key=key).first()
        return setting.value if setting else default
    finally:
        db.close()


def set_setting(key: str, value: str):
    db = SessionLocal()
    try:
        setting = db.query(BotSettings).filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            db.add(BotSettings(key=key, value=value))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error setting {key}: {e}")
    finally:
        db.close()

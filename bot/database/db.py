import os
import time
import threading
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool as QueuedPool

from .models import Base, BotSettings, AntiFloodSettings, BotLanguage
import logging

logger = logging.getLogger(__name__)

engine = None
_engine_lock = threading.Lock()


class _SessionProxy:
    """Callable proxy for sessionmaker; initialized by init_db()."""

    def __init__(self):
        self._factory = None

    def __call__(self, *args, **kwargs):
        if self._factory is None:
            raise RuntimeError(
                "Database not initialized. "
                "Ensure DATABASE_URL is set and init_db() has been called."
            )
        return self._factory(*args, **kwargs)

    def _setup(self, factory):
        self._factory = factory


SessionLocal = _SessionProxy()


def _create_engine():
    global engine
    if engine is not None:
        return
    with _engine_lock:
        if engine is not None:
            return
        db_url = os.environ.get("DATABASE_URL", "").strip()
        if not db_url:
            raise EnvironmentError(
                "DATABASE_URL environment variable is not set.\n"
                "Please add a PostgreSQL connection URL to your environment variables.\n"
                "Example: DATABASE_URL=postgresql://user:password@host:5432/dbname"
            )
        engine = create_engine(
            db_url,
            poolclass=QueuedPool,
            pool_size=25,
            max_overflow=50,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            echo=False,
        )
        SessionLocal._setup(sessionmaker(autocommit=False, autoflush=False, bind=engine))


_settings_cache: dict[str, tuple[str, float]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 30.0


def _cache_get(key: str):
    with _cache_lock:
        entry = _settings_cache.get(key)
        if entry and (time.monotonic() - entry[1]) < _CACHE_TTL:
            return entry[0]
    return None


def _cache_set(key: str, value: str):
    with _cache_lock:
        _settings_cache[key] = (value, time.monotonic())


def _cache_invalidate(key: str):
    with _cache_lock:
        _settings_cache.pop(key, None)


WORLD_LANGUAGES = [
    ("ar", "العربية", "🇸🇦", True),
    ("en", "English", "🇬🇧", True),
    ("ru", "Русский", "🇷🇺", True),
    ("fr", "Français", "🇫🇷", False),
    ("de", "Deutsch", "🇩🇪", False),
    ("es", "Español", "🇪🇸", False),
    ("pt", "Português", "🇵🇹", False),
    ("it", "Italiano", "🇮🇹", False),
    ("nl", "Nederlands", "🇳🇱", False),
    ("pl", "Polski", "🇵🇱", False),
    ("tr", "Türkçe", "🇹🇷", False),
    ("id", "Indonesia", "🇮🇩", False),
    ("ms", "Melayu", "🇲🇾", False),
    ("th", "ภาษาไทย", "🇹🇭", False),
    ("vi", "Tiếng Việt", "🇻🇳", False),
    ("zh", "中文", "🇨🇳", False),
    ("ja", "日本語", "🇯🇵", False),
    ("ko", "한국어", "🇰🇷", False),
    ("hi", "हिन्दी", "🇮🇳", False),
    ("bn", "বাংলা", "🇧🇩", False),
    ("ur", "اردو", "🇵🇰", False),
    ("fa", "فارسی", "🇮🇷", False),
    ("he", "עברית", "🇮🇱", False),
    ("uk", "Українська", "🇺🇦", False),
    ("cs", "Čeština", "🇨🇿", False),
    ("sk", "Slovenčina", "🇸🇰", False),
    ("ro", "Română", "🇷🇴", False),
    ("hu", "Magyar", "🇭🇺", False),
    ("sv", "Svenska", "🇸🇪", False),
    ("no", "Norsk", "🇳🇴", False),
    ("da", "Dansk", "🇩🇰", False),
    ("fi", "Suomi", "🇫🇮", False),
    ("el", "Ελληνικά", "🇬🇷", False),
    ("bg", "Български", "🇧🇬", False),
    ("hr", "Hrvatski", "🇭🇷", False),
    ("sr", "Српски", "🇷🇸", False),
    ("lt", "Lietuvių", "🇱🇹", False),
    ("lv", "Latviešu", "🇱🇻", False),
    ("et", "Eesti", "🇪🇪", False),
    ("az", "Azərbaycan", "🇦🇿", False),
    ("ka", "ქართული", "🇬🇪", False),
    ("am", "አማርኛ", "🇪🇹", False),
    ("sw", "Kiswahili", "🇹🇿", False),
    ("af", "Afrikaans", "🇿🇦", False),
    ("kk", "Қазақша", "��🇿", False),
    ("uz", "O'zbek", "🇺🇿", False),
    ("ky", "Кыргызча", "🇰🇬", False),
    ("tg", "Тоҷикӣ", "🇹🇯", False),
    ("mn", "Монгол", "🇲🇳", False),
    ("my", "မြန်မာ", "🇲🇲", False),
]


def init_db():
    _create_engine()
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _create_indexes()
    _seed_defaults()
    _seed_languages()
    logger.info("Database initialized successfully")


def _run_migrations():
    stmts = [
        "ALTER TABLE webapp_buttons ADD COLUMN IF NOT EXISTS placement VARCHAR(30) NOT NULL DEFAULT 'inline'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS download_count INTEGER DEFAULT 0",
        "ALTER TABLE subscription_channels ADD COLUMN IF NOT EXISTS subscriber_limit INTEGER",
        "ALTER TABLE background_jobs ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(255)",
        "ALTER TABLE scheduled_posts ADD COLUMN IF NOT EXISTS queued_at TIMESTAMP",
        "ALTER TABLE scheduled_posts ADD COLUMN IF NOT EXISTS last_job_id INTEGER",
        "ALTER TABLE scheduled_posts ADD COLUMN IF NOT EXISTS last_error TEXT",
        "ALTER TABLE broadcast_logs ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending'",
        "ALTER TABLE broadcast_logs ADD COLUMN IF NOT EXISTS last_job_id INTEGER",
        "ALTER TABLE broadcast_logs ADD COLUMN IF NOT EXISTS error_message TEXT",
    ]
    try:
        with engine.connect() as conn:
            for stmt in stmts:
                try:
                    conn.execute(text(stmt))
                except Exception:
                    pass
            conn.commit()
    except Exception as e:
        logger.warning(f"Migration warning (safe to ignore): {e}")


def _create_indexes():
    index_cmds = [
        "CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)",
        "CREATE INDEX IF NOT EXISTS idx_users_joined_at ON users(joined_at)",
        "CREATE INDEX IF NOT EXISTS idx_sub_channels_is_backup ON subscription_channels(is_backup)",
        "CREATE INDEX IF NOT EXISTS idx_sub_channels_is_active ON subscription_channels(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_sub_channels_chat_id ON subscription_channels(chat_id)",
        "CREATE INDEX IF NOT EXISTS idx_bot_settings_key ON bot_settings(key)",
        "CREATE INDEX IF NOT EXISTS idx_admin_users_telegram_id ON admin_users(telegram_id)",
        "CREATE INDEX IF NOT EXISTS idx_admin_users_is_active ON admin_users(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_background_jobs_status_available ON background_jobs(status, available_at)",
        "CREATE INDEX IF NOT EXISTS idx_background_jobs_ready_claim ON background_jobs(status, available_at, priority DESC, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_background_jobs_status_created ON background_jobs(status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_background_jobs_processing_locked ON background_jobs(status, locked_at)",
        "CREATE INDEX IF NOT EXISTS idx_background_jobs_celery_task_id ON background_jobs(celery_task_id)",
        "CREATE INDEX IF NOT EXISTS idx_scheduled_posts_due_queue ON scheduled_posts(is_active, is_sent, scheduled_at, queued_at)",
        "CREATE INDEX IF NOT EXISTS idx_broadcast_logs_status_started ON broadcast_logs(status, started_at)",
        "CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_last_seen ON worker_heartbeats(last_seen)",
        "CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_status_last_seen ON worker_heartbeats(status, last_seen)",
        "CREATE INDEX IF NOT EXISTS idx_users_status_id ON users(status, id)",
    ]
    try:
        with engine.connect() as conn:
            for cmd in index_cmds:
                try:
                    conn.execute(text(cmd))
                except Exception:
                    pass
            conn.commit()
        logger.info("Database indexes created/verified.")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")


@contextmanager
def session_scope() -> Session:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Session:
    return SessionLocal()


def _seed_defaults():
    db = SessionLocal()
    try:
        default_settings = [
            ("subscription_enabled", "true"),
            ("bot_name", "SaveEliteBot"),
            ("start_message", "مرحبا بك يا {name} 👋\n\nيمكنني تنزيل الوسائط من منصات متعددة بحسب تفعيل الإدارة.\nأرسل الرابط للبدء."),
            ("subscription_message", "لإستخدام البوت يرجى الإشتراك في القنوات التالية\n📢 اشترك في القنوات التالية"),
            ("help_message", "🤖 يمكنني تنزيل الوسائط من عدة منصات مدعومة بحسب إعدادات الإدارة.\n\nكيفية التنزيل:\n1. انسخ رابط المنشور أو الملف العام.\n2. أرسل الرابط هنا مباشرة.\n3. سيضع البوت الطلب في قائمة المعالجة ويرسل النتيجة عند اكتمالها."),
            ("downloading_message", "⏰┇تم استلام طلبك وسيتم معالجته الآن..."),
            ("unsupported_message", "⚠️ الرابط غير مدعوم حالياً. يرجى إرسال رابط من منصة مدعومة ومفعّلة."),
            ("error_message", "❌ حدث خطأ أثناء التحميل. يرجى المحاولة مجدداً."),
            ("video_caption", "📥 تم التحميل بنجاح\n\n🤖 @{bot_name}"),
            ("photo_caption", "🖼 تم التحميل بنجاح\n\n🤖 @{bot_name}"),
            ("audio_caption", "🎵 تم التحميل بنجاح\n\n🤖 @{bot_name}"),
            ("document_caption", "📁 تم التحميل بنجاح\n\n🤖 @{bot_name}"),
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
            ("google_drive_enabled", "false"),
            ("linkedin_enabled", "false"),
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
            ("google_drive_disabled_msg", "عذراً، Google Drive غير مفعل حالياً."),
            ("linkedin_disabled_msg", "عذراً، LinkedIn غير مفعل حالياً."),
            ("vimeo_disabled_msg", "عذراً، Vimeo غير مفعل حالياً."),
            ("dailymotion_disabled_msg", "عذراً، Dailymotion غير مفعل حالياً."),
            ("disabled_platform_generic_msg", "عذراً، هذه المنصة غير مفعلة حالياً في البوت."),
            ("unsupported_platform_msg", "⚠️ هذه المنصة غير مدعومة حالياً. يرجى إرسال رابط من منصة مدعومة."),
            ("rate_limit_message", "⚠️ الضغط مرتفع حالياً. يرجى الانتظار {seconds} ثانية قبل إرسال طلب جديد."),
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
    cached = _cache_get(key)
    if cached is not None:
        return cached
    db = SessionLocal()
    try:
        setting = db.query(BotSettings).filter_by(key=key).first()
        val = setting.value if setting else default
        _cache_set(key, val)
        return val
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
        _cache_set(key, value)
    except Exception as e:
        db.rollback()
        _cache_invalidate(key)
        logger.error(f"Error setting {key}: {e}")
    finally:
        db.close()

from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime, Text,
    ForeignKey, Float, JSON, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    BANNED = "banned"
    INACTIVE = "inactive"


class AdminPermission(str, enum.Enum):
    MANAGE_USERS = "manage_users"
    MANAGE_SUBSCRIPTION = "manage_subscription"
    MANAGE_CHANNELS = "manage_channels"
    MANAGE_BROADCAST = "manage_broadcast"
    MANAGE_SCHEDULED = "manage_scheduled"
    MANAGE_GROUPS = "manage_groups"
    MANAGE_ANTIFLOOD = "manage_antiflood"
    VIEW_STATS = "view_stats"
    MANAGE_SETTINGS = "manage_settings"
    ADD_ADMINS = "add_admins"
    DELETE_ADMINS = "delete_admins"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRY = "retry"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    language_code = Column(String(10), default="ar")
    status = Column(SAEnum(UserStatus), default=UserStatus.ACTIVE)
    is_admin = Column(Boolean, default=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    download_count = Column(Integer, default=0)
    tiktok_count = Column(Integer, default=0)
    youtube_count = Column(Integer, default=0)
    instagram_count = Column(Integer, default=0)
    likee_count = Column(Integer, default=0)

    downloads = relationship("Download", back_populates="user")


class Download(Base):
    __tablename__ = "downloads"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String(50), nullable=False)
    url = Column(Text, nullable=False)
    media_type = Column(String(20), default="video")
    downloaded_at = Column(DateTime(timezone=True), server_default=func.now())
    success = Column(Boolean, default=True)

    user = relationship("User", back_populates="downloads")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(Integer, primary_key=True)
    job_type = Column(String(50), nullable=False, index=True)
    status = Column(SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    worker_name = Column(String(100), nullable=True)
    celery_task_id = Column(String(255), nullable=True, index=True)
    available_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    id = Column(Integer, primary_key=True)
    worker_name = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(50), nullable=False, default="starting")
    active_task_id = Column(String(255), nullable=True)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_started_at = Column(DateTime(timezone=True), nullable=True)
    last_completed_at = Column(DateTime(timezone=True), nullable=True)


class SubscriptionChannel(Base):
    __tablename__ = "subscription_channels"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    username = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    invite_link = Column(String(500), nullable=True)
    chat_type = Column(String(20), default="channel")
    is_backup = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    subscriber_limit = Column(Integer, nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())


class PublishChannel(Base):
    __tablename__ = "publish_channels"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    username = Column(String(255), nullable=True)
    title = Column(String(255), nullable=True)
    chat_type = Column(String(20), default="channel")
    group_id = Column(Integer, ForeignKey("channel_groups.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    post_count = Column(Integer, default=0)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("ChannelGroup", back_populates="channels")


class ChannelGroup(Base):
    __tablename__ = "channel_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    channels = relationship("PublishChannel", back_populates="group")


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    permissions = Column(JSON, default=list)
    allowed_sections = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active = Column(DateTime(timezone=True), nullable=True)
    added_by = Column(BigInteger, nullable=True)

    activity_logs = relationship("AdminActivityLog", back_populates="admin")


class AdminActivityLog(Base):
    __tablename__ = "admin_activity_logs"

    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False)
    action = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now())

    admin = relationship("AdminUser", back_populates="activity_logs")


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=True)
    media_type = Column(String(20), nullable=True)
    media_file_id = Column(String(500), nullable=True)
    buttons_json = Column(JSON, nullable=True)
    channel_ids = Column(JSON, default=list)
    group_id = Column(Integer, nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    repeat_type = Column(String(20), default="once")
    auto_delete_seconds = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    fail_count = Column(Integer, default=0)


class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"

    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=True)
    target_type = Column(String(20), nullable=False)
    total_sent = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    sent_by = Column(BigInteger, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(255), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SavedAd(Base):
    __tablename__ = "saved_ads"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=True)
    text = Column(Text, nullable=True)
    media_type = Column(String(20), nullable=True)
    media_file_id = Column(String(500), nullable=True)
    buttons_json = Column(JSON, nullable=True)
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    send_count = Column(Integer, default=0)


class AntiFloodSettings(Base):
    __tablename__ = "antiflood_settings"

    id = Column(Integer, primary_key=True)
    messages_per_minute = Column(Integer, default=20)
    delay_between_messages = Column(Float, default=1.0)
    retry_count = Column(Integer, default=3)
    ignore_inactive = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BotButton(Base):
    """Dynamic buttons managed via admin panel"""
    __tablename__ = "bot_buttons"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    button_type = Column(String(20), nullable=False, default="url")
    label = Column(String(255), nullable=False)
    data = Column(Text, nullable=True)
    location = Column(String(50), nullable=False, default="start")
    position = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WebAppButton(Base):
    """Web App buttons (Mini Apps) with placement support"""
    __tablename__ = "webapp_buttons"

    id = Column(Integer, primary_key=True)
    label = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    placement = Column(String(30), nullable=False, default="inline")
    location = Column(String(50), nullable=False, default="start")
    position = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BotLanguage(Base):
    """Available bot languages — admin enables/disables which appear in /lang"""
    __tablename__ = "bot_languages"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    flag = Column(String(10), nullable=False)
    is_enabled = Column(Boolean, default=False)
    is_builtin = Column(Boolean, default=False)
    position = Column(Integer, default=0)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

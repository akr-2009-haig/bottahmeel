import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import user_handler


def _settings_side_effect(values: dict[str, str]):
    def _get_setting(key: str, default: str = "") -> str:
        return values.get(key, default)
    return _get_setting


def _db_with_user(db_user):
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = db_user
    return db


class UserFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_handler_shows_youtube_preview_with_expected_buttons(self):
        db_user = SimpleNamespace(id=11, status=user_handler.UserStatus.ACTIVE, language_code="ar", is_admin=False)
        db = _db_with_user(db_user)
        message = SimpleNamespace(
            text="https://youtu.be/demo123",
            reply_photo=AsyncMock(),
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=99, username="tester", first_name="Test", last_name="", language_code="ar"),
            effective_chat=SimpleNamespace(id=500),
        )
        context = SimpleNamespace(
            bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="UnitBot"))),
            user_data={},
            bot_data={},
        )

        with (
            patch.object(user_handler, "SessionLocal", return_value=db),
            patch.object(user_handler, "get_setting", side_effect=_settings_side_effect({
                "subscription_enabled": "false",
                "bot_name": "SaveEliteBot",
                "youtube_enabled": "true",
            })),
            patch.object(user_handler, "get_reply_button_response", return_value=None),
            patch.object(user_handler, "check_download_rate_limit", return_value=(True, 0)),
            patch.object(user_handler, "extract_media_info", new=AsyncMock(return_value={
                "ok": True,
                "title": "شيلة على هونك - ابو حمزة الحنفاشي",
                "channel": "قناة ايمن Ayman للإنتاج الفني - Topic",
                "duration": 185,
                "view_count": 28600,
                "thumbnail": "https://example.com/thumb.jpg",
                "filesize": 0,
            })),
        ):
            await user_handler.message_handler(update, context)

        message.reply_photo.assert_awaited_once()
        kwargs = message.reply_photo.await_args.kwargs
        self.assertEqual(kwargs["photo"], "https://example.com/thumb.jpg")
        self.assertIn("🎥 شيلة على هونك - ابو حمزة الحنفاشي", kwargs["caption"])
        self.assertIn("👤 قناة ايمن Ayman للإنتاج الفني - Topic", kwargs["caption"])
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].text, "🎬 : مقطع فيديو")
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[1][0].text, "🔊 : بصمة صوتية")
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[1][1].text, "🎶 : ملف صوتي")
        self.assertEqual(len(context.user_data["pending_downloads"]), 1)
        db.close.assert_called_once()

    async def test_message_handler_shows_instagram_profile_menu(self):
        db_user = SimpleNamespace(id=12, status=user_handler.UserStatus.ACTIVE, language_code="ar", is_admin=False)
        db = _db_with_user(db_user)
        message = SimpleNamespace(
            text="https://www.instagram.com/film4.vibes/",
            reply_photo=AsyncMock(),
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=55, username="tester", first_name="Test", last_name="", language_code="ar"),
            effective_chat=SimpleNamespace(id=600),
        )
        context = SimpleNamespace(
            bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="UnitBot"))),
            user_data={},
            bot_data={},
        )

        with (
            patch.object(user_handler, "SessionLocal", return_value=db),
            patch.object(user_handler, "get_setting", side_effect=_settings_side_effect({
                "subscription_enabled": "false",
                "instagram_enabled": "true",
            })),
            patch.object(user_handler, "get_reply_button_response", return_value=None),
            patch.object(user_handler, "check_download_rate_limit", return_value=(True, 0)),
            patch.object(user_handler, "extract_media_info", new=AsyncMock(return_value={
                "ok": True,
                "username": "film4.vibes",
                "display_name": "",
                "post_count": 0,
                "followers": 0,
                "following": 0,
                "bio": ".",
            })),
        ):
            await user_handler.message_handler(update, context)

        message.reply_text.assert_awaited_once()
        args = message.reply_text.await_args.args
        kwargs = message.reply_text.await_args.kwargs
        self.assertIn("➘ : نتيجة البحث 🔍.", args[0])
        self.assertIn("➘ : حساب المستخدم: film4.vibes،", args[0])
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].text, "📸 : معلومات المستخدم")
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[1][0].text, "🔥 : الستوريات")
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[1][1].text, "❄️ : الهايلات")
        db.close.assert_called_once()

    async def test_callback_handler_enqueues_youtube_audio_selection(self):
        db_user = SimpleNamespace(id=13, status=user_handler.UserStatus.ACTIVE, language_code="ar", is_admin=False)
        db = _db_with_user(db_user)
        wait_msg = SimpleNamespace(message_id=77, edit_text=AsyncMock())
        query = SimpleNamespace(
            data="ytdl:abc12345:audio",
            from_user=SimpleNamespace(id=42),
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=700, reply_text=AsyncMock(return_value=wait_msg)),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(
            user_data={"pending_downloads": {"abc12345": {"url": "https://youtu.be/demo123", "caption_override": "@UnitBot"}}},
            bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(username="UnitBot"))),
            bot_data={},
        )

        with (
            patch.object(user_handler, "SessionLocal", return_value=db),
            patch.object(user_handler, "get_setting", side_effect=_settings_side_effect({})),
            patch.object(user_handler.DownloadService, "enqueue_download", return_value=321) as enqueue_download,
        ):
            await user_handler.callback_handler(update, context)

        enqueue_download.assert_called_once_with(
            user_id=13,
            chat_id=700,
            url="https://youtu.be/demo123",
            platform="youtube",
            lang="ar",
            status_message_id=77,
            download_mode="audio",
            caption_override="@UnitBot",
        )
        wait_msg.edit_text.assert_not_awaited()
        db.close.assert_called_once()

    async def test_callback_handler_sends_instagram_profile_card(self):
        db_user = SimpleNamespace(id=14, status=user_handler.UserStatus.ACTIVE, language_code="ar", is_admin=False)
        db = _db_with_user(db_user)
        query = SimpleNamespace(
            data="igpf:ig123456:info",
            from_user=SimpleNamespace(id=43),
            answer=AsyncMock(),
            message=SimpleNamespace(chat_id=701, reply_text=AsyncMock()),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(
            user_data={"pending_downloads": {"ig123456": {"info": {
                "username": "Film4.vibes",
                "display_name": "",
                "post_count": 0,
                "followers": 0,
                "following": 0,
                "bio": ".",
            }}}},
            bot=SimpleNamespace(send_photo=AsyncMock()),
            bot_data={},
        )

        with (
            patch.object(user_handler, "SessionLocal", return_value=db),
            patch.object(user_handler, "get_setting", side_effect=_settings_side_effect({})),
        ):
            await user_handler.callback_handler(update, context)

        context.bot.send_photo.assert_awaited_once()
        kwargs = context.bot.send_photo.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], 701)
        self.assertIn("⌁︙معلومات المستخدم 📸.", kwargs["caption"])
        self.assertIn("⌁︙حساب المستخدم: Film4.vibes،", kwargs["caption"])
        db.close.assert_called_once()

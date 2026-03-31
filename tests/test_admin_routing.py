import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.admin import admin_handler, ui_handler
from bot.app import bootstrap
from bot.handlers import user_handler


class AdminRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_combined_callback_routes_sub3_callbacks_to_admin_handler(self):
        update = SimpleNamespace(
            callback_query=SimpleNamespace(data="sub3_main", from_user=SimpleNamespace(id=1))
        )
        context = SimpleNamespace()
        db = MagicMock()

        with (
            patch.object(bootstrap, "SessionLocal", return_value=db),
            patch.object(bootstrap, "is_admin", return_value=True),
            patch.object(bootstrap, "admin_callback", new=AsyncMock()) as admin_callback,
            patch.object(bootstrap, "callback_handler", new=AsyncMock()) as callback_handler,
        ):
            await bootstrap.combined_callback_handler(update, context)

        admin_callback.assert_awaited_once_with(update, context)
        callback_handler.assert_not_awaited()
        db.close.assert_called_once()

    async def test_combined_callback_routes_user_info_callbacks_to_admin_handler(self):
        update = SimpleNamespace(
            callback_query=SimpleNamespace(data="user_info_42", from_user=SimpleNamespace(id=1))
        )
        context = SimpleNamespace()
        db = MagicMock()

        with (
            patch.object(bootstrap, "SessionLocal", return_value=db),
            patch.object(bootstrap, "is_admin", return_value=True),
            patch.object(bootstrap, "admin_callback", new=AsyncMock()) as admin_callback,
            patch.object(bootstrap, "callback_handler", new=AsyncMock()) as callback_handler,
        ):
            await bootstrap.combined_callback_handler(update, context)

        admin_callback.assert_awaited_once_with(update, context)
        callback_handler.assert_not_awaited()
        db.close.assert_called_once()

    async def test_combined_callback_routes_admins_namespace_callbacks_to_admin_handler(self):
        update = SimpleNamespace(
            callback_query=SimpleNamespace(data="admins_add_menu", from_user=SimpleNamespace(id=1))
        )
        context = SimpleNamespace()
        db = MagicMock()

        with (
            patch.object(bootstrap, "SessionLocal", return_value=db),
            patch.object(bootstrap, "is_admin", return_value=True),
            patch.object(bootstrap, "admin_callback", new=AsyncMock()) as admin_callback,
            patch.object(bootstrap, "callback_handler", new=AsyncMock()) as callback_handler,
        ):
            await bootstrap.combined_callback_handler(update, context)

        admin_callback.assert_awaited_once_with(update, context)
        callback_handler.assert_not_awaited()
        db.close.assert_called_once()

    async def test_combined_callback_routes_edit_message_callbacks_to_admin_handler(self):
        update = SimpleNamespace(
            callback_query=SimpleNamespace(data="edit_msg_help", from_user=SimpleNamespace(id=1))
        )
        context = SimpleNamespace()
        db = MagicMock()

        with (
            patch.object(bootstrap, "SessionLocal", return_value=db),
            patch.object(bootstrap, "is_admin", return_value=True),
            patch.object(bootstrap, "admin_callback", new=AsyncMock()) as admin_callback,
            patch.object(bootstrap, "callback_handler", new=AsyncMock()) as callback_handler,
        ):
            await bootstrap.combined_callback_handler(update, context)

        admin_callback.assert_awaited_once_with(update, context)
        callback_handler.assert_not_awaited()
        db.close.assert_called_once()

    async def test_combined_message_routes_sub3_waiting_messages_to_admin_handler(self):
        update = SimpleNamespace(
            message=SimpleNamespace(text="https://t.me/example"),
            effective_user=SimpleNamespace(id=1),
        )
        context = SimpleNamespace(user_data={"waiting_for": "sub3_input_link"})
        db = MagicMock()

        with (
            patch.object(bootstrap, "SessionLocal", return_value=db),
            patch.object(bootstrap, "is_admin", return_value=True),
            patch.object(bootstrap, "admin_message_handler", new=AsyncMock()) as admin_message_handler,
            patch.object(bootstrap, "message_handler", new=AsyncMock()) as message_handler,
        ):
            await bootstrap.combined_message_handler(update, context)

        admin_message_handler.assert_awaited_once_with(update, context)
        message_handler.assert_not_awaited()
        db.close.assert_called_once()

    async def test_combined_message_routes_admin_media_waiting_messages_to_admin_handler(self):
        update = SimpleNamespace(
            message=SimpleNamespace(text=None, photo=[SimpleNamespace(file_id="photo-file")]),
            effective_user=SimpleNamespace(id=1),
        )
        context = SimpleNamespace(user_data={"waiting_for": "bc_media_photo_users"})
        db = MagicMock()

        with (
            patch.object(bootstrap, "SessionLocal", return_value=db),
            patch.object(bootstrap, "is_admin", return_value=True),
            patch.object(bootstrap, "admin_message_handler", new=AsyncMock()) as admin_message_handler,
            patch.object(bootstrap, "message_handler", new=AsyncMock()) as message_handler,
        ):
            await bootstrap.combined_message_handler(update, context)

        admin_message_handler.assert_awaited_once_with(update, context)
        message_handler.assert_not_awaited()
        db.close.assert_called_once()

    async def test_admin_callback_opens_sub3_subscription_screen_from_main_menu(self):
        query = SimpleNamespace(
            data="adm_sub",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={})
        db = MagicMock()

        with (
            patch.object(admin_handler, "SessionLocal", return_value=db),
            patch.object(admin_handler, "is_admin", return_value=True),
            patch.object(admin_handler, "dispatch_ui_callback", new=AsyncMock(return_value=False)),
            patch.object(admin_handler, "dispatch_sub_callback", new=AsyncMock(return_value=False)),
            patch.object(admin_handler, "sub3_main", new=AsyncMock()) as sub3_main,
        ):
            await admin_handler.admin_callback(update, context)

        sub3_main.assert_awaited_once_with(query, context)
        db.close.assert_called_once()

    async def test_admin_callback_perms_save_creates_new_admin(self):
        query = SimpleNamespace(
            data="perms_save",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={"new_admin_id": 42, "selected_perms": ["manage_users"]})
        db = MagicMock()

        with (
            patch.object(admin_handler, "SessionLocal", return_value=db),
            patch.object(admin_handler, "is_admin", return_value=True),
            patch.object(admin_handler, "dispatch_ui_callback", new=AsyncMock(return_value=False)),
            patch.object(admin_handler, "dispatch_sub_callback", new=AsyncMock(return_value=False)),
        ):
            await admin_handler.admin_callback(update, context)

        self.assertEqual(db.add.call_count, 1)
        created_admin = db.add.call_args.args[0]
        self.assertEqual(created_admin.telegram_id, 42)
        self.assertEqual(created_admin.permissions, ["manage_users"])
        self.assertEqual(query.answer.await_count, 2)
        self.assertNotIn("new_admin_id", context.user_data)
        db.close.assert_called_once()

    async def test_admin_callback_sched_repeat_creates_post_with_selected_repeat_type(self):
        query = SimpleNamespace(
            data="sched_repeat_daily",
            from_user=SimpleNamespace(id=7),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={
            "sched_data": {
                "text": "hello",
                "channel_ids": [1, 2],
                "scheduled_at": datetime(2026, 3, 26, 12, 30, tzinfo=timezone.utc),
            }
        })
        db = MagicMock()

        with (
            patch.object(admin_handler, "SessionLocal", return_value=db),
            patch.object(admin_handler, "is_admin", return_value=True),
            patch.object(admin_handler, "dispatch_ui_callback", new=AsyncMock(return_value=False)),
            patch.object(admin_handler, "dispatch_sub_callback", new=AsyncMock(return_value=False)),
        ):
            await admin_handler.admin_callback(update, context)

        self.assertEqual(db.add.call_count, 1)
        post = db.add.call_args.args[0]
        self.assertEqual(post.repeat_type, "daily")
        self.assertEqual(post.created_by, 7)
        self.assertNotIn("sched_data", context.user_data)
        query.edit_message_text.assert_awaited_once()
        db.close.assert_called_once()

    async def test_admin_callback_sub_enable_shows_error_when_setting_save_fails(self):
        query = SimpleNamespace(
            data="sub_enable",
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(user_data={})
        db = MagicMock()

        with (
            patch.object(admin_handler, "SessionLocal", return_value=db),
            patch.object(admin_handler, "is_admin", return_value=True),
            patch.object(admin_handler, "dispatch_ui_callback", new=AsyncMock(return_value=False)),
            patch.object(admin_handler, "dispatch_sub_callback", new=AsyncMock(return_value=False)),
            patch.object(admin_handler, "_setting_saved", return_value=False),
        ):
            await admin_handler.admin_callback(update, context)

        query.edit_message_text.assert_not_awaited()
        query.answer.assert_any_await("❌ تعذر حفظ إعداد الاشتراك الإجباري.", show_alert=True)
        db.close.assert_called_once()

    async def test_admin_message_handler_keeps_waiting_when_setting_save_fails(self):
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            message=SimpleNamespace(text="new value", reply_text=AsyncMock()),
        )
        context = SimpleNamespace(user_data={"waiting_for": "edit_setting_start_message"})
        db = MagicMock()

        with (
            patch.object(admin_handler, "SessionLocal", return_value=db),
            patch.object(admin_handler, "is_admin", return_value=True),
            patch.object(admin_handler, "_setting_saved", return_value=False),
        ):
            await admin_handler.admin_message_handler(update, context)

        update.message.reply_text.assert_awaited_once_with("❌ تعذر حفظ الإعداد. أعد المحاولة.")
        self.assertEqual(context.user_data["waiting_for"], "edit_setting_start_message")
        db.close.assert_called_once()


class AdminUiPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ui_activity_set_shows_error_when_save_fails(self):
        query = SimpleNamespace(answer=AsyncMock())
        context = SimpleNamespace(user_data={})

        with (
            patch.object(ui_handler, "_setting_saved", return_value=False),
            patch.object(ui_handler, "ui_activity_main", new=AsyncMock()) as ui_activity_main,
        ):
            await ui_handler.ui_activity_set(query, context, "typing")

        ui_activity_main.assert_not_awaited()
        query.answer.assert_awaited_once_with("❌ تعذر حفظ حالة النشاط. حاول مرة أخرى.", show_alert=True)

    async def test_ui_handle_message_keeps_waiting_when_message_save_fails(self):
        update = SimpleNamespace(message=SimpleNamespace(text="new text", reply_text=AsyncMock()))
        context = SimpleNamespace(user_data={
            "waiting_for": "ui_msg_text_start",
            "ui_msg_key": "start_message",
        })

        with patch.object(ui_handler, "_setting_saved", return_value=False):
            handled = await ui_handler.ui_handle_message(update, context)

        self.assertTrue(handled)
        update.message.reply_text.assert_awaited_once_with("❌ تعذر حفظ الرسالة. أعد المحاولة.")
        self.assertEqual(context.user_data["waiting_for"], "ui_msg_text_start")
        self.assertEqual(context.user_data["ui_msg_key"], "start_message")

    async def test_ui_handle_message_button_edit_requires_existing_button(self):
        update = SimpleNamespace(message=SimpleNamespace(text="زر جديد", reply_text=AsyncMock()))
        context = SimpleNamespace(user_data={"waiting_for": "ui_btn_new_label_5"})
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = None

        with patch.object(ui_handler, "SessionLocal", return_value=db):
            handled = await ui_handler.ui_handle_message(update, context)

        self.assertTrue(handled)
        update.message.reply_text.assert_awaited_once_with(
            "❌ الزر المطلوب لم يعد موجوداً."
        )
        self.assertNotIn("waiting_for", context.user_data)
        db.close.assert_called_once()

    async def test_ui_handle_message_button_edit_success_offers_detail_link(self):
        update = SimpleNamespace(message=SimpleNamespace(text="زر جديد", reply_text=AsyncMock()))
        context = SimpleNamespace(user_data={"waiting_for": "ui_btn_new_label_7"})
        btn = SimpleNamespace(label="قديم", name="قديم")
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = btn

        with patch.object(ui_handler, "SessionLocal", return_value=db):
            handled = await ui_handler.ui_handle_message(update, context)

        self.assertTrue(handled)
        self.assertEqual(btn.label, "زر جديد")
        self.assertEqual(btn.name, "زر جديد")
        db.commit.assert_called_once()
        kwargs = update.message.reply_text.await_args.kwargs
        self.assertEqual(kwargs["parse_mode"], "Markdown")
        markup = kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "ui_btn_detail_7")
        self.assertEqual(markup.inline_keyboard[1][0].callback_data, "adm_main")


class SubscriptionKeyboardTests(unittest.TestCase):
    def test_build_subscription_keyboard_includes_admin_buttons_and_check_action(self):
        channels = [
            SimpleNamespace(id=3, title="Main Channel", invite_link=None, username="main_channel"),
        ]
        with patch.object(user_handler, "get_setting", return_value='[{"label":"📣 قناة احتياطية","url":"https://t.me/backup"}]'):
            markup = user_handler.build_subscription_keyboard(channels, "ar")

        rows = markup.inline_keyboard
        self.assertEqual(rows[0][0].text, "📢 Main Channel")
        self.assertEqual(rows[0][0].url, "https://t.me/main_channel")
        self.assertEqual(rows[1][0].text, "📣 قناة احتياطية")
        self.assertEqual(rows[1][0].url, "https://t.me/backup")
        self.assertEqual(rows[2][0].callback_data, "check_sub")

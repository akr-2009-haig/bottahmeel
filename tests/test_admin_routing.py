import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.admin import admin_handler
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

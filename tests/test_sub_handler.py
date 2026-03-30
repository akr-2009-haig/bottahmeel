import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.admin import sub_handler


class SubHandlerDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_handles_limit_save_without_selection(self):
        query = SimpleNamespace(data="sub3_limit_save", answer=AsyncMock(), edit_message_text=AsyncMock())
        context = SimpleNamespace(user_data={})

        handled = await sub_handler.dispatch_sub_callback(query, context)

        self.assertTrue(handled)
        query.answer.assert_awaited_once_with("⚠️ لم يتم تحديد أي قيمة بعد.", show_alert=True)

    async def test_dispatch_routes_backup_delete_to_backup_list(self):
        query = SimpleNamespace(data="sub3_backup_delete", answer=AsyncMock(), edit_message_text=AsyncMock())
        context = SimpleNamespace(user_data={})

        with patch.object(sub_handler, "sub3_list", new=AsyncMock()) as sub3_list:
            handled = await sub_handler.dispatch_sub_callback(query, context)

        self.assertTrue(handled)
        sub3_list.assert_awaited_once_with(query, context, is_backup=True)

    async def test_dispatch_routes_buttons_shortcuts_to_editor(self):
        for action in ("sub3_btn_add", "sub3_btn_edit", "sub3_btn_delete"):
            query = SimpleNamespace(data=action, answer=AsyncMock(), edit_message_text=AsyncMock())
            context = SimpleNamespace(user_data={})
            with self.subTest(action=action):
                with patch.object(sub_handler, "_render_btns_editor", new=AsyncMock()) as render:
                    handled = await sub_handler.dispatch_sub_callback(query, context)
                self.assertTrue(handled)
                render.assert_awaited_once_with(query, context, is_reply=False)


if __name__ == "__main__":
    unittest.main()

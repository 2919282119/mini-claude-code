import unittest
from unittest import mock

from tools.Tool import Tool
from tools import check_permission, clear_remembered
from tools.setup import tools_setup


class TestPermission(unittest.TestCase):

    def setUp(self):
        clear_remembered()

    def make_tool(self, permission_level):
        return Tool(
            name="t",
            description="d",
            parameters={},
            function=lambda: "ok",
            permission_level=permission_level,
        )

    def test_read_auto_allowed(self):
        self.assertTrue(check_permission(self.make_tool("READ"), {}))

    def test_write_requires_approval(self):
        with mock.patch("builtins.input", return_value="y"):
            self.assertTrue(check_permission(self.make_tool("WRITE"), {}))

    def test_execute_denied(self):
        with mock.patch("builtins.input", return_value="n"):
            self.assertFalse(check_permission(self.make_tool("EXECUTE"), {}))

    def test_remember_choice(self):
        tool = self.make_tool("EXECUTE")
        args = {"command": "ls"}
        with mock.patch("builtins.input", return_value="a"):
            self.assertTrue(check_permission(tool, args))
        # 记住后不再询问，即使 input 会拒绝也不影响
        with mock.patch("builtins.input", return_value="n"):
            self.assertTrue(check_permission(tool, args))

    def test_different_args_not_remembered(self):
        tool = self.make_tool("EXECUTE")
        with mock.patch("builtins.input", return_value="a"):
            self.assertTrue(check_permission(tool, {"command": "ls"}))
        with mock.patch("builtins.input", return_value="n"):
            self.assertFalse(check_permission(tool, {"command": "rm -rf /"}))


class TestToolPermissionLevels(unittest.TestCase):

    def test_dangerous_tools_marked(self):
        registry = tools_setup()
        levels = {t.name: t.permission_level for t in registry.all()}

        self.assertEqual(levels["bash"], "EXECUTE")
        self.assertEqual(levels["write_file"], "WRITE")
        self.assertEqual(levels["edit_file"], "WRITE")
        # 读类工具默认 READ
        self.assertEqual(levels["read_file"], "READ")
        self.assertEqual(levels["list_dir"], "READ")
        self.assertEqual(levels["grep"], "READ")


if __name__ == "__main__":
    unittest.main()

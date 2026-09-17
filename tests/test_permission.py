import unittest
from unittest import mock

from llm.model import DEFAULT_MODEL
from tools.Tool import Tool
from tools.permission import check_permission, clear_remembered
from tools.setup import tools_setup


class TestPermission(unittest.TestCase):

    def setUp(self):
        clear_remembered()

    def make_tool(self, permission_level, name="t"):
        return Tool(
            name=name,
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

    def test_remember_is_per_tool(self):
        # 记忆以工具名为粒度：同一工具记住后不再询问（参数无关），另一工具仍需询问
        tool_a = self.make_tool("EXECUTE", name="a")
        tool_b = self.make_tool("EXECUTE", name="b")

        with mock.patch("builtins.input", return_value="a"):
            self.assertTrue(check_permission(tool_a, {"command": "ls"}))

        with mock.patch("builtins.input", return_value="n"):
            self.assertTrue(check_permission(tool_a, {"command": "rm -rf /"}))

        with mock.patch("builtins.input", return_value="n"):
            self.assertFalse(check_permission(tool_b, {"command": "ls"}))


class TestToolPermissionLevels(unittest.TestCase):

    def test_dangerous_tools_marked(self):
        # 只检查本地工具；不连接真实的 MCP 服务器（隔离用户配置）
        with mock.patch("tools.setup.load_mcp_tools", return_value=[]):
            registry = tools_setup(DEFAULT_MODEL, ".")

        levels = {t.name: t.permission_level for t in registry.all()}

        self.assertEqual(levels["bash"], "EXECUTE")
        self.assertEqual(levels["run_subagent"], "EXECUTE")
        self.assertEqual(levels["write_file"], "WRITE")
        self.assertEqual(levels["edit_file"], "WRITE")
        # 读类工具默认 READ
        self.assertEqual(levels["read_file"], "READ")
        self.assertEqual(levels["list_dir"], "READ")
        self.assertEqual(levels["grep"], "READ")


if __name__ == "__main__":
    unittest.main()

"""save_memory 工具的测试。

覆盖三层：工具函数本身（写入 / 重复 / 空内容）、注册接线（tools_setup 传入
memory_manager 才注册）、子 Agent 排除（create_subagent_registry 剔除）。
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.memory import MemoryManager
from agent.system_prompt import SYSTEM_PROMPT
from tools.Tool import Tool
from tools.local.usual.run_subagent import create_subagent_registry
from tools.local.usual.save_memory import create_save_memory_tool
from tools.setup import tools_setup
from tools.tool_registry import ToolRegistry


def _stub_tool(name):
    return Tool(
        name=name,
        description="测试工具",
        parameters={"type": "object", "properties": {}},
        function=lambda: None,
    )


class MemoryToolTestCase(unittest.TestCase):
    def make_manager(self):
        """真实 MemoryManager，但 Path.home 指向临时目录，不碰真实 ~/.miniCC。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        with mock.patch("agent.memory.Path.home", return_value=Path(tmp.name)):
            return MemoryManager()


class TestSaveMemoryTool(MemoryToolTestCase):

    def test_saves_content(self):
        manager = self.make_manager()
        tool = create_save_memory_tool(manager)

        result = tool.execute(content="用户偏好中文交流")

        self.assertEqual(result, {"saved": True})
        memories = manager.get_all()
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["content"], "用户偏好中文交流")

    def test_duplicate_is_not_saved(self):
        manager = self.make_manager()
        tool = create_save_memory_tool(manager)

        tool.execute(content="用户偏好中文交流")
        result = tool.execute(content="用户偏好中文交流")

        self.assertFalse(result["saved"])
        self.assertEqual(len(manager.get_all()), 1)

    def test_blank_content_is_rejected(self):
        manager = self.make_manager()
        tool = create_save_memory_tool(manager)

        result = tool.execute(content="   ")

        self.assertFalse(result["saved"])
        self.assertEqual(manager.get_all(), [])

    def test_permission_level_is_read(self):
        """静默写入：READ 级不触发权限询问（这是有意选择，不是漏配）。"""
        tool = create_save_memory_tool(self.make_manager())
        self.assertEqual(tool.permission_level, "READ")


class TestWiring(MemoryToolTestCase):

    def test_tools_setup_registers_tool_for_main_agent(self):
        manager = self.make_manager()
        registry = tools_setup(memory_manager=manager)

        tool = registry.get("save_memory")
        self.assertIsNotNone(tool)

        # 端到端：注册后的工具写进的是同一份 manager
        tool.execute(content="项目测试用 unittest")
        self.assertEqual(len(manager.get_all()), 1)

    def test_tools_setup_without_manager_does_not_register(self):
        registry = tools_setup()
        self.assertIsNone(registry.get("save_memory"))

    def test_subagent_registry_excludes_save_memory(self):
        registry = ToolRegistry()
        registry.register(create_save_memory_tool(self.make_manager()))
        registry.register(_stub_tool("run_subagent"))
        registry.register(_stub_tool("read_file"))

        names = {tool.name for tool in create_subagent_registry(registry).all()}

        self.assertNotIn("save_memory", names)
        self.assertNotIn("run_subagent", names)
        self.assertIn("read_file", names)

    def test_system_prompt_lists_save_memory(self):
        self.assertIn("save_memory", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()

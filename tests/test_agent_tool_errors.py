import json
import unittest
from unittest import mock

from agent.agent import agent_loop
from agent.session import AgentState
from llm.model import DEFAULT_MODEL
from tools.setup import tools_setup


def make_response(content, tool_calls=None):
    message = mock.MagicMock()
    message.content = content
    message.tool_calls = tool_calls or []
    message.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": [],
    }

    choice = mock.MagicMock()
    choice.message = message

    response = mock.MagicMock()
    response.choices = [choice]

    return response


def make_tool_call(call_id, name, arguments):
    tool_call = mock.MagicMock()
    tool_call.id = call_id
    tool_call.function.name = name
    tool_call.function.arguments = arguments
    return tool_call


class TestToolErrorHandling(unittest.TestCase):
    """回归：LLM 生成的工具参数出错时不能崩掉整个 agent"""

    def setUp(self):
        # 测试只关心本地工具；不连接真实的 MCP 服务器（隔离用户配置）
        with mock.patch("tools.setup.load_mcp_tools", return_value=[]):
            self.registry = tools_setup(DEFAULT_MODEL, ".")

        self.context_manager = mock.MagicMock()
        self.memory_manager = mock.MagicMock()
        self.memory_manager.format_for_prompt.return_value = ""

    def run_agent(self, responses):
        state = AgentState("s1", [{"role": "user", "content": "hi"}], ".")
        # 权限检查有独立测试，这里直接放行以聚焦工具错误处理
        with mock.patch("agent.agent.call_llm", side_effect=responses), \
                mock.patch("agent.agent.check_permission", return_value=True):
            answer = agent_loop(
                state, self.registry, self.context_manager, self.memory_manager
            )
        return state, answer

    def test_missing_argument_does_not_crash(self):
        """edit_file 缺 path 参数：错误回填给 LLM，agent 继续运行"""
        bad_call = make_tool_call(
            "call_1",
            "edit_file",
            json.dumps({"old_text": "a", "new_text": "b"}),  # 缺 path
        )

        state, answer = self.run_agent([
            make_response(None, [bad_call]),
            make_response("已纠正"),
        ])

        self.assertEqual(answer, "已纠正")

        tool_messages = [m for m in state.messages if m.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("error", json.loads(tool_messages[0]["content"]))
        self.assertIn("path", tool_messages[0]["content"])

    def test_invalid_json_arguments_does_not_crash(self):
        """参数 JSON 非法：错误回填给 LLM，agent 继续运行"""
        bad_call = make_tool_call("call_2", "edit_file", '{"path": "a.py"')

        state, answer = self.run_agent([
            make_response(None, [bad_call]),
            make_response("没关系"),
        ])

        self.assertEqual(answer, "没关系")

        tool_messages = [m for m in state.messages if m.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("JSON", tool_messages[0]["content"])


if __name__ == "__main__":
    unittest.main()

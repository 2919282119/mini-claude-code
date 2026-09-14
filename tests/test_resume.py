import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager
from commands.handle_command import handle_command


class TestResumeKeepsMessagesRef(unittest.TestCase):
    """回归：/resume 重绑定 state.messages 会导致后续 user prompt 加不进去"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.session_manager = SessionManager()
        self.session_manager.session_dir = Path(self._tmp.name)
        self.context_manager = ContextManager(100000)
        self.memory_manager = MemoryManager()

    def tearDown(self):
        self._tmp.cleanup()

    def test_user_prompt_after_resume_goes_into_state_messages(self):
        old_messages = [
            {"role": "user", "content": "旧问题"},
            {"role": "assistant", "content": "旧回答"},
        ]
        self.session_manager.save(
            AgentState(
                session_id="old-session",
                messages=old_messages,
                cwd=str(Path.cwd()),
                name="oldsession",
            )
        )

        # 模拟 main.py：本地 messages 与 state.messages 是同一个 list
        messages = []
        state = AgentState("new-session", messages, str(Path.cwd()))

        handle_command(
            "/resume oldsession",
            state,
            self.session_manager,
            self.context_manager,
            self.memory_manager,
        )

        # 恢复历史后 list 身份必须保持不变
        self.assertIs(messages, state.messages)
        self.assertEqual(state.messages, old_messages)

        # main.py 追加用户输入后，state.messages 必须能看到
        messages.append({"role": "user", "content": "新问题"})
        self.assertEqual(
            state.messages[-1],
            {"role": "user", "content": "新问题"},
        )


class TestCompactKeepsMessagesRef(unittest.TestCase):
    """回归：compact 重绑定 state.messages 会导致 agent loop 里的引用分叉"""

    def test_compact_mutates_in_place(self):
        messages = [
            {"role": "user", "content": f"msg-{i}"}
            for i in range(12)
        ]
        state = AgentState("s1", messages, str(Path.cwd()))
        context_manager = ContextManager(100000)

        response = mock.MagicMock()
        response.usage.prompt_tokens = 123
        response.choices[0].message.content = "摘要"

        with mock.patch("agent.context.call_llm", return_value=response):
            self.assertTrue(context_manager.compact(state))

        # agent loop 里持有的 messages 引用依然指向同一个 list
        self.assertIs(messages, state.messages)
        # summary + 最近 10 条
        self.assertEqual(len(state.messages), 11)
        self.assertIn(
            "[Conversation Summary]",
            state.messages[0]["content"],
        )


if __name__ == "__main__":
    unittest.main()
"""Ctrl+C 中断 agent 循环的回归测试。

核心不变量：**assistant 消息里的每个 tool_call 都必须有恰好一条配对的 tool 回复**。
OpenAI 兼容接口对消息序列有这条硬要求，缺一个下一次请求就会被直接拒绝——所以
「中断不丢状态」的真正含义不只是保留对话，而是必须把没执行完的 tool_call 补上结果。
"""

import _thread
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from agent import agent as agent_module
from agent.agent import agent_loop
from agent.interrupt import (
    clear_interrupt,
    is_interrupted,
    request_interrupt,
)
from agent.session import AgentState
from tools.Tool import Tool
from tools.tool_registry import ToolRegistry


def assert_transcript_is_valid(test_case, messages):
    """每个 tool_call 都要有恰好一条配对的 tool 回复。"""
    for message in messages:
        for tool_call in message.get("tool_calls") or []:
            answers = [
                item
                for item in messages
                if item.get("role") == "tool"
                and item.get("tool_call_id") == tool_call["id"]
            ]

            test_case.assertEqual(
                len(answers),
                1,
                f"tool_call {tool_call['id']} 应有 1 条配对回复，实际 {len(answers)} 条",
            )


def tool_call_result_of(messages, call_id):
    """取某个 tool_call 的结果（已解析成 dict），没有则返回 None。"""
    for item in messages:
        if item.get("role") == "tool" and item.get("tool_call_id") == call_id:
            return json.loads(item["content"])
    return None


def _tool_call(call_id, name, arguments="{}"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _assistant_message(tool_calls=None, content=None):
    message = mock.Mock()
    message.content = content
    message.tool_calls = tool_calls
    message.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in (tool_calls or [])
        ],
    }
    return message


class AgentLoopInterruptTestCase(unittest.TestCase):

    def setUp(self):
        clear_interrupt()
        self.addCleanup(clear_interrupt)

    def make_registry(self, functions):
        registry = ToolRegistry()

        for name, function in functions.items():
            registry.register(
                Tool(
                    name=name,
                    description=f"测试工具 {name}",
                    parameters={"type": "object", "properties": {}},
                    function=function,
                )
            )

        return registry

    def run_loop(self, messages, registry, state=None):
        """驱动 agent_loop，call_llm 依次返回给定的 assistant 消息。"""
        state = state or AgentState(
            session_id="s1",
            messages=[{"role": "user", "content": "开始"}],
            cwd=".",
        )

        with mock.patch.object(
            agent_module,
            "call_llm",
            side_effect=[mock.Mock(choices=[mock.Mock(message=m)]) for m in messages],
        ) as self.fake_call_llm:
            result = agent_loop(state, registry, mock.Mock(), verbose=False)

        return state, result


class TestToolCallInterrupt(AgentLoopInterruptTestCase):

    def test_interrupt_midway_keeps_transcript_valid(self):
        """3 个工具、第 2 个执行时被 Ctrl+C：第 1 个的真实结果保留，剩下两个补成
        「未运行」，且转录合法——这是「不丢状态」的硬要求。"""
        executed = []

        def first():
            executed.append("first")
            return {"ok": 1}

        def second():
            executed.append("second")
            raise KeyboardInterrupt

        def third():
            executed.append("third")
            return {"ok": 3}

        registry = self.make_registry(
            {"first": first, "second": second, "third": third}
        )
        calls = [
            _tool_call("c1", "first"),
            _tool_call("c2", "second"),
            _tool_call("c3", "third"),
        ]

        state, result = self.run_loop([_assistant_message(tool_calls=calls)], registry)

        self.assertIsNone(result)
        self.assertTrue(is_interrupted())
        # 中断在那个工具上就生效了，后面的工具根本不该跑
        self.assertEqual(executed, ["first", "second"])

        assert_transcript_is_valid(self, state.messages)

        self.assertEqual(tool_call_result_of(state.messages, "c1"), {"ok": 1})
        self.assertIn("未运行", tool_call_result_of(state.messages, "c2")["error"])
        self.assertIn("未运行", tool_call_result_of(state.messages, "c3")["error"])

    def test_interrupt_delivers_promptly_while_waiting_for_the_llm(self):
        """回归：LLM 请求阻塞期间按 Ctrl+C 必须立刻生效。

        真终端实测过：不改的话，一次长回答请求里按 Ctrl+C，要 70~80 秒后才出现
        「已中断」——那正是请求自己的耗时。原因是 Windows 上 Ctrl+C 只中止**控制台
        句柄**上的阻塞读，socket 读取不在其列，待处理的 KeyboardInterrupt 得等系统
        调用返回才抛得出来。现在请求跑 worker 线程、主线程只用 Event.wait 轮询。
        """
        release = threading.Event()
        self.addCleanup(release.set)

        def slow_llm(*args, **kwargs):
            release.wait(10)  # 模拟一个很慢的请求
            return mock.Mock(
                choices=[mock.Mock(message=_assistant_message(content="迟到的答案"))]
            )

        state = AgentState(
            session_id="s1",
            messages=[{"role": "user", "content": "开始"}],
            cwd=".",
        )

        threading.Thread(
            target=lambda: (time.sleep(0.3), _thread.interrupt_main()), daemon=True
        ).start()

        with mock.patch.object(agent_module, "call_llm", side_effect=slow_llm):
            start = time.monotonic()
            result = agent_loop(state, mock.Mock(), mock.Mock(), verbose=False)
            elapsed = time.monotonic() - start

        self.assertIsNone(result)
        self.assertLess(elapsed, 2.0, "中断被阻塞的请求压住了，没有立刻生效")

    def test_flag_set_from_the_main_thread_stops_it(self):
        """子 Agent 的实况：它跑在 worker 线程里、**收不到 KeyboardInterrupt**（信号只
        投递给主线程），只能靠主线程置的进程级标志在下一个轮边界停下——验证这条路径
        真的通。

        注意这个「轮边界」的确切含义：标志是在**准备发起下一次请求之前**检查的。所以
        一个卡在 LLM 请求里的子 Agent 会把那一次请求跑完，如果返回的是工具调用，还会
        把那一轮工具也跑完，才会停。这里让 mock 返回工具调用，就是为了走到那条路径。
        """
        release = threading.Event()
        self.addCleanup(release.set)
        inside_llm = threading.Event()

        llm_calls = []

        def slow_llm(*args, **kwargs):
            llm_calls.append(1)
            inside_llm.set()
            release.wait(10)  # 模拟一次很慢的请求
            return mock.Mock(
                choices=[
                    mock.Mock(
                        message=_assistant_message(
                            tool_calls=[_tool_call("s1", "noop")]
                        )
                    )
                ]
            )

        registry = self.make_registry({"noop": lambda: {"ok": True}})
        state = AgentState(
            session_id="sub", messages=[{"role": "user", "content": "任务"}], cwd="."
        )
        outcome = {}

        def subagent_body():
            with mock.patch.object(agent_module, "call_llm", side_effect=slow_llm):
                outcome["value"] = agent_loop(state, registry, mock.Mock(), verbose=False)

        worker = threading.Thread(target=subagent_body)
        worker.start()

        self.assertTrue(inside_llm.wait(5), "子 Agent 没有进入 LLM 调用")
        request_interrupt()  # 等价于主线程收到了 Ctrl+C
        release.set()        # 放行它当前这一轮
        worker.join(5)

        self.assertFalse(worker.is_alive(), "子 Agent 卡住没返回")
        self.assertIsNone(outcome.get("value"), "子 Agent 没有在轮边界停下")
        self.assertEqual(len(llm_calls), 1, "被中断后还继续发起了请求")
        assert_transcript_is_valid(self, state.messages)

    def test_interrupt_during_llm_leaves_no_partial_message(self):
        """LLM 调用中途被中断：转录里不该留下半截 assistant 消息。"""
        state = AgentState(
            session_id="s1",
            messages=[{"role": "user", "content": "开始"}],
            cwd=".",
        )

        with mock.patch.object(agent_module, "call_llm", side_effect=KeyboardInterrupt):
            result = agent_loop(state, mock.Mock(), mock.Mock(), verbose=False)

        self.assertIsNone(result)
        self.assertTrue(is_interrupted())
        self.assertEqual(state.messages, [{"role": "user", "content": "开始"}])
        assert_transcript_is_valid(self, state.messages)

    def test_flag_stops_a_running_loop_at_the_next_boundary(self):
        """子 Agent 的场景：它收不到 KeyboardInterrupt，只能靠标志在自己的轮边界停下。"""

        def trigger():
            request_interrupt()
            return {"ok": True}

        registry = self.make_registry({"trigger": trigger})

        state, result = self.run_loop(
            [
                _assistant_message(tool_calls=[_tool_call("c1", "trigger")]),
                _assistant_message(content="这轮不该被调到"),
            ],
            registry,
        )

        self.assertIsNone(result)
        self.assertEqual(self.fake_call_llm.call_count, 1)
        assert_transcript_is_valid(self, state.messages)
        self.assertNotIn(
            "这轮不该被调到", json.dumps(state.messages, ensure_ascii=False)
        )


class TestBlockingCallsGoThroughRunInterruptibly(unittest.TestCase):
    """回归：凡是主线程里发起的阻塞网络请求，都必须走 run_interruptibly。

    不走的话，按 Ctrl+C 会被压到那次请求结束才生效——真终端实测过一次长回答请求
    里按 Ctrl+C，70~80 秒后才出现「已中断」。这里逐个钉住调用点，将来谁新加一个
    阻塞调用忘了包，至少这几处不会再退回去。
    """

    def test_compact_wraps_its_llm_call(self):
        from agent import context as context_module

        state = AgentState(
            session_id="s1",
            messages=[{"role": "user", "content": "x"}] * 12,  # >10 条才会触发压缩
            cwd=".",
        )

        with mock.patch.object(context_module, "run_interruptibly") as fake:
            fake.return_value = mock.Mock(
                usage=None,
                choices=[mock.Mock(message=mock.Mock(content="摘要"))],
            )
            self.assertTrue(context_module.ContextManager(1000).compact(state))

        self.assertIs(fake.call_args.args[0], context_module.call_llm)

    def test_btw_wraps_its_llm_call(self):
        from commands.slash import btw as btw_module

        with mock.patch.object(btw_module, "run_interruptibly") as fake:
            fake.return_value = mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content="答案"))]
            )
            btw_module.btw("问题", AgentState(session_id="s1", messages=[], cwd="."))

        self.assertIs(fake.call_args.args[0], btw_module.call_llm)

    def test_search_web_wraps_its_request(self):
        from tools.local.usual import search_web as search_web_module

        with mock.patch.object(search_web_module, "run_interruptibly") as fake:
            search_web_module.search_web("关键词")

        # 绑定方法每次访问都是新对象，比不了身份；比它绑定的实例
        self.assertIs(
            fake.call_args.args[0].__self__, search_web_module.tavily_client
        )
        self.assertEqual(fake.call_args.args[0].__name__, "search")


class TestReplInterrupt(unittest.TestCase):

    def setUp(self):
        clear_interrupt()
        self.addCleanup(clear_interrupt)

    def test_ctrl_c_at_the_prompt_does_not_exit(self):
        """提示符处按 Ctrl+C 只回到干净提示符（以前是抛裸 traceback 退出）。"""
        from main import run_repl

        state = AgentState(session_id="s1", messages=[], cwd=".")

        with mock.patch(
            "builtins.input", side_effect=[KeyboardInterrupt, "exit"]
        ) as fake_input, mock.patch("builtins.print"):
            run_repl(state, mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock())

        self.assertEqual(fake_input.call_count, 2)

    def test_interrupted_turn_prints_marker_and_saves(self):
        """中断时不能打印「🤖 None」，且要落盘——已完成的结果都在 messages 里。"""
        from main import run_repl

        state = AgentState(session_id="s1", messages=[], cwd=".")
        session_manager = mock.Mock()

        def interrupting_loop(*args, **kwargs):
            request_interrupt()
            return None

        with mock.patch("builtins.input", side_effect=["你好", "exit"]), mock.patch(
            "main.agent_loop", side_effect=interrupting_loop
        ), mock.patch("builtins.print") as fake_print:
            run_repl(state, session_manager, mock.Mock(), mock.Mock(), mock.Mock())

        printed = [call.args for call in fake_print.call_args_list]
        self.assertIn(("\n⏹ 已中断",), printed)
        self.assertFalse(
            any(args and args[0] == "\n🤖" for args in printed),
            "中断时打印了「🤖 None」",
        )
        session_manager.save.assert_called_once()

    def test_interrupt_does_not_leak_into_the_next_turn(self):
        """上一轮的中断标志必须被清掉，否则新提问会在循环开头直接被掐掉。"""
        from main import run_repl

        state = AgentState(session_id="s1", messages=[], cwd=".")
        flags_seen_by_loop = []

        def loop(*args, **kwargs):
            flags_seen_by_loop.append(is_interrupted())
            if len(flags_seen_by_loop) == 1:
                request_interrupt()
            return "答案"

        with mock.patch(
            "builtins.input", side_effect=["第一问", "第二问", "exit"]
        ), mock.patch("main.agent_loop", side_effect=loop), mock.patch("builtins.print"):
            run_repl(state, mock.Mock(), mock.Mock(), mock.Mock(), mock.Mock())

        self.assertEqual(flags_seen_by_loop, [False, False])


class TestRunSubagentInterrupt(unittest.TestCase):

    def test_interrupt_marks_unfinished_tasks(self):
        """中断时不抛出去，未拿到结果的任务标为已中断。"""
        from tools.local.usual import run_subagent as subagent_module

        def boom(*args, **kwargs):
            raise KeyboardInterrupt

        with mock.patch.object(
            subagent_module, "run_one_subagent", side_effect=boom
        ), mock.patch("builtins.print"):
            result = subagent_module.run_subagent(["t1", "t2"], ToolRegistry())

        self.assertEqual(len(result["results"]), 2)
        for item in result["results"]:
            self.assertEqual(item["error"], "已中断")

    def test_does_not_wait_for_a_running_subagent(self):
        """回归：以前用 `with ThreadPoolExecutor(...)`，退出时 shutdown(wait=True)
        会一直等到所有子 Agent 跑完，Ctrl+C 看起来就像卡死。
        线程杀不掉，但主线程不能等它。"""
        import threading

        from tools.local.usual import run_subagent as subagent_module

        # 用一个永远不主动结束、只在测试收尾时才放开的 worker 来代表「还在跑的子 Agent」
        release = threading.Event()
        self.addCleanup(release.set)

        def blocking(task, *args, **kwargs):
            if task == "卡住":
                release.wait(10)
                return {"task": task, "result": "太晚了"}
            raise KeyboardInterrupt

        with mock.patch.object(
            subagent_module, "run_one_subagent", side_effect=blocking
        ), mock.patch("builtins.print"):
            start = time.monotonic()
            result = subagent_module.run_subagent(["卡住", "炸"], ToolRegistry())
            elapsed = time.monotonic() - start

        # 若退化成 shutdown(wait=True)，这里会实打实等满 10 秒
        self.assertLess(elapsed, 0.5, "主线程等了还在跑的子 Agent")
        self.assertEqual(len(result["results"]), 2)


if __name__ == "__main__":
    unittest.main()

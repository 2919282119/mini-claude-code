import threading
import time
import unittest
from unittest import mock

from llm.model import DEFAULT_MODEL, MODELS
from tools.local.usual.run_subagent import (
    MAX_SUBAGENT_COUNT,
    SUBAGENT_SYSTEM_PROMPT,
    create_subagent_registry,
)
from tools.setup import tools_setup


def make_registry(model=DEFAULT_MODEL, cwd="."):
    # 只装配本地工具；不连接真实的 MCP 服务器（隔离用户配置）
    with mock.patch("tools.setup.load_mcp_tools", return_value=[]):
        return tools_setup(model, cwd)


class TestSubagentRegistry(unittest.TestCase):

    def test_tool_registered_as_execute(self):
        """派生时确认一次：工具本身是 EXECUTE 级"""
        tool = make_registry().get("run_subagent")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.permission_level, "EXECUTE")

    def test_subagent_cannot_spawn_subagent(self):
        sub_registry = create_subagent_registry(make_registry())

        # 子 Agent 的注册表里没有 run_subagent，从代码上禁止继续派生
        self.assertIsNone(sub_registry.get("run_subagent"))
        # 其他工具照常可用
        self.assertIsNotNone(sub_registry.get("read_file"))
        self.assertIsNotNone(sub_registry.get("bash"))


class TestRunSubagentTool(unittest.TestCase):

    def setUp(self):
        self.registry = make_registry(model="deepseek", cwd="D:\\cwd")
        self.tool = self.registry.get("run_subagent")

    def run_tool(self, fake_loop, tasks):
        """用替身 agent_loop 跑一次工具，返回（工具结果, 替身）"""
        with mock.patch(
            "tools.local.usual.run_subagent.agent_loop", side_effect=fake_loop
        ) as fake:
            return self.tool.execute(tasks=tasks), fake

    def test_tasks_run_in_parallel(self):
        """三个子任务必须真正并发：串行执行会在这里超时失败"""
        barrier = threading.Barrier(3, timeout=5)

        def fake_loop(**kwargs):
            barrier.wait()
            return "ok"

        result, _ = self.run_tool(fake_loop, ["a", "b", "c"])

        self.assertFalse(barrier.broken)
        self.assertEqual([item["result"] for item in result["results"]], ["ok"] * 3)

    def test_parallelism_capped(self):
        lock = threading.Lock()
        stats = {"cur": 0, "max": 0}
        release = threading.Event()

        def fake_loop(**kwargs):
            with lock:
                stats["cur"] += 1
                stats["max"] = max(stats["max"], stats["cur"])
            # 卡住直到主线程放行，从而观察到真实并发数
            release.wait(timeout=5)
            with lock:
                stats["cur"] -= 1
            return "ok"

        box = []
        with mock.patch(
            "tools.local.usual.run_subagent.agent_loop", side_effect=fake_loop
        ):
            worker = threading.Thread(
                target=lambda: box.append(
                    self.tool.execute(tasks=[f"t{i}" for i in range(6)])
                )
            )
            worker.start()

            deadline = time.time() + 5
            while time.time() < deadline:
                with lock:
                    if stats["cur"] == MAX_SUBAGENT_COUNT:
                        break
                time.sleep(0.01)

            release.set()
            worker.join(timeout=10)

        self.assertEqual(stats["max"], MAX_SUBAGENT_COUNT)
        self.assertEqual(len(box[0]["results"]), 6)

    def test_subagent_isolation_and_flags(self):
        """每个子任务独立的 state / 上下文，且复用同一套循环的两个开关"""
        seen = {}

        def fake_loop(**kwargs):
            seen[kwargs["state"].messages[0]["content"]] = kwargs
            return "ok"

        self.run_tool(fake_loop, ["A", "B"])

        a, b = seen["A"], seen["B"]

        self.assertIsNot(a["state"], b["state"])
        self.assertIsNot(a["context_manager"], b["context_manager"])
        self.assertEqual(a["state"].messages, [{"role": "user", "content": "A"}])
        self.assertEqual(b["state"].messages, [{"role": "user", "content": "B"}])
        self.assertEqual(a["state"].model, "deepseek")
        self.assertEqual(a["state"].cwd, "D:\\cwd")
        self.assertEqual(
            a["context_manager"].context_window, MODELS["deepseek"].context_window
        )
        # 静默执行 + 不再询问权限 + 不碰长期记忆 + 子 Agent 专用提示词
        self.assertFalse(a["verbose"])
        self.assertEqual(a["permission_mode"], "auto")
        self.assertIsNone(a["memory_manager"])
        self.assertEqual(a["system_prompt"], SUBAGENT_SYSTEM_PROMPT)
        # 子 Agent 拿到的是过滤后的注册表
        self.assertIsNone(a["registry"].get("run_subagent"))

    def test_failed_task_does_not_break_others(self):
        def fake_loop(state, **kwargs):
            if state.messages[0]["content"] == "B":
                raise RuntimeError("炸了")
            return "ok"

        result, _ = self.run_tool(fake_loop, ["A", "B", "C"])
        by_task = {item["task"]: item for item in result["results"]}

        self.assertEqual(by_task["A"]["result"], "ok")
        self.assertIn("炸了", by_task["B"]["error"])
        self.assertEqual(by_task["C"]["result"], "ok")

    def test_none_result_coalesced(self):
        """agent_loop 达到最大循环次数时返回 None，不能把 None 交给上层"""
        result, _ = self.run_tool(lambda **kwargs: None, ["A"])
        self.assertTrue(result["results"][0]["result"])

    def test_invalid_tasks_rejected(self):
        for bad in ([], "不是列表", [1, 2], None):
            result, fake = self.run_tool(lambda **kwargs: "ok", bad)
            self.assertIn("error", result)
            fake.assert_not_called()

    def test_silent_execution_with_summary(self):
        """执行过程静默，但结束后要有启动与完成汇总输出"""
        with mock.patch(
            "tools.local.usual.run_subagent.agent_loop", return_value="ok"
        ), mock.patch("builtins.print") as fake_print:
            self.tool.execute(tasks=["A", "B"])

        printed = " ".join(str(c.args[0]) for c in fake_print.call_args_list if c.args)
        self.assertIn("SubAgent", printed)
        self.assertIn("完成", printed)


if __name__ == "__main__":
    unittest.main()

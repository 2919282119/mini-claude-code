# tools/local/usual/run_subagent.py

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4

from agent.agent import agent_loop
from agent.interrupt import is_interrupted
from agent.context import ContextManager
from agent.session import AgentState
from agent.system_prompt import SYSTEM_PROMPT
from llm.model import DEFAULT_MODEL, MODELS
from tools.Tool import Tool
from tools.tool_registry import ToolRegistry

MAX_SUBAGENT_COUNT=4

SUBAGENT_SYSTEM_PROMPT = """
你是一个 SubAgent。

你只负责执行主 Agent 分配的任务。

禁止：
1. 调用 run_subagent
2. 创建新的任务
3. 与用户交互
4. 管理会话和记忆

允许：
- 使用已有工具
- 读取代码
- 分析问题

完成后返回：

1. 结论
2. 涉及文件
3. 验证结果
4. 遗留风险
"""


def create_subagent_registry(registry: ToolRegistry):
    """
    创建 SubAgent 专用工具注册表。
    禁止 SubAgent 调用 run_subagent，避免递归。
    """

    sub_registry = ToolRegistry()

    for tool in registry.all():
        if tool.name != "run_subagent":
            sub_registry.register(tool)

    return sub_registry


def run_one_subagent(
    task: str,
    registry: ToolRegistry,
    model: str,
    cwd: str,
):
    """
    执行单个 SubAgent。
    """

    state = AgentState(
        session_id=f"subagent-{uuid4().hex}",
        messages=[
            {
                "role": "user",
                "content": task,
            }
        ],
        cwd=cwd,
        name="subagent",
        model=model,
    )
    config = MODELS[model]
    context_manager = ContextManager(config.context_window)

    result = agent_loop(
        state=state,
        registry=registry,
        context_manager=context_manager,
        memory_manager=None,
        system_prompt=SUBAGENT_SYSTEM_PROMPT,
        verbose=False,   # SubAgent 不打印工具调用
        permission_mode="auto"
    )

    if result is None and is_interrupted():
        # 中断时 agent_loop 也返回 None，和「达到最大循环次数」得靠标志区分
        result = "已被用户中断，未产生结论"

    return {
        "task": task,
        # agent_loop 达到最大循环次数时会返回 None
        "result": result or "未返回结果（可能达到最大循环次数）",
    }


def run_subagent(
    tasks: list[str],
    registry: ToolRegistry,
    model: str = DEFAULT_MODEL,
    cwd: str = ".",
):
    """
    并行启动多个 SubAgent。
    """
    if not isinstance(tasks, list) or not tasks or not all(
        isinstance(task, str) for task in tasks
    ):
        return {
            "error": "参数错误: tasks 必须是非空的字符串列表"
        }

    sub_registry = create_subagent_registry(registry)

    # 创建一个长度和 tasks 一样的列表，每个位置先放 None
    results = [None] * len(tasks)

    # 限制并发数量，避免无限创建
    max_workers = min(len(tasks), MAX_SUBAGENT_COUNT)

    print(f"🚀 启动 {len(tasks)} 个 SubAgent（并行，上限 {MAX_SUBAGENT_COUNT}）")
    start = time.time()

    # 不用 `with ThreadPoolExecutor(...)`：它退出时会 shutdown(wait=True)，一直等到
    # 所有子 Agent 跑完，Ctrl+C 看起来就像卡死。这里显式创建、不等待地关闭。
    executor = ThreadPoolExecutor(max_workers=max_workers)
    interrupted = False

    try:
        future_map = {
            executor.submit(
                run_one_subagent,
                task,
                sub_registry,
                model,
                cwd,
            ): index
            for index, task in enumerate(tasks)
        }

        for future in as_completed(future_map):
            index = future_map[future]

            try:
                results[index] = future.result()

            except Exception as e:
                results[index] = {
                    "task": tasks[index],
                    "error": f"SubAgent执行失败: {e}",
                }

    except KeyboardInterrupt:
        # 子 Agent 收不到这个信号（信号只投递给主线程），只能靠中断标志在自己的
        # 下一个轮边界停下；还在跑的那一轮不等待，没拿到结果的任务直接标为已中断
        interrupted = True

    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    for index, task in enumerate(tasks):
        if results[index] is None:
            results[index] = {"task": task, "error": "已中断"}

    # 子 Agent 执行过程静默，结束后统一汇总
    if interrupted:
        print(f"⏹ SubAgent 已中断（{time.time() - start:.1f}s）")
    else:
        print(f"✅ SubAgent 完成 {len(tasks)} 个任务（{time.time() - start:.1f}s）")
    for index, item in enumerate(results, 1):
        text = item.get("result") or item.get("error") or ""
        print(f"  [{index}] {_short(item['task'], 60)} → {_short(text, 200)}")

    return {
        "results": results
    }

# Runtime Tool，依赖于当前的model,cwd等
def create_run_subagent_tool(
    registry: ToolRegistry,
    model: str = DEFAULT_MODEL,
    cwd: str = ".",
):
    """
    创建 run_subagent Tool。
    暴露给LLM的参数只有:
    {
        tasks: []
    }
    registry/model/cwd通过闭包注入。
    """

    return Tool(
        name="run_subagent",
        description=(
            "启动多个SubAgent并行执行独立任务。"
            "适用于代码分析、问题调查、测试分析等可以并行拆分的任务。"
            "子 Agent 看不到主对话，每个任务必须自包含（目标、涉及文件、约束、验收标准）。"
            "子 Agent 不能再派生 SubAgent，也不能与用户交互。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "需要并行执行的子任务列表",
                }
            },
            "required": [
                "tasks"
            ],
        },
        function=lambda tasks: run_subagent(
            tasks=tasks,
            registry=registry,
            model=model,
            cwd=cwd,
        ),
        permission_level="EXECUTE",
    )


def _short(text, limit):
    """把结果压成单行并截断，供终端汇总展示"""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"
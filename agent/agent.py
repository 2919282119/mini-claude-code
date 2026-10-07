import json

from dotenv import load_dotenv
from pyexpat.errors import messages

from agent.context import ContextManager
from agent.interrupt import is_interrupted, request_interrupt, run_interruptibly
from agent.memory import MemoryManager
from agent.session import AgentState
from agent.system_prompt import SYSTEM_PROMPT, load_cc_md
from llm.call_llm import call_llm
from llm.model import MODELS
from tools.permission import check_permission
from tools.tool_registry import ToolRegistry

load_dotenv()

# ========================
# Agent Loop
# ========================
MAX_LOOP_CNT=30


def agent_loop(
    state,
    registry,
    context_manager,
    memory_manager=None,
    system_prompt: str = SYSTEM_PROMPT,
    verbose: bool = True, # 默认是打印调用信息的
    permission_mode: str = "interactive",
):
    messages = state.messages
    tools = registry.schemas()

    loop_cnt = 0

    while True:

        # 子 Agent 只能靠轮询停下（收不到 KeyboardInterrupt）；主 Agent 的这个
        # 标志由 main 在每轮提问前清掉，所以正常情况下不会误触发
        if is_interrupted():
            return None

        loop_cnt += 1

        if loop_cnt > MAX_LOOP_CNT:
            if verbose:
                print("Max loop count reached")
            break


        # 构造 system prompt
        current_system_prompt = system_prompt

        # 加载 CC.md
        current_system_prompt += load_cc_md()


        # 加载 memory
        if memory_manager:
            memory_prompt = memory_manager.format_for_prompt()

            if memory_prompt:
                current_system_prompt += "\n\n" + memory_prompt


        # 调用 LLM
        config = MODELS[state.model]

        try:
            response = run_interruptibly(
                call_llm,
                config,
                [
                    {
                        "role": "system",
                        "content": current_system_prompt,
                    },
                    *messages,
                ],
                tools=tools,
            )
        except KeyboardInterrupt:
            # LLM 还没返回，messages 里没有半截消息要收拾，直接结束本轮
            request_interrupt()
            return None


        context_manager.update(response)

        message = response.choices[0].message

        messages.append(message.model_dump())

        context_manager.auto_compact(state)


        # 无工具调用，直接返回
        if not message.tool_calls:
            return message.content


        # 处理工具调用
        try:
            _execute_tool_calls(messages, message, registry, verbose, permission_mode)

        except KeyboardInterrupt:
            # 工具跑到一半被 Ctrl+C：已经拿到的结果原样保留，剩下的补成「已中断」。
            # 这一步不能省——assistant 消息里的每个 tool_call 都必须有配对的 tool
            # 回复，缺一个下一次请求就会被 API 直接拒绝，那才是真的丢状态。
            request_interrupt()
            _fill_interrupted_results(messages, message.tool_calls)
            return None


def _execute_tool_calls(messages, message, registry, verbose, permission_mode):
    """执行本轮请求的所有工具，把结果按 tool_call_id 回填进 messages。

    被 Ctrl+C 打断时让 KeyboardInterrupt 继续往外抛，由调用方负责补齐剩余结果。
    """
    for tool_call in message.tool_calls:

        tool_name = tool_call.function.name

        try:
            arguments = json.loads(tool_call.function.arguments)

        except json.JSONDecodeError as e:

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        {
                            "error": f"工具参数 JSON 解析失败: {e}"
                        },
                        ensure_ascii=False,
                    ),
                }
            )

            continue


        if verbose:
            print(f"🔧 调用工具: {tool_name}")
            print(f"📦 参数: {arguments}")


        tool = registry.get(tool_name)


        if tool is None:

            result = {
                "error": f"未知工具: {tool_name}"
            }

        else:

            if permission_mode == "auto":
                allowed = True
            else:
                allowed = check_permission(tool, arguments)


            if not allowed:

                result = {
                    "error": f"用户拒绝了工具调用: {tool_name}"
                }

            else:

                try:
                    result = tool.execute(**arguments)

                except Exception as e:
                    result = {
                        "error": f"工具执行失败: {e}"
                    }


        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(
                    result,
                    ensure_ascii=False,
                ),
            }
        )


def _fill_interrupted_results(messages, tool_calls):
    """给中断时还没有结果的 tool_call 补一条「未执行」回复。

    靠扫 messages 里已有的 tool_call_id 判断缺哪些，而不是另外维护一份记账——
    转录本身就是唯一事实来源，也不会漏掉参数解析失败等提前 continue 的分支。
    """
    answered = {
        item.get("tool_call_id")
        for item in messages
        if item.get("role") == "tool"
    }

    for tool_call in tool_calls:
        if tool_call.id in answered:
            continue

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(
                    {"error": "用户中断了执行，该工具未运行"},
                    ensure_ascii=False,
                ),
            }
        )
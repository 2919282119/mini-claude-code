import json
from dotenv import load_dotenv
from pyexpat.errors import messages

from agent.context import ContextManager
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

        response = call_llm(
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


        context_manager.update(response)

        message = response.choices[0].message

        messages.append(message.model_dump())

        context_manager.auto_compact(state)


        # 无工具调用，直接返回
        if not message.tool_calls:
            return message.content


        # 处理工具调用
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
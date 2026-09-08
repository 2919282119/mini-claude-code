import json
from dotenv import load_dotenv
from pyexpat.errors import messages

from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState
from agent.system_prompt import SYSTEM_PROMPT
from llm.call_llm import call_llm
from tools.permission import check_permission
from tools.tool_registry import ToolRegistry

load_dotenv()

# ========================
# Agent Loop
# ========================
def agent_loop(state:AgentState,registry:ToolRegistry,context_manager:ContextManager,memory_manager:MemoryManager):
    # 这里传的是局部引用，后面修改没问题
    messages=state.messages
    # 这里llm要的tools列表是schema（dict）
    tools=registry.schemas()
    while True:

        # 加载memory
        memory_prompt = memory_manager.format_for_prompt()
        # 每次请求动态构造 system prompt
        system_prompt = SYSTEM_PROMPT
        if memory_prompt:
            system_prompt += "\n\n" + memory_prompt

        # 1. 调用 LLM
        response = call_llm(
            # 这里做了一个修改，平时压缩或者追加都是修改的state.messages，然后call_llm的时候再在开头添加system_prompt，防止把system_prompt也给压缩了
            [
                {
                    "role": "system",
                    "content": system_prompt
                },
                *messages
            ],
            tools=tools
        )
        # 根据LLM的response来更新上下文窗口
        context_manager.update(response)

        message = response.choices[0].message


        # 2. 把 LLM 的回复加入上下文
        # 注意这里不能直接把message加入到messages中，因为message不是dict，而是ChatCompletionMessage对象
        messages.append(message.model_dump())

        # 若usage_ratio超过80%自动执行compact
        context_manager.auto_compact(state)

        # 3. 没有 Tool Call，说明 LLM 已经可以直接回答
        if not message.tool_calls:
            return message.content

        # 4. 处理 Tool Call
        for tool_call in message.tool_calls:

            tool_name = tool_call.function.name

            arguments = json.loads(
                tool_call.function.arguments
            )

            print(f"🔧 调用工具: {tool_name}")
            print(f"📦 参数: {arguments}")

            # 5. 权限检查 + 执行具体 Tool
            tool = registry.get(tool_name)

            if tool is None:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        {"error": f"未知工具: {tool_name}"},
                        ensure_ascii=False
                    )
                })
                continue

            if not check_permission(tool, arguments):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        {"error": f"用户拒绝了工具调用: {tool_name}"},
                        ensure_ascii=False
                    )
                })
                continue

            result = tool.execute(**arguments)

            # 6. 把 Tool 执行结果返回给 LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(
                    result,
                    ensure_ascii=False
                )
            })


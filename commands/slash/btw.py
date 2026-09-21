from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager
from llm.call_llm import call_llm
from llm.model import MODELS


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    # 使用新的system_prompt，并且对话不加入state.messages
    question = " ".join(parts[1:])

    if not question:
        print("用法: /btw <问题>")
        return True

    answer = btw(question, state)
    print("\n🤖", answer)

    return True

def btw(question, state):
    messages = [
        {
            "role": "system",
            "content": """
    你是 Coding Agent 的临时辅助助手。
    根据当前上下文回答用户的问题。
    不要修改代码，不要调用工具。
    """
        },
        *state.messages,
        {
            "role": "user",
            "content": question
        }
    ]
    model_config = MODELS[state.model]
    response = call_llm(model_config,messages)

    return response.choices[0].message.content

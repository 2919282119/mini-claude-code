from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager
from llm.model import MODELS


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    if len(parts) == 1:
        print(f"Current model: {state.model}")
        print("Available models:")

        for model_name in MODELS:
            print(f"  {model_name}")

        return True

    model_name = parts[1]

    if model_name not in MODELS:
        print(f"Unknown model: {model_name}")
        print("Available models:")

        for name in MODELS:
            print(f"  {name}")

        return True

    state.model = model_name

    # 模型改变以后，上下文窗口也应该改变
    context_manager.context_window = MODELS[model_name].context_window

    print(f"Switched to {model_name}")

    return True

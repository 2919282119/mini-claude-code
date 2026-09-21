from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    state.messages.clear()
    print("Conversation cleared.")
    return True

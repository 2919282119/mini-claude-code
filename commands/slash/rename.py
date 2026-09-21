from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    if len(parts) < 2:
        print("Usage: /rename <name>")
        return True

    state.name = " ".join(parts[1:])
    session_manager.save(state)

    print("Renamed to: " + state.name)
    return True

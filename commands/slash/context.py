from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    usage = context_manager.get_usage()

    print("Context Usage")
    print("────────────────────────")
    print(f"Context Window: {usage['total']:,} tokens")
    print(f"Used:           {usage['used']:,} tokens")
    print(f"Remaining:      {usage['remaining']:,} tokens")
    print(f"Usage:          {usage['percentage']:.1f}%")

    return True

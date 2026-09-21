from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    # 合理的压缩上下文策略是：总结旧消息+保留最近消息，具体逻辑在context_manager中实现
    print(f"Context usage: {context_manager.usage_ratio:.1%}. Compacting...")
    compacted = context_manager.compact(state)
    if compacted:
        # 更新state json文件
        session_manager.save(state)
        print("Context has been compacted.")
    else:
        print("Nothing to compact.")
    return True

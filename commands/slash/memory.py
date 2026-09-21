from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    # /memory
    # 查看所有长期记忆
    if len(parts) == 1:

        memories = memory_manager.get_all()

        if not memories:
            print("No memories.")
            return True

        print("\nLong-term memories:\n")

        for memory in memories:
            print(
                f"[{memory['id']}] "
                f"{memory['content']}"
            )

        print()

        return True

    # /memory clear
    if parts[1].lower() == "clear":
        memory_manager.clear()

        print("All memories cleared.")

        return True

    # /memory delete <id>
    if parts[1].lower() == "delete":

        if len(parts) < 3:
            print("Usage: /memory delete <id>")
            return True

        if not parts[2].isdigit():
            print("Memory ID must be a number.")
            return True

        memory_id = int(parts[2])

        if memory_manager.delete(memory_id):
            print(f"Memory [{memory_id}] deleted.")
        else:
            print(f"Memory [{memory_id}] not found.")

        return True

    # /memory <content>
    # 添加长期记忆
    content = " ".join(parts[1:])

    if memory_manager.add(content):
        print(f"Memory saved: {content}")
    else:
        print("Memory already exists.")

    return True

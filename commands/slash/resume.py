from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    sessions = session_manager.list_sessions()

    if not sessions:
        print("No sessions found.")
        return True

    # /resume
    if len(parts) == 1:
        print("\nAvailable sessions:\n")

        # 第二个参数表示从1开始编号
        for i, session in enumerate(sessions, 1):
            print(
                f"[{i}] {session['name']}"
                f" | {session['cwd']}"
                f" | {session['size'] / 1024:.1f} KB"
            )

        print()

        choice = input(
            "Select session (number, q to cancel): "
        ).strip()

        if choice.lower() == "q":
            return True

        if not choice.isdigit():
            print("Invalid selection.")
            return True

        index = int(choice) - 1

        if not 0 <= index < len(sessions):
            print("Invalid selection.")
            return True

        session_id = sessions[index]["session_id"]

    # /resume <name>
    else:
        name = " ".join(parts[1:])

        matched = [
            session
            for session in sessions
            if session["name"].lower() == name.lower()
        ]

        if not matched:
            print(f"Session not found: {name}")
            return True

        if len(matched) > 1:
            print(f"Multiple sessions found for: {name}")
            return True

        session_id = matched[0]["session_id"]

    # 加载
    try:
        new_state = session_manager.load(session_id)
    except FileNotFoundError:
        print("Session no longer exists.")
        return True

    # 更新当前 state
    state.session_id = new_state.session_id
    state.name = new_state.name
    # TODO:这种写法有问题，直接把messages的引用给改掉了导致user_prompt加不进去
    # state.messages = new_state.messages

    state.messages.clear()
    state.messages.extend(new_state.messages)

    state.cwd = new_state.cwd
    state.model=new_state.model

    print(f"Resumed session: {state.name}")
    print(f"Project: {state.cwd}")

    return True

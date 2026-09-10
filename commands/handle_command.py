import subprocess

from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import SessionManager, AgentState
from llm.call_llm import call_llm
from llm.model import MODELS


def handle_command(user_input,state:AgentState,session_manager:SessionManager,context_manager:ContextManager, memory_manager:MemoryManager):
    if user_input.startswith("!"):
        return handle_shell_command(user_input, state)

    if user_input.startswith("/"):
        return handle_slash_command(
            user_input,
            state,
            session_manager,
            context_manager,
            memory_manager
        )

    return False

def handle_slash_command(user_input,state:AgentState,session_manager:SessionManager,context_manager:ContextManager, memory_manager:MemoryManager):
    parts = user_input.split()
    command = parts[0].lower()

    if command == "/help":
        print("Available commands:")
        print()
        print("  /help                 Show this help message")
        print("  /clear                Clear the current conversation")
        print("  /resume               Resume a previous session")
        print("  /compact              Compact the conversation context")
        print("  /rename <name>        Rename the current session")
        print("  /btw <message>        Ask a quick question without changing context")
        print("  /memory               Show saved long-term memories")
        print("  /memory <content>     Save a new long-term memory")
        print("  /memory delete <id>   Delete a saved memory")
        print("  /memory clear         Clear all long-term memories")
        print("  /model                Show the current model")
        print("  /model <name>         Switch to another model")
        print()
        print("  ! <command>           Execute a shell command")

        return True

    if command == "/clear":
        state.messages.clear()
        print("Conversation cleared.")
        return True

    if command == "/rename":
        if len(parts) < 2:
            print("Usage: /rename <name>")
            return True

        state.name = " ".join(parts[1:])
        session_manager.save(state)

        print("Renamed to: " + state.name)
        return True

    if command == "/resume":
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
        state.messages = new_state.messages
        state.cwd = new_state.cwd

        print(f"Resumed session: {state.name}")
        print(f"Project: {state.cwd}")

        return True

    if command == "/compact":
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

    if command == "/btw":
        # 使用新的system_prompt，并且对话不加入state.messages
        question = " ".join(parts[1:])

        if not question:
            print("用法: /btw <问题>")
            return True

        answer = btw(question, state)
        print("\n🤖", answer)

        return True

    if command == "/memory":
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

    if command=='/model':
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

    return False

def handle_shell_command(user_input, state):
    command = user_input[1:].strip()

    if not command:
        print("Usage: ! <command>")
        return True

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=state.cwd,
            capture_output=True,
            text=True
        )

        if result.stdout:
            print(result.stdout, end="")

        if result.stderr:
            print(result.stderr, end="")

        if result.returncode != 0:
            print(f"\nCommand exited with code {result.returncode}")

    except Exception as e:
        print(f"Failed to execute command: {e}")

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
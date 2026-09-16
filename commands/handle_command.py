import subprocess

from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import SessionManager, AgentState
from llm.call_llm import call_llm
from llm.model import MODELS
from tools.local.usual.load_skill import skill_manager
from tools.mcp.config import load_servers, save_servers


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
        print("  /context              Show the context usage")
        print("  /compact              Compact the conversation context")
        print("  /rename <name>        Rename the current session")
        print("  /btw <message>        Ask a quick question without changing context")
        print("  /memory               Show saved long-term memories")
        print("  /memory <content>     Save a new long-term memory")
        print("  /memory delete <id>   Delete a saved memory")
        print("  /memory clear         Clear all long-term memories")
        print("  /model                Show the current model")
        print("  /model <name>         Switch to another model")
        print("  /skills               Show installed skills")
        print("  /mcp                  List MCP servers")
        print("  /mcp add <name> <url> Add a remote MCP server")
        print("  /mcp remove <name>    Remove an MCP server")
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
        # TODO:这种写法有问题，直接把messages的引用给改掉了导致user_prompt加不进去
        # state.messages = new_state.messages

        state.messages.clear()
        state.messages.extend(new_state.messages)

        state.cwd = new_state.cwd
        state.model=new_state.model

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

    if command == "/context":
        usage = context_manager.get_usage()

        print("Context Usage")
        print("────────────────────────")
        print(f"Context Window: {usage['total']:,} tokens")
        print(f"Used:           {usage['used']:,} tokens")
        print(f"Remaining:      {usage['remaining']:,} tokens")
        print(f"Usage:          {usage['percentage']:.1f}%")

        return True

    if command == "/skills":
        # TODO:最好在安装完或者手动移入skill之后就能更新skills
        skill_manager.discover()
        skills = skill_manager.skills

        if not skills:
            print("No skills installed.")
            return True

        print("Installed skills:")
        for name, skill in skills.items():
            description = skill.get("description", "")
            if description:
                print(f"- {name}: {description}")
            else:
                print(f"- {name}")

        return True

    if command == "/mcp":
        return handle_mcp_command(parts)

    return False

def handle_mcp_command(parts):
    """MCP 服务器管理：/mcp [add|remove]

    直接读写配置文件，由代码确定性地合并/删除条目，
    不依赖模型编辑 JSON（避免覆盖丢配置）。
    """
    servers = load_servers()

    if len(parts) == 1:
        print_mcp_servers(servers)
        return True

    action = parts[1]

    if action == "add":
        return handle_mcp_add(parts[2:], servers)

    if action == "remove":
        if len(parts) < 3:
            print("Usage: /mcp remove <name>")
            return True

        name = parts[2]

        if name not in servers:
            print(f"MCP server not found: {name}")
            return True

        servers.pop(name)
        save_servers(servers)
        print(f"Removed MCP server: {name}")
        return True

    print(f"Unknown /mcp action: {action}")
    print("Usage: /mcp | /mcp add <name> <url> | /mcp remove <name>")
    return True

def handle_mcp_add(rest, servers):
    if not rest:
        print("Usage:")
        print("  /mcp add <name> <url>")
        print("  /mcp add <name> -- <command> [args...]")
        return True

    name = rest[0]

    if name in servers:
        print(f"MCP server already exists: {name}")
        print(f"Remove it first: /mcp remove {name}")
        return True

    # stdio 形式：/mcp add <name> -- <command> [args...]
    if "--" in rest:
        command_args = rest[rest.index("--") + 1:]

        if not command_args:
            print("Usage: /mcp add <name> -- <command> [args...]")
            return True

        command_args = [a.strip('"').strip("'") for a in command_args]

        servers[name] = {
            "command": command_args[0],
            "args": command_args[1:],
        }
        save_servers(servers)
        print(f"Added MCP server: {name} (stdio)")
        print("Restart miniCC to connect.")
        return True

    # http 形式：/mcp add <name> <url>
    if len(rest) < 2:
        print("Usage: /mcp add <name> <url>")
        return True

    url = rest[1]

    if not url.startswith(("http://", "https://")):
        print(f"Invalid url: {url}（需要 http:// 或 https:// 开头）")
        return True

    servers[name] = {"url": url}
    save_servers(servers)
    print(f"Added MCP server: {name} (http)")
    print("Restart miniCC to connect.")
    return True

def print_mcp_servers(servers):
    if not servers:
        print("No MCP servers configured.")
        print("Add one with: /mcp add <name> <url>")
        return

    print("MCP servers:")

    for name, conf in servers.items():
        if "url" in conf:
            print(f"  {name}  (http)   {conf['url']}")
        else:
            args = " ".join(conf.get("args", []))
            line = f"  {name}  (stdio)  {conf.get('command', '')} {args}"
            print(line.rstrip())


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
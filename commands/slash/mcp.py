from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager
from tools.mcp.config import load_servers, save_servers


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
    return handle_mcp_command(parts)

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

from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
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

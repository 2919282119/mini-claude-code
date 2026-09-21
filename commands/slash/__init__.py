from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager
from commands.slash import btw, clear, compact, context, help, mcp, memory, model, rename, resume, skills


def handle_slash_command(user_input,state:AgentState,session_manager:SessionManager,context_manager:ContextManager, memory_manager:MemoryManager):
    parts = user_input.split()
    command = parts[0].lower()

    if command == "/help":
        return help.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/clear":
        return clear.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/rename":
        return rename.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/resume":
        return resume.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/compact":
        return compact.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/btw":
        return btw.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/memory":
        return memory.run(parts, state, session_manager, context_manager, memory_manager)

    if command=='/model':
        return model.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/context":
        return context.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/skills":
        return skills.run(parts, state, session_manager, context_manager, memory_manager)

    if command == "/mcp":
        return mcp.run(parts, state, session_manager, context_manager, memory_manager)

    return False

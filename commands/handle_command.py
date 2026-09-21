import subprocess

from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import SessionManager, AgentState
from commands.shell_command import handle_shell_command
from commands.slash import handle_slash_command
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


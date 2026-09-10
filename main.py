import uuid
from pathlib import Path

from agent.agent import agent_loop
from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager
from agent.system_prompt import SYSTEM_PROMPT
from cli.banner import print_banner
from commands.handle_command import handle_command
from llm.model import MODELS, ModelConfig
from tools.setup import tools_setup


def main():
    messages = []

    # 工具的注册和初始化不应该放在agent里面，而是放在app层
    registry = tools_setup()

    # 新建一个session（AgentState）
    session_id=str(uuid.uuid4())
    cwd=str(Path.cwd())
    state=AgentState(session_id,messages,cwd)

    session_manager = SessionManager()

    memory_manager = MemoryManager()

    model_config:ModelConfig=MODELS[state.model]
    context_manager = ContextManager(model_config.context_window)

    print_banner(model_config.name)

    while True:
        user_input = input("\n> ")

        if user_input.lower() in ["exit", "quit"]:
            break
        # 检查是不是特殊命令:比如/ ! @等
        if handle_command(user_input, state,session_manager,context_manager,memory_manager):
            continue

        messages.append({
            "role": "user",
            "content": user_input
        })

        answer = agent_loop(state,registry,context_manager,memory_manager)

        print("\n🤖", answer)

        # 这里保存state到文件

        session_manager.save(state)

if __name__ == "__main__":
    main()
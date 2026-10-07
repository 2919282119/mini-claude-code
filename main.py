import uuid
from pathlib import Path

from agent.agent import agent_loop
from agent.interrupt import clear_interrupt, is_interrupted
from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager
from agent.system_prompt import SYSTEM_PROMPT
from cli.banner import print_banner
from commands.handle_command import handle_command
from llm.model import MODELS, ModelConfig
from tools.setup import tools_setup


def main():

    # 新建一个session（AgentState）
    session_id=str(uuid.uuid4())
    cwd=str(Path.cwd())
    state=AgentState(session_id,[],cwd)

    session_manager = SessionManager()

    memory_manager = MemoryManager()

    model_config:ModelConfig=MODELS[state.model]
    context_manager = ContextManager(model_config.context_window)

    # 工具的注册和初始化不应该放在agent里面，而是放在app层
    registry = tools_setup(state.model,cwd)

    print_banner(model_config.name)

    run_repl(state, session_manager, context_manager, memory_manager, registry)


def run_repl(state, session_manager, context_manager, memory_manager, registry):
    while True:
        try:
            user_input = input("\n> ")
        except EOFError:
            # stdin 读完就退出：管道喂完、输入被重定向（miniCC < 文件）、
            # Windows 下 Ctrl-Z+回车 都会走到这里。不处理的话会抛裸 traceback。
            print()
            break
        except KeyboardInterrupt:
            # 提示符处按 Ctrl+C 只回到干净提示符，不退出（否则会抛裸 traceback 退出）
            print("^C")
            continue

        if user_input.lower() in ["exit", "quit"]:
            break
        # 检查是不是特殊命令:比如/ ! @等
        if handle_command(user_input, state,session_manager,context_manager,memory_manager):
            continue

        # 这里应该判断state.name是不是None，如果是，就state.name=user_input
        if state.name==None:
            state.name=user_input[:50] # 前50个字符

        # 上一轮的中断标志不能漏进这一轮，否则新提问会在循环开头直接被掐掉
        clear_interrupt()

        state.messages.append({
            "role": "user",
            "content": user_input
        })

        answer = agent_loop(state,registry,context_manager,memory_manager)

        # 中断时 agent_loop 返回 None，打印出来会是「🤖 None」
        if is_interrupted():
            print("\n⏹ 已中断")
        else:
            print("\n🤖", answer)

        # 这里保存state到文件。中断也照常保存——已执行完的工具结果和中断标记
        # 都在 messages 里，/resume 之后能接着往下问
        session_manager.save(state)

if __name__ == "__main__":
    main()
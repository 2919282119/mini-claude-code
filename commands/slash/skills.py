from agent.context import ContextManager
from agent.memory import MemoryManager
from agent.session import AgentState, SessionManager
from tools.local.usual.load_skill import skill_manager


def run(parts: list[str], state: AgentState,
        session_manager: SessionManager,
        context_manager: ContextManager,
        memory_manager: MemoryManager) -> bool:
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

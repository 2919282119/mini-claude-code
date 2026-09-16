from tools.Tool import Tool
from agent.skill import SkillManager


skill_manager = SkillManager()


def load_skill(name):
    """
    加载指定 Skill 的完整内容。
    """
    try:
        return skill_manager.load_skill(name)

    except ValueError as e:
        return str(e)

    except Exception as e:
        return f"加载 Skill 失败: {e}"


load_skill_tool = Tool(
    name="load_skill",
    description=(
        "加载指定 Skill 的完整内容。"
        "当任务需要某个 Skill 提供的专业知识或操作规范时使用。\n\n"
        "当前可用的 Skill：\n"
        f"{skill_manager.get_skill_description()}"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "要加载的 Skill 名称"
            }
        },
        "required": ["name"]
    },
    function=load_skill,
    permission_level="READ"
)
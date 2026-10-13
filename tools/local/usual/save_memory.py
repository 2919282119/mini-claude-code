# tools/local/usual/save_memory.py

from agent.memory import MemoryManager
from tools.Tool import Tool


def create_save_memory_tool(memory_manager: MemoryManager):
    """
    创建 save_memory Tool。
    memory_manager 通过闭包注入：主 Agent 与 SubAgent 共用一份 MemoryManager，
    但该工具会在子注册表里被剔除（见 create_subagent_registry）。
    """

    def save_memory(content: str):
        if not content or not content.strip():
            return {"saved": False, "reason": "内容为空，未保存"}

        if memory_manager.add(content):
            return {"saved": True}

        return {"saved": False, "reason": "已存在相同的记忆，未重复添加"}

    return Tool(
        name="save_memory",
        description=(
            "把值得跨会话记住的信息写入长期记忆（用户偏好、项目约定、纠正与反馈、踩坑与解决方案等）。"
            "system prompt 中已列出全部现有记忆，添加前先对照，已有等价内容时不要重复添加。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "要记住的内容，一句完整、自包含的话"
                }
            },
            "required": ["content"]
        },
        function=save_memory,
        permission_level="READ",
    )

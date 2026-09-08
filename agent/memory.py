import json
from datetime import datetime
from pathlib import Path


class MemoryManager:

    def __init__(self):
        self.memory_dir = Path.home() / ".miniCC"
        self.memory_file = self.memory_dir / "memory.json"

        self.memory_dir.mkdir(parents=True, exist_ok=True)

    # ========================
    # Load
    # ========================

    def load(self):
        """加载全部长期记忆"""
        if not self.memory_file.exists():
            return []

        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                return json.load(f)

        except (json.JSONDecodeError, OSError):
            return []

    # ========================
    # Save
    # ========================

    def save(self, memories):
        """保存全部长期记忆"""
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(
                memories,
                f,
                ensure_ascii=False,
                indent=2
            )

    # ========================
    # Add
    # ========================

    def add(self, content):
        """添加一条长期记忆"""

        content = content.strip()

        if not content:
            return False

        memories = self.load()

        # 防止重复
        for memory in memories:
            if memory["content"] == content:
                return False

        memory = {
            "id": self._next_id(memories),
            "content": content,
            "created_at": datetime.now().isoformat()
        }

        memories.append(memory)

        self.save(memories)

        return True

    # ========================
    # Delete
    # ========================

    def delete(self, memory_id):
        """根据 ID 删除记忆"""

        memories = self.load()

        new_memories = [
            memory
            for memory in memories
            if memory["id"] != memory_id
        ]

        if len(new_memories) == len(memories):
            return False

        self.save(new_memories)

        return True

    # ========================
    # Clear
    # ========================

    def clear(self):
        """清空所有长期记忆"""
        self.save([])

    # ========================
    # Get
    # ========================

    def get_all(self):
        """获取全部长期记忆"""
        return self.load()

    # ========================
    # Format
    # ========================

    def format_for_prompt(self):
        """
        把长期记忆转换成适合放进 system prompt 的文本
        """

        memories = self.load()

        if not memories:
            return ""

        lines = [
            "以下是关于用户的长期记忆："
        ]

        for memory in memories:
            lines.append(
                f"- {memory['content']}"
            )

        return "\n".join(lines)

    # ========================
    # Utils
    # ========================

    # @staticmethod应该就是静态方法（类方法）
    @staticmethod
    def _next_id(memories):
        if not memories:
            return 1

        return max(
            memory["id"]
            for memory in memories
        ) + 1


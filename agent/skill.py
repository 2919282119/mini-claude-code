import yaml
from pathlib import Path


class SkillManager:
    def __init__(self):
        self.skills_dir = Path.home() / ".miniCC" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        self.skills = {}

        self.discover()

    def discover(self):
        """发现所有可用的 Skill"""
        self.skills.clear()

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"

            if not skill_file.exists():
                continue

            name = skill_dir.name
            description = self._read_description(skill_file)

            self.skills[name] = {
                "name": name,
                "description": description,
                "path": skill_file
            }

    def _read_description(self, skill_file):
        """读取 Skill frontmatter 中的 description"""
        try:
            with skill_file.open("r", encoding="utf-8") as f:
                content = f.read()

            if not content.startswith("---"):
                return ""

            parts = content.split("---", 2)

            if len(parts) < 3:
                return ""

            frontmatter = yaml.safe_load(parts[1])

            return frontmatter.get("description", "")

        except (OSError, yaml.YAMLError):
            return ""

    def load_skill(self, name):
        """加载 Skill 的完整内容"""
        skill = self.skills.get(name)

        if skill is None:
            raise ValueError(f"Skill 不存在: {name}")

        try:
            with skill["path"].open("r", encoding="utf-8") as f:
                return f.read()

        except OSError as e:
            raise RuntimeError(f"读取 Skill 失败: {e}")

    def get_skill_description(self):
        """生成给 LLM 看的 Skill 列表"""
        if not self.skills:
            return "当前没有可用的 Skill。"

        lines = []

        for skill in self.skills.values():
            lines.append(
                f"- {skill['name']}: {skill['description']}"
            )

        return "\n".join(lines)
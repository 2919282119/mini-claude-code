from dataclasses import dataclass, asdict
from pathlib import Path
import json

@dataclass
class AgentState:
    session_id: str
    messages: list
    # cwd:current working directory
    cwd: str
    name: str | None = None

    def to_dict(self) -> dict:
        # asdict是把对象转化为字典
        # json.dumps()
        # Python对象 → JSON字符串
        # json.loads()
        # JSON字符串 → Python对象
        # json.dump()
        # Python对象 → JSON文件
        # json.load()
        # JSON文件 → Python对象
        return asdict(self)

    # 一种比较特殊的静态方法，可以访问类
    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        return cls(
            session_id=data["session_id"],
            messages=data["messages"],
            cwd=data["cwd"],
            name=data["name"]
        )


class SessionManager:
    def __init__(self):
        # Path 对象重载了 / 运算符，让它可以用来拼接路径
        self.session_dir = Path.home() / ".miniCC" / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    # 应该每次agentLoop完成后保存state,而不是每次llm调用之后
    def save(self, state: AgentState) -> None:
        path = self.session_dir / f"{state.session_id}.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                state.to_dict(),
                f,
                ensure_ascii=False,
                indent=2,
            )

    def load(self, session_id: str) -> AgentState:
        path = self.session_dir / f"{session_id}.json"

        if not path.exists():
            raise FileNotFoundError(
                f"Session not found: {session_id}"
            )

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return AgentState.from_dict(data)

    # sessions列表
    def list_sessions(self):
        sessions = []

        for path in self.session_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                sessions.append({
                    "session_id": data["session_id"],
                    "name": data.get("name", "Unnamed"),
                    "cwd": data.get("cwd", ""),
                    "updated_at": path.stat().st_mtime,
                    "size": path.stat().st_size,
                })

            except (json.JSONDecodeError, KeyError):
                # 跳过损坏的 session
                continue

        # 最近修改的排在前面
        sessions.sort(
            key=lambda x: x["updated_at"],
            reverse=True
        )

        return sessions
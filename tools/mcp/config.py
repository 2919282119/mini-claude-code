import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".miniCC" / "mcp.json"


def load_servers():
    """读取全局 MCP 服务器配置。

    文件不存在视为未配置（正常情况，返回空）；文件损坏时警告并跳过。
    """
    if not CONFIG_PATH.exists():
        return {}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = f.read()

    # 空文件（如刚创建还没填）视为尚未配置
    if not raw.strip():
        return {}

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"⚠️ MCP 配置解析失败: {e}")
        return {}

    return config.get("mcpServers", {})


def save_servers(servers):
    """写回 MCP 服务器配置。

    传入的必须是完整的服务器字典（调用方负责合并），
    写入时统一走这里，保证 mcpServers 结构正确。
    """
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": servers}, f, ensure_ascii=False, indent=2)
        f.write("\n")
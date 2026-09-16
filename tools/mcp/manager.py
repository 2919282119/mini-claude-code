import atexit
import json
import logging
import re

from tools.Tool import Tool
from tools.mcp.client import MCPClient
from tools.mcp.config import load_servers

# SDK 内部的协议细节日志（对旧服务器做现代协议探测的告警、stdout 偶发
# 非法行的解析记录等）对用户没有行动价值——连接与调用的失败 miniCC 自己会
# 报告，这里静音避免刷屏。
logging.getLogger("mcp").setLevel(logging.CRITICAL)

# 已建立的客户端（stdio 的会在进程退出时统一清理，避免留下孤儿进程）
_clients = []


def load_mcp_tools():
    """连接配置中的所有 MCP 服务器，把远程工具包装成 Tool 列表。

    单个服务器失败只警告并跳过，不影响其他服务器和本地工具。
    """
    tools = []

    for server_name, server_conf in load_servers().items():
        try:
            client = _create_client(server_name, server_conf)
            _clients.append(client)
            client.initialize()
            remote_tools = client.list_tools()
        except Exception as e:
            print(f"⚠️ MCP 服务器 {server_name} 连接失败: {e}")
            continue

        for remote in remote_tools:
            tools.append(_wrap_tool(server_name, client, remote))

        print(f"🔌 MCP 服务器 {server_name}: 已加载 {len(remote_tools)} 个工具")

    return tools


def _wrap_tool(server_name, client, remote):
    """把一个远程工具包装成 Tool；调用时转发到 MCP 服务器"""

    def call(**arguments):
        try:
            result = client.call_tool(remote["name"], arguments)
        except Exception as e:
            return {"error": f"MCP 工具调用失败: {e}"}

        return _format_result(result)

    return Tool(
        name=_normalize_name(f"{server_name}__{remote['name']}"),
        description=remote.get("description", ""),
        parameters=remote.get(
            "inputSchema",
            {"type": "object", "properties": {}},
        ),
        function=call,
        permission_level="EXECUTE",
    )


def _create_client(server_name, server_conf):
    """按配置创建客户端：url 走远程 HTTP，command 走本地 stdio"""
    if "url" in server_conf:
        return MCPClient(
            name=server_name,
            url=server_conf["url"],
            headers=server_conf.get("headers"),
        )

    if "command" in server_conf:
        return MCPClient(
            name=server_name,
            command=server_conf["command"],
            args=server_conf.get("args"),
            env=server_conf.get("env"),
        )

    raise ValueError("服务器配置缺少 url 或 command")


def _close_clients():
    for client in _clients:
        close = getattr(client, "close", None)
        if close is None:
            continue

        try:
            close()
        except Exception:
            pass


atexit.register(_close_clients)


def _normalize_name(raw):
    """OpenAI function name 只允许 [a-zA-Z0-9_-]，最长 64 字符"""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)[:64]


def _format_result(result):
    """把 MCP 的 content 列表提取为文本；isError 时返回 error 字典"""
    parts = []

    for item in result.get("content", []):
        if item.get("type") == "text":
            parts.append(item.get("text", ""))
        else:
            parts.append(json.dumps(item, ensure_ascii=False))

    text = "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)

    if result.get("isError"):
        return {"error": text}

    return text

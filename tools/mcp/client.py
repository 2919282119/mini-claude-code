import asyncio
import os
import threading
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import (
    create_mcp_http_client,
    streamable_http_client,
)

REQUEST_TIMEOUT = 30

LOG_DIR = Path.home() / ".miniCC" / "logs"


class MCPClient:
    """基于官方 mcp SDK 的 MCP 客户端（同步接口包装 async SDK）。

    SDK 是异步的，而 miniCC 是同步的：客户端在后台线程运行一个 asyncio
    事件循环，连接在其中保持存活，同步方法把协程提交到该循环执行。
    对外接口与上层（manager / 工具包装 / 权限）保持不变。
    """

    def __init__(self, name=None, url=None, headers=None, command=None, args=None, env=None):
        self.name = name
        self.url = url
        self.headers = headers
        self.command = command
        self.args = args or []
        self.env = env

        self._loop = None
        self._thread = None
        self._stack = None
        self._client = None
        self._errlog = None

    # ---------- 同步接口 ----------

    def initialize(self):
        """连接服务器并完成握手（在后台事件循环中进行）"""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True
        )
        self._thread.start()

        self._run(self._connect())

    def list_tools(self):
        result = self._run(self._client.list_tools())
        return _convert_tools(result)

    def call_tool(self, name, arguments):
        result = self._run(self._client.call_tool(name, arguments))
        return _convert_result(result)

    def close(self):
        """关闭连接并停止事件循环"""
        if self._stack is not None:
            try:
                self._run(self._stack.aclose())
            except Exception:
                pass
            self._stack = None

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)

            self._loop = None
            self._thread = None

        if self._errlog is not None:
            try:
                self._errlog.close()
            except Exception:
                pass
            self._errlog = None

    # ---------- 内部实现 ----------

    def _make_server(self):
        """按配置构造 SDK 的连接目标（HTTP 用自定义 transport 以支持 headers）"""
        if self.url:
            http_client = create_mcp_http_client(headers=self.headers)
            return streamable_http_client(self.url, http_client=http_client)

        env = None
        if self.env:
            env = {**os.environ, **self.env}

        server = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=env,
        )

        # 服务器 stderr（含协议探测告警等噪音）不直接刷屏，
        # 转存日志文件；该文件对象作为子进程 stderr 的目标，存活期间保持打开
        self._errlog = _open_log_file(self.name)
        return stdio_client(server, errlog=self._errlog)

    async def _connect(self):
        self._stack = AsyncExitStack()
        self._client = await self._stack.enter_async_context(
            Client(self._make_server())
        )

    def _run(self, awaitable):
        future = asyncio.run_coroutine_threadsafe(awaitable, self._loop)
        return future.result(timeout=REQUEST_TIMEOUT)


def _convert_tools(result):
    """SDK 的 ListToolsResult → 内部的工具定义 dict 列表"""
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "inputSchema": tool.input_schema,
        }
        for tool in result.tools
    ]


def _convert_result(result):
    """SDK 的 CallToolResult → 内部的 content/isError dict"""
    return {
        "content": [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in result.content
        ],
        "isError": bool(result.is_error),
    }


def _open_log_file(name):
    """打开服务器日志文件（每次连接覆盖写）"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"mcp-{name or 'stdio'}.log"
    return open(path, "w", encoding="utf-8", errors="replace")

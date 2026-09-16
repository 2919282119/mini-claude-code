import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.mcp.client import MCPClient, _convert_result, _convert_tools
from tools.mcp.config import load_servers
from tools.mcp.manager import _create_client, _wrap_tool, load_mcp_tools


class TestMCPConfig(unittest.TestCase):

    def test_missing_config_returns_empty(self):
        with mock.patch(
            "tools.mcp.config.CONFIG_PATH", Path("/nonexistent/mcp.json")
        ):
            self.assertEqual(load_servers(), {})

    def test_empty_config_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text("", encoding="utf-8")

            with mock.patch("tools.mcp.config.CONFIG_PATH", path):
                self.assertEqual(load_servers(), {})

    def test_broken_config_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text("{broken json", encoding="utf-8")

            with mock.patch("tools.mcp.config.CONFIG_PATH", path):
                self.assertEqual(load_servers(), {})


class TestSDKConversion(unittest.TestCase):
    """SDK 类型 → 内部格式的转换。

    回归：SDK 2.x 用 snake_case 字段名（input_schema / is_error），
    1.x 风格的 inputSchema / isError 会直接报 AttributeError。
    """

    def test_tools_conversion(self):
        sdk_tool = mock.MagicMock()
        sdk_tool.name = "add"
        sdk_tool.description = "加法"
        sdk_tool.input_schema = {"type": "object", "properties": {}}

        result = mock.MagicMock()
        result.tools = [sdk_tool]

        self.assertEqual(
            _convert_tools(result),
            [{
                "name": "add",
                "description": "加法",
                "inputSchema": {"type": "object", "properties": {}},
            }],
        )

    def test_tools_conversion_none_description(self):
        sdk_tool = mock.MagicMock()
        sdk_tool.name = "t"
        sdk_tool.description = None
        sdk_tool.input_schema = {}

        result = mock.MagicMock()
        result.tools = [sdk_tool]

        self.assertEqual(_convert_tools(result)[0]["description"], "")

    def test_result_conversion(self):
        item = mock.MagicMock()
        item.model_dump.return_value = {"type": "text", "text": "hello"}

        result = mock.MagicMock()
        result.content = [item]
        result.is_error = False

        self.assertEqual(
            _convert_result(result),
            {"content": [{"type": "text", "text": "hello"}], "isError": False},
        )

    def test_result_conversion_error(self):
        item = mock.MagicMock()
        item.model_dump.return_value = {"type": "text", "text": "bad"}

        result = mock.MagicMock()
        result.content = [item]
        result.is_error = True

        self.assertTrue(_convert_result(result)["isError"])


class TestCreateClient(unittest.TestCase):

    def test_url_config_creates_http_client(self):
        client = _create_client("srv", {
            "url": "https://x.example.com/mcp",
            "headers": {"Authorization": "Bearer t"},
        })
        self.assertIsInstance(client, MCPClient)
        self.assertEqual(client.name, "srv")
        self.assertEqual(client.url, "https://x.example.com/mcp")
        self.assertEqual(client.headers, {"Authorization": "Bearer t"})
        self.assertIsNone(client.command)

    def test_command_config_creates_stdio_client(self):
        client = _create_client("srv", {
            "command": "uvx",
            "args": ["some-server", "--db", "x.db"],
            "env": {"HTTPS_PROXY": "http://127.0.0.1:7897"},
        })
        self.assertIsInstance(client, MCPClient)
        self.assertEqual(client.name, "srv")
        self.assertEqual(client.command, "uvx")
        self.assertEqual(client.args, ["some-server", "--db", "x.db"])
        self.assertEqual(client.env, {"HTTPS_PROXY": "http://127.0.0.1:7897"})
        self.assertIsNone(client.url)

    def test_invalid_config_raises(self):
        with self.assertRaises(ValueError):
            _create_client("srv", {"foo": "bar"})


class TestMCPToolWrapping(unittest.TestCase):

    def test_wrap_tool(self):
        client = mock.MagicMock()
        client.call_tool.return_value = {
            "content": [{"type": "text", "text": "结果文本"}]
        }
        remote = {
            "name": "search.repos",
            "description": "搜索仓库",
            "inputSchema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        }

        tool = _wrap_tool("github", client, remote)

        # 点号等非法字符被规范化为下划线
        self.assertEqual(tool.name, "github__search_repos")
        self.assertEqual(tool.permission_level, "EXECUTE")
        self.assertEqual(tool.parameters, remote["inputSchema"])
        self.assertEqual(tool.description, "搜索仓库")

        result = tool.execute(q="test")
        self.assertEqual(result, "结果文本")
        # 转发用的是原始的远程工具名，不是包装后的名字
        client.call_tool.assert_called_once_with("search.repos", {"q": "test"})

    def test_tool_call_failure_returns_error(self):
        client = mock.MagicMock()
        client.call_tool.side_effect = RuntimeError("网络错误")

        tool = _wrap_tool("srv", client, {"name": "t"})
        result = tool.execute()

        self.assertIn("error", result)

    def test_iserror_result(self):
        client = mock.MagicMock()
        client.call_tool.return_value = {
            "content": [{"type": "text", "text": "失败原因"}],
            "isError": True,
        }

        tool = _wrap_tool("srv", client, {"name": "t"})
        result = tool.execute()

        self.assertEqual(result, {"error": "失败原因"})


class TestLoadMCPTools(unittest.TestCase):

    @mock.patch("tools.mcp.manager.MCPClient")
    @mock.patch("tools.mcp.manager.load_servers")
    def test_server_failure_skipped(self, mock_load_servers, MockClient):
        mock_load_servers.return_value = {
            "bad": {"url": "https://bad.example.com/mcp"},
            "good": {"url": "https://good.example.com/mcp"},
        }

        bad_client = mock.MagicMock()
        bad_client.initialize.side_effect = RuntimeError("连不上")

        good_client = mock.MagicMock()
        good_client.list_tools.return_value = [{"name": "t1"}]

        MockClient.side_effect = [bad_client, good_client]

        tools = load_mcp_tools()

        # 坏服务器被跳过，好服务器的工具正常返回
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, "good__t1")

    @mock.patch("tools.mcp.manager.load_servers")
    def test_no_servers_returns_empty(self, mock_load_servers):
        mock_load_servers.return_value = {}
        self.assertEqual(load_mcp_tools(), [])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from commands.slash.mcp import handle_mcp_command


class TestMCPCommand(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config_path = Path(self._tmp.name) / "mcp.json"

        # 配置路径指到临时目录，隔离真实用户配置
        self.patcher = mock.patch(
            "tools.mcp.config.CONFIG_PATH", self.config_path
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        # 静音命令输出
        self.print_patcher = mock.patch("builtins.print")
        self.print_patcher.start()
        self.addCleanup(self.print_patcher.stop)

    def read_config(self):
        with open(self.config_path, encoding="utf-8") as f:
            return json.load(f)["mcpServers"]

    def test_add_http_server(self):
        handle_mcp_command(
            ["/mcp", "add", "niu-lai", "https://niu-lai.net/api/mcp"]
        )

        servers = self.read_config()
        self.assertEqual(
            servers["niu-lai"], {"url": "https://niu-lai.net/api/mcp"}
        )

    def test_add_stdio_server(self):
        handle_mcp_command([
            "/mcp", "add", "yahoo", "--",
            "uvx", "--with", "mcp<2", "yahoo-finance-mcp",
        ])

        servers = self.read_config()
        self.assertEqual(servers["yahoo"]["command"], "uvx")
        self.assertEqual(
            servers["yahoo"]["args"],
            ["--with", "mcp<2", "yahoo-finance-mcp"],
        )

    def test_add_keeps_existing_servers(self):
        """回归：新增服务器必须保留已有条目（曾因覆盖写入丢失配置）"""
        handle_mcp_command(
            ["/mcp", "add", "first", "https://a.example.com/mcp"]
        )
        handle_mcp_command(
            ["/mcp", "add", "second", "https://b.example.com/mcp"]
        )

        servers = self.read_config()
        self.assertEqual(set(servers), {"first", "second"})
        self.assertEqual(
            servers["first"], {"url": "https://a.example.com/mcp"}
        )

    def test_add_duplicate_rejected(self):
        handle_mcp_command(
            ["/mcp", "add", "first", "https://a.example.com/mcp"]
        )
        handle_mcp_command(
            ["/mcp", "add", "first", "https://b.example.com/mcp"]
        )

        servers = self.read_config()
        # 保留原条目，不被新值覆盖
        self.assertEqual(
            servers["first"], {"url": "https://a.example.com/mcp"}
        )

    def test_remove_keeps_others(self):
        handle_mcp_command(
            ["/mcp", "add", "first", "https://a.example.com/mcp"]
        )
        handle_mcp_command(
            ["/mcp", "add", "second", "https://b.example.com/mcp"]
        )
        handle_mcp_command(["/mcp", "remove", "first"])

        servers = self.read_config()
        self.assertEqual(set(servers), {"second"})

    def test_invalid_url_rejected(self):
        handle_mcp_command(["/mcp", "add", "bad", "not-a-url"])

        # 无效配置不应写入文件
        self.assertFalse(self.config_path.exists())

    def test_list_and_usage_do_not_crash(self):
        handle_mcp_command(["/mcp"])
        handle_mcp_command(["/mcp", "add"])
        handle_mcp_command(["/mcp", "remove"])
        handle_mcp_command(["/mcp", "unknown-action"])
        handle_mcp_command(["/mcp", "remove", "not-exist"])


if __name__ == "__main__":
    unittest.main()

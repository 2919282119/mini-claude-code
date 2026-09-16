import subprocess
import unittest
from unittest import mock

from tools.local.builtin.bash import bash


class TestBashTimeout(unittest.TestCase):

    def test_timeout_kills_process_tree_and_returns(self):
        """回归：前台命令超时后必须杀整棵进程树并返回，而不是卡死"""
        with mock.patch(
            "tools.local.builtin.bash.subprocess.Popen"
        ) as mock_popen, mock.patch(
            "tools.local.builtin.bash.subprocess.run"
        ) as mock_run:
            proc = mock_popen.return_value
            proc.pid = 4321
            proc.communicate.side_effect = subprocess.TimeoutExpired(
                cmd="long command", timeout=30
            )

            result = bash("long command")

        # 超时时用 taskkill /T 杀整棵进程树（含孙进程）
        mock_run.assert_called_once()
        taskkill_args = mock_run.call_args[0][0]
        self.assertEqual(taskkill_args[:3], ["taskkill", "/F", "/T"])
        self.assertEqual(taskkill_args[-1], "4321")

        # 返回超时错误，而不是抛异常或永远阻塞
        self.assertEqual(result["returncode"], -1)
        self.assertIn("超时", result["output"])

    def test_normal_command_returns_output(self):
        with mock.patch(
            "tools.local.builtin.bash.subprocess.Popen"
        ) as mock_popen:
            proc = mock_popen.return_value
            proc.communicate.return_value = ("hello\n", "")
            proc.returncode = 0

            result = bash("echo hello")

        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["output"], "hello\n")

    def test_background_detaches_stdin(self):
        """后台命令不应继承控制台输入"""
        with mock.patch(
            "tools.local.builtin.bash.subprocess.Popen"
        ) as mock_popen:
            mock_popen.return_value.pid = 99

            result = bash("npm run dev", background=True)

        kwargs = mock_popen.call_args[1]
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(result["returncode"], 0)


if __name__ == "__main__":
    unittest.main()

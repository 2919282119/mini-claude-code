import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.local.builtin.edit_file import edit_file
from tools.local.builtin.read_file import read_file
from tools.local.builtin.write_file import write_file


class TestTildeExpansion(unittest.TestCase):
    """回归：文件工具需支持 ~ 展开（如 ~/.miniCC/mcp.json）"""

    def test_read_write_edit_with_tilde(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "os.path.expanduser",
                side_effect=lambda p: (
                    p.replace("~", tmp, 1) if p.startswith("~") else p
                ),
            ):
                # 写（含自动创建父目录）
                result = write_file("~/sub/data.json", '{"a": 1}')
                self.assertIn("成功", result)
                self.assertTrue((Path(tmp) / "sub" / "data.json").exists())

                # 读
                self.assertEqual(read_file("~/sub/data.json"), '{"a": 1}')

                # 编辑
                edit_file("~/sub/data.json", "1", "2")
                self.assertEqual(read_file("~/sub/data.json"), '{"a": 2}')


if __name__ == "__main__":
    unittest.main()

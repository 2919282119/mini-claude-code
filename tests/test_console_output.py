import sys
import unittest


class TestConsoleOutput(unittest.TestCase):

    def test_emoji_output_does_not_crash(self):
        """回归：输出流不支持 emoji 时（如 GBK 管道）也不应抛 UnicodeEncodeError"""
        for stream in (sys.stdout, sys.stderr):
            encoding = getattr(stream, "encoding", None) or "utf-8"
            errors = getattr(stream, "errors", None) or "strict"

            "⚠️ 🔌".encode(encoding, errors)


if __name__ == "__main__":
    unittest.main()

# Windows 下 stdout/stderr 默认 GBK（尤其输出被重定向/管道时），emoji 等字符
# 直接 print 会抛 UnicodeEncodeError；统一按 UTF-8 输出且不抛错（终端不支持时
# 显示乱码，但程序不会崩）。放在本包而不是 main.py：程序与测试等所有入口都会
# 先 import tools，保证任何工具代码打印之前输出流已配置好。
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

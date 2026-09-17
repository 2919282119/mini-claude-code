import json
import unicodedata

# 修改，不再以工具名:参数为key，而是直接以函数名为key，避免权限询问太过于频繁
_remembered = {}

def _request_approval(tool, arguments):
    """WRITE/EXECUTE 工具需要用户确认。返回 True=允许，False=拒绝。"""
    key = tool.name

    if key in _remembered:
        return _remembered[key]

    # 参数刚才已由 agent 循环打印过（🔧/📦），这里不重复
    print(f"\n⚠️  需要权限: {tool.name} ({tool.permission_level})")

    while True:
        raw = input("允许 (y) / 拒绝 (n) / 记住并允许 (a) [n]: ")
        # 归一化：中文输入法下容易打出全角字符（ｙ / ｎ / ａ）
        choice = unicodedata.normalize("NFKC", raw).strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("a", "always"):
            _remembered[key] = True
            return True
        if choice in ("n", "no", ""):
            # 只记住用户显式选择的「记住并允许」；回车 / n 的拒绝只作用于本次，
            # 否则一次误按回车会让该工具在本进程内被静默拒绝（连提示都不再出现）
            return False
        print("无效输入，请输入 y / n / a")


def check_permission(tool, arguments):
    if tool.permission_level in ("WRITE", "EXECUTE"):
        return _request_approval(tool, arguments)
    return True


def clear_remembered():
    _remembered.clear()

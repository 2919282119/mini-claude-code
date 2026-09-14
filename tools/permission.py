import json

# 修改，不再以工具名:参数为key，而是直接以函数名为key，避免权限询问太过于频繁
_remembered = {}

def _request_approval(tool, arguments):
    """WRITE/EXECUTE 工具需要用户确认。返回 True=允许，False=拒绝。"""
    key = tool.name

    if key in _remembered:
        return _remembered[key]

    print(f"\n⚠️  需要权限: {tool.name} ({tool.permission_level})")
    print(f"📦 参数: {arguments}")

    while True:
        choice = input("允许 (y) / 拒绝 (n) / 记住并允许 (a) [n]: ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("a", "always"):
            _remembered[key] = True
            return True
        if choice in ("n", "no", ""):
            _remembered[key] = False
            return False
        print("无效输入，请输入 y / n / a")


def check_permission(tool, arguments):
    if tool.permission_level in ("WRITE", "EXECUTE"):
        return _request_approval(tool, arguments)
    return True


def clear_remembered():
    _remembered.clear()

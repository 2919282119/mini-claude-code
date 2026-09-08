import json

# 记住的权限决定：key = "工具名:参数"，参数相同的调用不再询问
_remembered = {}


def _approval_key(tool_name, arguments):
    return f"{tool_name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"


def _request_approval(tool, arguments):
    """WRITE/EXECUTE 工具需要用户确认。返回 True=允许，False=拒绝。"""
    key = _approval_key(tool.name, arguments)

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

import os

from tools.Tool import Tool


def grep(pattern, path="."):
    """
    在文件中搜索指定字符串。

    pattern: 要搜索的字符串
    path: 文件或目录
    """

    results = []

    try:

        # 如果 path 本身就是文件
        if os.path.isfile(path):
            _search_file(path, pattern, results)

        # 如果 path 是目录
        elif os.path.isdir(path):

            for root, dirs, files in os.walk(path):

                # 忽略常见无关目录
                dirs[:] = [
                    d for d in dirs
                    if d not in {
                        ".git",
                        "__pycache__",
                        "node_modules",
                        ".venv",
                        "venv"
                    }
                ]

                for file in files:

                    file_path = os.path.join(root, file)

                    _search_file(
                        file_path,
                        pattern,
                        results
                    )

        else:
            return f"路径不存在: {path}"

        if not results:
            return f"没有找到: {pattern}"

        return "\n".join(results)

    except Exception as e:
        return f"搜索失败: {e}"


def _search_file(path, pattern, results):

    # 只搜索文本文件
    try:
        with open(path, "r", encoding="utf-8") as f:

            for line_number, line in enumerate(f, 1):

                if pattern in line:
                    results.append(
                        f"{path}:{line_number}: {line.rstrip()}"
                    )

    except (UnicodeDecodeError, PermissionError):
        # 二进制文件或者没有权限的文件直接跳过
        pass


grep_tool = Tool(
    name="grep",
    description="在文件中搜索指定字符串",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "要搜索的字符串"
            },
            "path": {
                "type": "string",
                "description": "文件或目录，默认当前目录"
            }
        },
        "required": ["pattern"]
    },
    function=grep
)
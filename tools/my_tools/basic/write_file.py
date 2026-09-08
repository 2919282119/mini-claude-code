import os

from tools.Tool import Tool


def write_file(path, content):
    """
    创建或覆盖文件。
    """
    try:
        # 如果父目录不存在，则创建
        parent = os.path.dirname(path)

        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"文件写入成功: {path}"

    except PermissionError:
        return f"没有权限写入文件: {path}"

    except Exception as e:
        return f"写入文件失败: {e}"


write_file_tool = Tool(
    name="write_file",
    description="创建或覆盖文件",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要写入的文件路径"
            },
            "content": {
                "type": "string",
                "description": "要写入的文件内容"
            }
        },
        "required": ["path", "content"]
    },
    function=write_file,
    permission_level="WRITE"
)
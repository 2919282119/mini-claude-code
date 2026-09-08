import os

from tools.Tool import Tool


def list_dir(path="."):
    """
    列出目录下的文件和子目录。
    """
    try:
        entries = os.listdir(path)

        result = []

        for entry in entries:
            full_path = os.path.join(path, entry)

            if os.path.isdir(full_path):
                result.append(f"[DIR]  {entry}")
            else:
                result.append(f"[FILE] {entry}")

        return "\n".join(result)

    except FileNotFoundError:
        return f"目录不存在: {path}"

    except PermissionError:
        return f"没有权限访问目录: {path}"

    except Exception as e:
        return f"列出目录失败: {e}"


list_dir_tool = Tool(
    name="list_dir",
    description="列出目录下的文件和子目录",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要列出的目录路径，默认当前目录"
            }
        },
        "required": []
    },
    function=list_dir
)
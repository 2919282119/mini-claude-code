from tools.Tool import Tool


def read_file(path):
    """
    读取文件内容。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    except FileNotFoundError:
        return f"文件不存在: {path}"

    except PermissionError:
        return f"没有权限读取文件: {path}"

    except UnicodeDecodeError:
        return f"文件不是 UTF-8 文本文件: {path}"

    except Exception as e:
        return f"读取文件失败: {e}"


read_file_tool = Tool(
    name="read_file",
    description="读取文件内容",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要读取的文件路径"
            }
        },
        "required": ["path"]
    },
    function=read_file
)
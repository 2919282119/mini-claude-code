import os

from tools.Tool import Tool


def edit_file(path, old_text, new_text):
    """
    将文件中的 old_text 精确替换为 new_text。
    """
    path = os.path.expanduser(path)

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # 找不到
        if old_text not in content:
            return f"未找到要替换的内容: {old_text}"

        # 防止误修改多个地方
        count = content.count(old_text)

        if count > 1:
            return (
                f"修改失败: old_text 在文件中出现了 {count} 次，"
                f"为了避免误修改，不执行替换"
            )

        new_content = content.replace(old_text, new_text)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"文件修改成功: {path}"

    except FileNotFoundError:
        return f"文件不存在: {path}"

    except PermissionError:
        return f"没有权限修改文件: {path}"

    except Exception as e:
        return f"修改文件失败: {e}"


edit_file_tool = Tool(
    name="edit_file",
    description="将文件中的 old_text 精确替换为 new_text",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要修改的文件路径"
            },
            "old_text": {
                "type": "string",
                "description": "要被替换的原文"
            },
            "new_text": {
                "type": "string",
                "description": "替换后的新文本"
            }
        },
        "required": ["path", "old_text", "new_text"]
    },
    function=edit_file,
    permission_level="WRITE"
)
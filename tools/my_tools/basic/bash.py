import subprocess

from tools.Tool import Tool


def bash(command):
    """
    执行 Shell 命令。
    """

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )

        output = result.stdout

        if result.stderr:
            output += "\n" + result.stderr

        return {
            "returncode": result.returncode,
            "output": output
        }

    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "output": "命令执行超时（30秒）"
        }

    except Exception as e:
        return {
            "returncode": -1,
            "output": f"执行失败: {e}"
        }


bash_tool = Tool(
    name="bash",
    description="执行 Shell 命令",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令"
            }
        },
        "required": ["command"]
    },
    function=bash,
    permission_level="EXECUTE"
)
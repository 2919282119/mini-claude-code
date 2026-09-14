import subprocess

from tools.Tool import Tool


def bash(command, background=False):
    """
    执行 Shell 命令。

    background=False：等待命令执行完成
    background=True：后台运行，适合 npm run dev 等长期运行命令
    """
    try:
        # 后台运行
        if background:
            process = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )

            return {
                "returncode": 0,
                "output": f"命令已在后台启动，PID: {process.pid}"
            }

        # 普通命令：等待执行完成
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        try:
            stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            # shell=True 下命令可能派生出孙进程（如 npm run dev 下的 node），
            # 只杀直接子进程不足以关闭管道写端，communicate() 会永远等不到 EOF，
            # 导致整个进程卡死；必须用 taskkill /T 杀整棵进程树
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
            )
            process.wait()

            return {
                "returncode": -1,
                "output": "命令执行超时（30秒）"
            }

        output = stdout

        if stderr:
            output += "\n" + stderr

        return {
            "returncode": process.returncode,
            "output": output
        }

    except Exception as e:
        return {
            "returncode": -1,
            "output": f"执行失败: {e}"
        }


bash_tool = Tool(
    name="bash",
    description=(
        "执行 Shell 命令。"
        "普通命令直接执行并等待完成。"
        "对于会长期运行且不会自动退出的命令，例如 npm run dev、"
        "开发服务器、watcher 等，应设置 background=true。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 Shell 命令"
            },
            "background": {
                "type": "boolean",
                "description": (
                    "是否后台运行。"
                    "长期运行的开发服务器、watcher 等设置为 true。"
                )
            }
        },
        "required": ["command"]
    },
    function=bash,
    permission_level="EXECUTE"
)
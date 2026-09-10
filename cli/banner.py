from pathlib import Path


LOGO = r"""
███╗   ███╗██╗███╗   ██╗██╗ ██████╗ ██████╗
████╗ ████║██║████╗  ██║██║██╔════╝██╔════╝
██╔████╔██║██║██╔██╗ ██║██║██║     ██║
██║╚██╔╝██║██║██║╚██╗██║██║██║     ██║
██║ ╚═╝ ██║██║██║ ╚████║██║╚██████╗╚██████╗
╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝ ╚═════╝ ╚═════╝
""".strip("\n")


def print_banner(model_name: str, version: str = "0.1.0"):
    width = 70

    print()
    print("╭" + "─" * width + "╮")

    # Logo
    for line in LOGO.splitlines():
        padding = width - 2 - len(line)
        print("│  " + line + " " * padding + "│")

    print("│" + " " * width + "│")

    # 信息
    lines = [
        "                       miniCC",
        "",
        f"  Model   · {model_name}",
        f"  Project · {Path.cwd()}",
        "",
        "  Type /help for commands.",
    ]

    for line in lines:
        padding = width - len(line)
        print("│" + line + " " * padding + "│")

    print("│" + " " * width + "│")
    print("╰" + "─" * width + "╯")
    print()
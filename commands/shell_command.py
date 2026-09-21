import subprocess


def handle_shell_command(user_input, state):
    command = user_input[1:].strip()

    if not command:
        print("Usage: ! <command>")
        return True

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=state.cwd,
            capture_output=True,
            text=True
        )

        if result.stdout:
            print(result.stdout, end="")

        if result.stderr:
            print(result.stderr, end="")

        if result.returncode != 0:
            print(f"\nCommand exited with code {result.returncode}")

    except Exception as e:
        print(f"Failed to execute command: {e}")

    return True

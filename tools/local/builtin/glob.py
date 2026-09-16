from pathlib import Path

from tools.Tool import Tool


def glob_files(pattern: str, path: str = ".") -> list[str]:
    """
    Find files and directories matching a glob pattern.

    Args:
        pattern: Glob pattern, e.g. "**/*.py", "src/**/*.vue"
        path: Base directory to search from. Defaults to current directory.

    Returns:
        A list of matching paths.
    """
    base_path = Path(path).resolve()

    if not base_path.exists():
        return [f"Error: path does not exist: {path}"]

    if not base_path.is_dir():
        return [f"Error: path is not a directory: {path}"]

    try:
        matches = base_path.glob(pattern)

        results = sorted(
            str(match.relative_to(base_path))
            for match in matches
        )

        return results

    except Exception as e:
        return [f"Error: {e}"]


glob_tool = Tool(
    name="glob",
    description=(
        "Find files and directories matching a glob pattern. "
        "Use patterns like '**/*.py' or 'src/**/*.vue'. "
        "Returns matching paths relative to the search directory."
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": (
                    "Glob pattern to match files or directories, "
                    "for example '**/*.py' or 'src/**/*.vue'."
                ),
            },
            "path": {
                "type": "string",
                "description": (
                    "Directory to search from. "
                    "Defaults to the current working directory."
                ),
                "default": ".",
            },
        },
        "required": ["pattern"],
    },
    function=glob_files,
    permission_level="READ",
)
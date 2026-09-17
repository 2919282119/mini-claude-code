from llm.model import DEFAULT_MODEL
from tools.local.usual.load_skill import load_skill_tool
from tools.local.builtin.glob import glob_tool
from tools.local.usual.run_subagent import create_subagent_registry, create_run_subagent_tool
from tools.local.usual.search_web import search_tool
from tools.local.builtin.bash import bash_tool
from tools.local.builtin.edit_file import edit_file_tool
from tools.local.builtin.grep import grep_tool
from tools.local.builtin.ls import list_dir_tool
from tools.local.builtin.read_file import read_file_tool
from tools.local.builtin.write_file import write_file_tool
from tools.mcp.manager import load_mcp_tools
from tools.tool_registry import ToolRegistry

def tools_setup(model=DEFAULT_MODEL,cwd='.'):
    # 注意这里要返回，而不是每次都创建新的registry
    registry = ToolRegistry()
    registry.register(search_tool)
    registry.register(bash_tool)
    registry.register(edit_file_tool)
    registry.register(grep_tool)
    registry.register(glob_tool)
    registry.register(list_dir_tool)
    registry.register(read_file_tool)
    registry.register(write_file_tool)
    registry.register(load_skill_tool)

    # 远程 MCP 工具（未配置时为空列表）
    for tool in load_mcp_tools():
        registry.register(tool)

    # SubAgent Tool
    run_subagent_tool = create_run_subagent_tool(
        registry=registry,
        model=model,
        cwd=cwd,
    )
    registry.register(run_subagent_tool)

    return registry

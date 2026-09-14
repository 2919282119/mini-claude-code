from tools.load_skill import load_skill_tool
from tools.my_tools.basic.glob import glob_tool
from tools.my_tools.usual.search_web import search_tool
from tools.my_tools.basic.bash import bash_tool
from tools.my_tools.basic.edit_file import edit_file_tool
from tools.my_tools.basic.grep import grep_tool
from tools.my_tools.basic.ls import list_dir_tool
from tools.my_tools.basic.read_file import read_file_tool
from tools.my_tools.basic.write_file import write_file_tool
from tools.tool_registry import ToolRegistry

def tools_setup():
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
    return registry

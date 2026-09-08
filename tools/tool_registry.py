from typing import List

from tools.Tool import Tool


class ToolRegistry:

    def __init__(self):
        self.tools = {}

    def register(self, tool: Tool):
        self.tools[tool.name] = tool

    def get(self, name)->Tool:
        return self.tools.get(name)

    def all(self)->List[Tool]:
        return list(self.tools.values())

    def schemas(self)->List:
        return [tool.to_schema() for tool in self.tools.values()]
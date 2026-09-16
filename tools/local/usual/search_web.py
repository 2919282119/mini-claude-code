from tools.Tool import Tool
from tavily import TavilyClient


tavily_client = TavilyClient()
def search_web(query: str):
    """联网搜索"""
    return tavily_client.search(
        query=query,
        max_results=5
    )

search_tool=Tool(
    name="search_web",
    description="联网搜索，获取最新信息",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            }
        },
        "required": ["query"]
    },
    function=search_web
)

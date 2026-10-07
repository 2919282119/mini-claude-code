from agent.interrupt import run_interruptibly
from tools.Tool import Tool
from tavily import TavilyClient


tavily_client = TavilyClient()
def search_web(query: str):
    """联网搜索"""
    # 走 run_interruptibly：Tavily 也是主线程里的阻塞 HTTP，直接发的话 Ctrl+C 会被
    # 压到这次请求结束（见 agent/interrupt.py 里第 2 条）
    return run_interruptibly(
        tavily_client.search,
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

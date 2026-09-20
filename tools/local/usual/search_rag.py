from tools.Tool import Tool

from rag.knowledge_base import describe, resolve_name
from rag.retriever import get_retriever


def search_rag(
    kb: str,
    query: str
):

    name = resolve_name(kb)

    if name is None:
        # 库名对不上就把可用库列出来，让模型自己纠正后重试（模型可能记错名字）
        return (
            f"知识库不存在：{kb}\n"
            f"当前可用知识库：\n{describe()}"
        )

    try:
        docs = get_retriever(name).invoke(query)

    except Exception as e:
        # 索引缺失 / RAG 依赖未安装 / PDF 不存在：返回文本让 LLM 自己决定怎么办，
        # 不要抛异常中断主循环
        return (
            f"RAG 知识库不可用：{e}\n"
            "请确认该知识库的 PDF 文件存在，或执行 `python -m rag.build_index` 重建索引"
            "（需先安装 rag 依赖）。"
        )


    result = "\n\n".join(
        [
            f"""
参考资料 {i + 1}

来源:
{doc.metadata}

内容:
{doc.page_content}
"""
            for i, doc in enumerate(docs)
        ]
    )


    return result



rag_tool = Tool(
    name="rag_search",

    description=f"""
在本地 PDF 文档知识库里做语义检索，返回最相关的段落。

语料是 PDF 文档（书籍 / 论文 / 技术资料），不是本项目的源码——问代码请用 grep / read_file。
当问题涉及下面某个库覆盖的主题（概念、原理、设计取舍、方法论）时使用它，
并选描述最贴合问题的那个 kb；没有贴合的库就不要调用。

可用知识库（kb 参数必须是下列名字之一）：
{describe()}
""",

    parameters={
        "type": "object",
        "properties": {
            "kb": {
                "type": "string",
                "description": "知识库名称，必须是「可用知识库」里列出的名字之一"
            },
            "query": {
                "type": "string",
                "description": "要检索的问题"
            }
        },
        "required": [
            "kb",
            "query"
        ]
    },

    function=search_rag,

    permission_level="READ"
)

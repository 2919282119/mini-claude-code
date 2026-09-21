"""共享的 embedding 模型单例，以及"本地优先"的模型加载策略。

所有知识库用的是同一个模型（`EMBEDDING_MODEL`），embedding 推理又是无状态的
纯函数——同样的输入无论谁调用都得到同样的向量，所以没理由每个库各加载一份。
共用一份之后，常驻内存/显存不随知识库数量增长。

单独一个模块而不是塞进 retriever：build_index 和 retriever 都要用它，放任何
一边都会让另一个反向依赖。

并发：已实测共享同一个实例、8 线程并发 encode 无异常且与串行结果分差 0.00e+00。
"""

from rag.knowledge_base import EMBEDDING_MODEL

# 进程内缓存：一次构造，所有知识库共用
_embeddings = None


def load_local_first(build):
    """先只认本地缓存构造模型，本地没有才允许联网下载。

    huggingface_hub 默认会为每个文件发 HEAD 去查远端有没有更新；网络不通时每个
    文件要重试 5 次并退避（1+2+4+8+8 秒），实测一次加载在 4 个文件上累计白等约
    **90 秒**，而模型其实早就躺在本地缓存里。本地找不到时抛 `OSError`（实测 0.0 秒、
    不发请求），据此回退到联网下载——所以首次使用该下载还是能下载，只是缓存命中时
    不再有任何网络往返。
    """
    try:
        return build(local_files_only=True)
    except OSError:
        # 本地没有：首次使用，或缓存被清掉/缺文件，都走这里补上
        return build(local_files_only=False)


def get_embeddings():
    """返回进程内共享的 HuggingFaceEmbeddings。

    重依赖在函数内 import，保证本模块可被安全 import——索引缺失或 RAG 依赖
    没装时 miniCC 仍要能正常启动。
    """
    global _embeddings

    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings

        _embeddings = load_local_first(
            lambda local_files_only: HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={"local_files_only": local_files_only},
            )
        )

    return _embeddings

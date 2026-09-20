from rag.knowledge_base import EMBEDDING_MODEL, index_dir, index_file


# 按库名缓存：一个知识库一个 retriever，用到哪个才加载哪个
_retrievers = {}


def get_retriever(kb):
    """返回指定知识库的 FAISS retriever（按库缓存）；索引不存在时先构建一次。

    langchain / embedding 模型都在首次调用时才加载，保证 miniCC 在未安装
    RAG 依赖或索引缺失时仍能正常启动。
    """
    if kb in _retrievers:
        return _retrievers[kb]

    from langchain_community.vectorstores import FAISS
    from langchain_huggingface import HuggingFaceEmbeddings

    # 判断索引文件而不是目录：构建中途失败会留下空目录，只查目录会导致
    # 「已建好」的假象，工具从此永久返回不可用提示
    if index_file(kb).exists():
        vectorstore = FAISS.load_local(
            str(index_dir(kb)),
            HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL
            ),
            allow_dangerous_deserialization=True
        )
    else:
        # 首次调用：build_index 内部已经建好了 embedding，直接复用它返回的
        # 向量库，不再把模型加载第二遍
        from rag.build_index import build_index

        vectorstore = build_index(kb)

    _retrievers[kb] = vectorstore.as_retriever(
        search_kwargs={
            "k": 8
        }
    )

    return _retrievers[kb]

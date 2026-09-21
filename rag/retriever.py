from rag.knowledge_base import EMBEDDING_MODEL, index_dir, index_file


# 稠密与稀疏两路各取这么多，融合后再截断回这么多
TOP_K = 8

# 按库名缓存：一个知识库一个检索器，用到哪个才加载哪个
_retrievers = {}


def _tokenize(text):
    """BM25 的分词器。

    默认的 text.split() 按空格切，对中文等于失效（整句变成一个 token），
    BM25 就只剩"整句精确匹配"这一条路；jieba 还会把英文/技术术语原样保留
    成一个 token（PagedAttention 不会被切开），而这正是加 BM25 想捞回的那类查询。
    """
    import jieba

    return [word for word in jieba.lcut(text) if word.strip()]


class _TopKRetriever:
    """EnsembleRetriever 没有 k 参数，返回的是两路并集（最多 2*TOP_K 条）；
    这里按融合排序截断到 TOP_K 条再交给调用方。"""

    def __init__(self, retriever, k):
        self._retriever = retriever
        self._k = k

    def invoke(self, query):
        return self._retriever.invoke(query)[: self._k]

def _build_hybrid_retriever(vectorstore):
    """稠密（FAISS 向量）+ 稀疏（BM25）混合检索，用 EnsembleRetriever 做 RRF 融合。

    注意 RRF 只看排名、不看分数：某一路给的低质量结果一样会被等权计入。
    权重相等是未经评测时的默认起点。
    """
    from langchain_classic.retrievers import EnsembleRetriever
    from langchain_community.retrievers import BM25Retriever

    dense = vectorstore.as_retriever(
        search_kwargs={
            "k": TOP_K
        }
    )

    # chunk 正文随索引一起存在 docstore 里，直接拿它构造 BM25，不额外落一份
    # 稀疏索引——也就不会有和稠密索引不同步的问题
    documents = list(vectorstore.docstore._dict.values())

    bm25 = BM25Retriever.from_documents(
        documents,
        preprocess_func=_tokenize,
        k=TOP_K,
    )

    ensemble = EnsembleRetriever(
        retrievers=[dense, bm25],
        weights=[0.5, 0.5],
    )

    return _TopKRetriever(ensemble, TOP_K)


def get_retriever(kb):
    """返回指定知识库的混合检索器（按库缓存）；索引不存在时先构建一次。

    langchain / embedding 模型 / jieba 都在首次调用时才加载，保证 miniCC 在未安装
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

    _retrievers[kb] = _build_hybrid_retriever(vectorstore)

    return _retrievers[kb]

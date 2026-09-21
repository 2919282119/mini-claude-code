from rag.embeddings import get_embeddings, load_local_first
from rag.knowledge_base import index_dir, index_file


# 最终交给模型的条数
TOP_K = 8

# 稠密 / 稀疏两路各自召回的条数，也就是 rerank 的候选池大小。
# EnsembleRetriever 返回的是两路并集（按 page_content 去重，所以 ≤ 2*CANDIDATE_K）。
CANDIDATE_K = 20

RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# 按库名缓存：一个知识库一个检索器，用到哪个才加载哪个
_retrievers = {}

# reranker 与知识库无关，整个进程共用一个
_reranker = None


def _tokenize(text):
    """BM25 的分词器。

    默认的 text.split() 按空格切，对中文等于失效（整句变成一个 token），
    BM25 就只剩"整句精确匹配"这一条路；jieba 还会把英文/技术术语原样保留
    成一个 token（PagedAttention 不会被切开），而这正是加 BM25 想捞回的那类查询。
    """
    import jieba

    return [word for word in jieba.lcut(text) if word.strip()]


def _get_reranker():
    """cross-encoder 重排模型，进程内单例。

    和 embedding / 索引一样把加载放在函数里：导入期不能碰这些重依赖，否则模型
    没下载或依赖没装时 miniCC 会起不来。设备显式选 cuda，不可用时回退 CPU 并把
    实际设备打出来——否则跑在哪张卡上、有没有真的用上 GPU，从输出里看不出来。

    用 fp16 权重（实测 36 条候选：1.0s，fp32 要 3.7s；权重/峰值显存 1083/1512 MB，
    fp32 是 2166/3009 MB）。CPU 回退路径同样加载 fp16，实测可以正常跑。
    不显式传 max_length——默认取模型自己的 8192，远超 chunk 长度。

    加载走 load_local_first：缓存命中时不碰网络，省掉 HF 查更新那~90 秒重试。
    """
    global _reranker

    if _reranker is None:
        import torch
        from sentence_transformers import CrossEncoder

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[rag] reranker 设备: {device}")

        _reranker = load_local_first(
            lambda local_files_only: CrossEncoder(
                RERANKER_MODEL,
                device=device,
                model_kwargs={"torch_dtype": torch.float16},
                local_files_only=local_files_only,
            )
        )

    return _reranker


class _RerankRetriever:
    """混合检索先召回候选，再交给 cross-encoder 精排，最后只返回 TOP_K 条。

    RRF 只看排名不看分数，某一路给的低质量结果一样会被等权计入；cross-encoder 直接
    对 (query, 正文) 打分，能把这类结果压下去。截断放在精排之后——给模型的上下文量
    与加 rerank 之前完全一致（都是 TOP_K 条），效果变化才能归因到重排本身。
    """

    def __init__(self, retriever, reranker, top_k):
        self._retriever = retriever
        self._reranker = reranker
        self._top_k = top_k

    def invoke(self, query):
        candidates = self._retriever.invoke(query)

        if not candidates:
            return []

        scores = self._reranker.predict(
            [(query, doc.page_content) for doc in candidates]
        )

        ranked = sorted(
            zip(candidates, scores), key=lambda pair: pair[1], reverse=True
        )

        return [doc for doc, _ in ranked[: self._top_k]]


def _build_hybrid_retriever(vectorstore):
    """稠密（FAISS 向量）+ 稀疏（BM25）混合检索，RRF 融合后再 cross-encoder 精排。

    RRF 权重取相等（0.5/0.5），因为**没有评测集时调权重就是猜**。
    """
    from langchain_classic.retrievers import EnsembleRetriever
    from langchain_community.retrievers import BM25Retriever

    dense = vectorstore.as_retriever(
        search_kwargs={
            "k": CANDIDATE_K
        }
    )

    # chunk 正文随索引一起存在 docstore 里，直接拿它构造 BM25，不额外落一份
    # 稀疏索引——也就不会有和稠密索引不同步的问题
    documents = list(vectorstore.docstore._dict.values())

    bm25 = BM25Retriever.from_documents(
        documents,
        preprocess_func=_tokenize,
        k=CANDIDATE_K,
    )

    ensemble = EnsembleRetriever(
        retrievers=[dense, bm25],
        weights=[0.5, 0.5],
    )

    return _RerankRetriever(ensemble, _get_reranker(), TOP_K)


def get_retriever(kb):
    """返回指定知识库的混合检索器（按库缓存）；索引不存在时先构建一次。

    langchain / embedding 模型 / reranker / jieba 都在首次调用时才加载，保证 miniCC
    在未安装 RAG 依赖、索引或模型缺失时仍能正常启动。
    """
    if kb in _retrievers:
        return _retrievers[kb]

    from langchain_community.vectorstores import FAISS

    # 判断索引文件而不是目录：构建中途失败会留下空目录，只查目录会导致
    # 「已建好」的假象，工具从此永久返回不可用提示
    if index_file(kb).exists():
        vectorstore = FAISS.load_local(
            str(index_dir(kb)),
            get_embeddings(),
            allow_dangerous_deserialization=True
        )
    else:
        # 首次调用：build_index 内部已经建好了 embedding，直接复用它返回的
        # 向量库，不再把模型加载第二遍
        from rag.build_index import build_index

        vectorstore = build_index(kb)

    _retrievers[kb] = _build_hybrid_retriever(vectorstore)

    return _retrievers[kb]

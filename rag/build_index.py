from rag.embeddings import get_embeddings
from rag.knowledge_base import (
    KNOWLEDGE_BASES,
    index_dir,
    pdf_path,
)


def build_index(kb):
    """把某个知识库的 PDF 加载 → 切分 → 向量化 → 保存 FAISS 索引，并返回向量库。

    返回向量库是为了让调用方复用（否则首次自动构建时 embedding 模型要
    被加载两次）。第三方依赖在函数内导入，保证本模块可被安全 import 而
    不触发重依赖加载（否则索引缺失时整个 miniCC 都起不来）。
    """
    from langchain_pymupdf4llm import PyMuPDF4LLMLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS

    documents = PyMuPDF4LLMLoader(pdf_path(kb)).load()

    chunks = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    ).split_documents(documents)

    # 共用进程内的 embedding 单例：返回的向量库会持有它，每库各建一份的话
    # 常驻内存就随知识库数量线性增长
    vectorstore = FAISS.from_documents(
        chunks,
        get_embeddings()
    )

    target = index_dir(kb)

    target.mkdir(
        parents=True,
        exist_ok=True
    )

    vectorstore.save_local(
        str(target)
    )

    print(f"RAG index saved: {target} ({len(chunks)} chunks)")

    return vectorstore


if __name__ == "__main__":
    for name in KNOWLEDGE_BASES:
        build_index(name)

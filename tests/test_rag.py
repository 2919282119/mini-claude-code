import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from rag import knowledge_base
from rag.knowledge_base import describe
from tools.local.usual.search_rag import rag_tool, search_rag


class _FakeEmbeddings(Embeddings):
    """只为让 FAISS 能建索引，不参与语义"""

    def embed_documents(self, texts):
        return [[float(len(t) % 7), 1.0, 0.5] for t in texts]

    def embed_query(self, text):
        return [float(len(text) % 7), 1.0, 0.5]


def make_fake_vectorstore(documents=None):
    """假 vectorstore。_build_hybrid_retriever 会从 docstore._dict 取 chunk 正文
    构造 BM25，所以这里的 docstore 必须是真的字典（Mock 的 values() 喂不进 BM25）。"""
    fake = mock.Mock()
    fake.docstore._dict = (
        documents
        if documents is not None
        else {"doc-1": Document(page_content="示例正文", metadata={})}
    )
    fake.as_retriever.return_value = "dense-retriever"
    return fake


class TestSearchRagDegrades(unittest.TestCase):

    def test_unknown_kb_lists_available(self):
        """回归：库名对不上时返回可用列表（让模型自纠），而不是抛异常或瞎检索"""
        with mock.patch(
            "tools.local.usual.search_rag.resolve_name", return_value=None
        ), mock.patch(
            "tools.local.usual.search_rag.describe", return_value="- kb-a: 描述 A"
        ):
            result = search_rag("不存在的库", "q")

        self.assertIsInstance(result, str)
        self.assertIn("知识库不存在", result)
        self.assertIn("kb-a", result)

    def test_returns_hint_instead_of_raising(self):
        """回归：索引缺失 / RAG 依赖未安装时返回提示文本，不能抛异常中断主循环"""
        with mock.patch(
            "tools.local.usual.search_rag.resolve_name", return_value="kb-a"
        ), mock.patch(
            "tools.local.usual.search_rag.get_retriever",
            side_effect=RuntimeError("索引没了"),
        ):
            result = search_rag("kb-a", "什么是 agent")

        self.assertIn("RAG 知识库不可用", result)
        self.assertIn("python -m rag.build_index", result)

    def test_documents_are_rendered(self):
        doc = mock.Mock()
        doc.metadata = {"source": "AI-Agents-in-Depth.pdf"}
        doc.page_content = "Agent 是一段可以自主决策的程序。"

        fake_retriever = mock.Mock()
        fake_retriever.invoke.return_value = [doc]

        with mock.patch(
            "tools.local.usual.search_rag.resolve_name", return_value="kb-a"
        ), mock.patch(
            "tools.local.usual.search_rag.get_retriever",
            return_value=fake_retriever,
        ):
            result = search_rag("kb-a", "q")

        fake_retriever.invoke.assert_called_once_with("q")
        self.assertIn("Agent 是一段可以自主决策的程序。", result)


class TestToolDeclaration(unittest.TestCase):

    def test_rag_tool_is_read_only(self):
        # 检索是只读操作，不该弹权限询问
        self.assertEqual(rag_tool.name, "rag_search")
        self.assertEqual(rag_tool.permission_level, "READ")

    def test_kb_and_query_required(self):
        properties = rag_tool.parameters["properties"]
        self.assertIn("kb", properties)
        self.assertIn("query", properties)
        self.assertEqual(set(rag_tool.parameters["required"]), {"kb", "query"})

    def test_no_top_k_parameter(self):
        # top_k 已移除，检索条数按 retriever 里的默认值来
        self.assertNotIn("top_k", rag_tool.parameters["properties"])

    def test_description_lists_knowledge_bases(self):
        # 库列表在装配时拼进 description，模型不必再额外调用一次才知道有哪些库
        self.assertIn(describe(), rag_tool.description)


class TestKnowledgeBaseManifest(unittest.TestCase):

    def test_resolve_name_normalizes(self):
        """回归：大小写 / 首尾空格 / 中文输入法打出的全角字符都要能匹配上"""
        with mock.patch.dict(
            knowledge_base.KNOWLEDGE_BASES, {"my-kb": {"file": "x.pdf"}}, clear=True
        ):
            for variant in ("my-kb", "MY-KB", "  My-Kb  ", "ｍｙ－ｋｂ"):
                self.assertEqual(knowledge_base.resolve_name(variant), "my-kb")

            self.assertIsNone(knowledge_base.resolve_name("other"))
            self.assertIsNone(knowledge_base.resolve_name(None))

    def test_missing_manifest_is_safe(self):
        with mock.patch.object(
            knowledge_base, "MANIFEST_PATH", Path("no/such/file.json")
        ):
            self.assertEqual(knowledge_base._load_manifest(), {})

    def test_broken_manifest_is_safe(self):
        """回归：manifest 写坏不能让 miniCC 起不来"""
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "knowledge_bases.json"

            for content in ("{ not json", "[1, 2]"):
                bad.write_text(content, encoding="utf-8")

                with mock.patch.object(knowledge_base, "MANIFEST_PATH", bad):
                    self.assertEqual(knowledge_base._load_manifest(), {})


class TestNoImportTimeSideEffects(unittest.TestCase):
    """回归：RAG 的加载不能发生在导入期——否则索引缺失会让整个 miniCC 起不来"""

    def test_retriever_is_lazy(self):
        import rag.retriever

        importlib.reload(rag.retriever)
        self.assertEqual(rag.retriever._retrievers, {})

    def test_retriever_imports_without_langchain(self):
        import rag.retriever

        with mock.patch.dict(
            sys.modules,
            {"langchain_community": None, "langchain_huggingface": None},
        ):
            importlib.reload(rag.retriever)

    def test_build_index_imports_without_langchain(self):
        import rag.build_index

        with mock.patch.dict(
            sys.modules,
            {"langchain_pymupdf4llm": None, "langchain_huggingface": None},
        ):
            importlib.reload(rag.build_index)

    def test_importing_tools_setup_does_not_build_index(self):
        with mock.patch(
            "rag.build_index.build_index",
            side_effect=AssertionError("导入期不该构建索引"),
        ):
            import tools.setup

            importlib.reload(tools.setup)


class TestRetrieverDefaults(unittest.TestCase):

    def reload_retriever(self):
        import rag.retriever

        importlib.reload(rag.retriever)

        return rag.retriever

    def test_wiring_dense_bm25_and_weights(self):
        """两路各自的 k、BM25 的语料与分词器、融合的权重，都要接对"""
        retriever_module = self.reload_retriever()

        documents = {
            "d1": Document(page_content="甲 PagedAttention", metadata={}),
            "d2": Document(page_content="乙", metadata={}),
        }
        fake_vectorstore = make_fake_vectorstore(documents)

        with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch.object(
            retriever_module, "index_dir"
        ), mock.patch(
            "langchain_huggingface.HuggingFaceEmbeddings"
        ), mock.patch(
            "langchain_community.vectorstores.FAISS.load_local",
            return_value=fake_vectorstore,
        ), mock.patch(
            "langchain_community.retrievers.BM25Retriever.from_documents"
        ) as fake_bm25, mock.patch(
            "langchain_classic.retrievers.EnsembleRetriever"
        ) as fake_ensemble:
            fake_file.return_value.exists.return_value = True
            retriever_module.get_retriever("kb-a")

        fake_vectorstore.as_retriever.assert_called_once_with(search_kwargs={"k": 8})

        bm25_args, bm25_kwargs = fake_bm25.call_args
        self.assertEqual(
            {doc.page_content for doc in bm25_args[0]}, {"甲 PagedAttention", "乙"}
        )
        self.assertIs(bm25_kwargs["preprocess_func"], retriever_module._tokenize)
        self.assertEqual(bm25_kwargs["k"], 8)

        ensemble_kwargs = fake_ensemble.call_args.kwargs
        self.assertEqual(len(ensemble_kwargs["retrievers"]), 2)
        self.assertEqual(ensemble_kwargs["weights"], [0.5, 0.5])

    def test_fused_result_truncated_to_top_k(self):
        """EnsembleRetriever 返回的是两路并集（最多 2*TOP_K），要截回 TOP_K"""
        retriever_module = self.reload_retriever()

        fused = [
            Document(page_content=f"第{i}段", metadata={})
            for i in range(2 * retriever_module.TOP_K)
        ]

        fake_vectorstore = make_fake_vectorstore()

        with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch.object(
            retriever_module, "index_dir"
        ), mock.patch(
            "langchain_huggingface.HuggingFaceEmbeddings"
        ), mock.patch(
            "langchain_community.vectorstores.FAISS.load_local",
            return_value=fake_vectorstore,
        ), mock.patch(
            "langchain_community.retrievers.BM25Retriever.from_documents"
        ), mock.patch(
            "langchain_classic.retrievers.EnsembleRetriever"
        ) as fake_ensemble:
            fake_file.return_value.exists.return_value = True
            fake_ensemble.return_value.invoke.return_value = fused
            retriever = retriever_module.get_retriever("kb-a")

        docs = retriever.invoke("问题")

        self.assertEqual(len(docs), retriever_module.TOP_K)
        self.assertEqual(
            [doc.page_content for doc in docs],
            [f"第{i}段" for i in range(retriever_module.TOP_K)],
        )

    def test_tokenize_keeps_technical_terms(self):
        """回归：默认的 text.split() 对中文等于失效（整句变成一个 token）。
        jieba 才能保住英文术语，而那正是加 BM25 想捞回来的那类查询。"""
        retriever_module = self.reload_retriever()

        tokens = retriever_module._tokenize("使用 PagedAttention 加速推理")

        self.assertIn("PagedAttention", tokens)
        self.assertNotIn("使用 PagedAttention 加速推理", tokens)
        self.assertTrue(all(token.strip() for token in tokens))

    def test_builds_index_when_index_file_missing(self):
        """回归：索引文件不存在时补建一次，且复用构建结果。

        判断的是 index.faiss 而不是目录——目录可能是上次构建失败留下的空壳，
        只查目录会让工具永久返回「不可用」。
        """
        retriever_module = self.reload_retriever()

        fake_vectorstore = mock.Mock()

        with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch(
            "rag.build_index.build_index", return_value=fake_vectorstore
        ) as fake_build, mock.patch(
            "langchain_huggingface.HuggingFaceEmbeddings"
        ) as fake_embeddings, mock.patch.object(
            retriever_module, "_build_hybrid_retriever", return_value="hybrid"
        ) as fake_hybrid:
            fake_file.return_value.exists.return_value = False
            result = retriever_module.get_retriever("kb-a")

        fake_build.assert_called_once_with("kb-a")
        # 复用 build_index 返回的向量库，不把 embedding 模型加载第二遍
        fake_embeddings.assert_not_called()
        fake_hybrid.assert_called_once_with(fake_vectorstore)
        self.assertEqual(result, "hybrid")

    def test_caches_per_knowledge_base(self):
        """按库名缓存：同一个库复用，不同库各自加载并构造一次"""
        retriever_module = self.reload_retriever()

        with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch.object(
            retriever_module, "index_dir"
        ), mock.patch(
            "langchain_huggingface.HuggingFaceEmbeddings"
        ), mock.patch(
            "langchain_community.vectorstores.FAISS.load_local",
            side_effect=lambda *a, **k: mock.Mock(),
        ) as fake_load, mock.patch.object(
            retriever_module,
            "_build_hybrid_retriever",
            side_effect=lambda vectorstore: mock.Mock(),
        ) as fake_hybrid:
            fake_file.return_value.exists.return_value = True

            first = retriever_module.get_retriever("kb-a")
            again = retriever_module.get_retriever("kb-a")
            other = retriever_module.get_retriever("kb-b")

        self.assertIs(first, again)
        self.assertIsNot(first, other)
        self.assertEqual(fake_load.call_count, 2)
        # BM25 + 融合只构造两次（每库一次），不是每次检索都重建
        self.assertEqual(fake_hybrid.call_count, 2)


class TestDocstoreIsReusable(unittest.TestCase):
    """护栏：BM25 的语料直接取自 FAISS 的 docstore（私有属性 _dict）。

    这是整个混合检索里唯一依赖 langchain 私有结构的地方。上游一旦改了它，
    这个测试要**明确失败**，而不是让 BM25 静默拿到空列表——那样 BM25 不再
    贡献任何召回，却没有任何报错，是最难发现的一类退化。
    """

    def test_documents_survive_save_and_load(self):
        from langchain_community.vectorstores import FAISS

        documents = [
            Document(page_content=f"第 {i} 段正文", metadata={"source": "x.pdf"})
            for i in range(5)
        ]

        with tempfile.TemporaryDirectory() as tmp:
            vectorstore = FAISS.from_documents(documents, _FakeEmbeddings())
            vectorstore.save_local(tmp)

            reloaded = FAISS.load_local(
                tmp, _FakeEmbeddings(), allow_dangerous_deserialization=True
            )

        self.assertEqual(
            {doc.page_content for doc in reloaded.docstore._dict.values()},
            {doc.page_content for doc in documents},
        )


if __name__ == "__main__":
    unittest.main()

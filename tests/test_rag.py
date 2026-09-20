import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rag import knowledge_base
from rag.knowledge_base import describe
from tools.local.usual.search_rag import rag_tool, search_rag


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

    def test_fixed_k_default(self):
        retriever_module = self.reload_retriever()

        fake_vectorstore = mock.Mock()
        fake_vectorstore.as_retriever.return_value = "retriever"

        with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch.object(
            retriever_module, "index_dir"
        ), mock.patch(
            "langchain_huggingface.HuggingFaceEmbeddings"
        ), mock.patch(
            "langchain_community.vectorstores.FAISS.load_local",
            return_value=fake_vectorstore,
        ):
            fake_file.return_value.exists.return_value = True
            result = retriever_module.get_retriever("kb-a")

        self.assertEqual(result, "retriever")
        fake_vectorstore.as_retriever.assert_called_once_with(
            search_kwargs={"k": 8}
        )

    def test_builds_index_when_index_file_missing(self):
        """回归：索引文件不存在时补建一次，且复用构建结果。

        判断的是 index.faiss 而不是目录——目录可能是上次构建失败留下的空壳，
        只查目录会让工具永久返回「不可用」。
        """
        retriever_module = self.reload_retriever()

        fake_vectorstore = mock.Mock()
        fake_vectorstore.as_retriever.return_value = "retriever"

        with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch(
            "rag.build_index.build_index", return_value=fake_vectorstore
        ) as fake_build, mock.patch(
            "langchain_huggingface.HuggingFaceEmbeddings"
        ) as fake_embeddings:
            fake_file.return_value.exists.return_value = False
            result = retriever_module.get_retriever("kb-a")

        fake_build.assert_called_once_with("kb-a")
        # 复用 build_index 返回的向量库，不把 embedding 模型加载第二遍
        fake_embeddings.assert_not_called()
        self.assertEqual(result, "retriever")

    def test_caches_per_knowledge_base(self):
        """按库名缓存：同一个库复用，不同库各自加载一次"""
        retriever_module = self.reload_retriever()

        with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch.object(
            retriever_module, "index_dir"
        ), mock.patch(
            "langchain_huggingface.HuggingFaceEmbeddings"
        ), mock.patch(
            "langchain_community.vectorstores.FAISS.load_local",
            side_effect=lambda *a, **k: mock.Mock(),
        ) as fake_load:
            fake_file.return_value.exists.return_value = True

            first = retriever_module.get_retriever("kb-a")
            again = retriever_module.get_retriever("kb-a")
            other = retriever_module.get_retriever("kb-b")

        self.assertIs(first, again)
        self.assertIsNot(first, other)
        self.assertEqual(fake_load.call_count, 2)


if __name__ == "__main__":
    unittest.main()

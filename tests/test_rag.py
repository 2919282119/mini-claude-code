import contextlib
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch
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


def fake_embeddings():
    """假 embedding 模型（测试里不该真的去读模型文件）。"""
    return mock.Mock()


def fake_reranker():
    """假 cross-encoder。测试里绝不能真的构造 CrossEncoder——那会去下 2.14GB 的模型。"""
    reranker = mock.Mock()
    reranker.predict.side_effect = lambda pairs: [0.0] * len(pairs)
    return reranker


@contextlib.contextmanager
def fake_retrieval_stack(retriever_module, fake_vectorstore):
    """把 get_retriever 一路上的重依赖（FAISS / embedding / BM25 / 融合）全换成假对象，
    只留下本次要验的接线逻辑。"""
    with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch.object(
        retriever_module, "index_dir"
    ), mock.patch.object(
        retriever_module, "get_embeddings", return_value=fake_embeddings()
    ), mock.patch(
        "langchain_community.vectorstores.FAISS.load_local",
        return_value=fake_vectorstore,
    ), mock.patch(
        "langchain_community.retrievers.BM25Retriever.from_documents"
    ) as fake_bm25, mock.patch(
        "langchain_classic.retrievers.EnsembleRetriever"
    ) as fake_ensemble:
        fake_file.return_value.exists.return_value = True
        yield fake_ensemble, fake_bm25


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

    def test_reranker_is_not_loaded_on_import(self):
        """回归：导入 rag.retriever 不能触发 reranker 加载。

        加载一次要下 2.14GB 的模型，放在导入期会让没下过模型的机器直接起不来。
        """
        import rag.retriever

        importlib.reload(rag.retriever)
        self.assertIsNone(rag.retriever._reranker)

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

        # 兜底：任何测试都不许真的构造 CrossEncoder（那会去下 2.14GB 的模型）
        patcher = mock.patch.object(
            rag.retriever, "_get_reranker", return_value=fake_reranker()
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        return rag.retriever

    def build_retriever(self, retriever_module, candidates):
        """走一遍 get_retriever，融合结果固定为 candidates。"""
        fake_vectorstore = make_fake_vectorstore()

        with fake_retrieval_stack(
            retriever_module, fake_vectorstore
        ) as (fake_ensemble, _):
            fake_ensemble.return_value.invoke.return_value = candidates
            return retriever_module.get_retriever("kb-a")

    def test_wiring_dense_bm25_reranker(self):
        """两路各自的 k、BM25 的语料与分词器、融合权重、外层 rerank 截断，都要接对"""
        retriever_module = self.reload_retriever()

        documents = {
            "d1": Document(page_content="甲 PagedAttention", metadata={}),
            "d2": Document(page_content="乙", metadata={}),
        }
        fake_vectorstore = make_fake_vectorstore(documents)

        with fake_retrieval_stack(
            retriever_module, fake_vectorstore
        ) as (fake_ensemble, fake_bm25):
            retriever = retriever_module.get_retriever("kb-a")

        candidate_k = retriever_module.CANDIDATE_K

        fake_vectorstore.as_retriever.assert_called_once_with(
            search_kwargs={"k": candidate_k}
        )

        bm25_args, bm25_kwargs = fake_bm25.call_args
        self.assertEqual(
            {doc.page_content for doc in bm25_args[0]}, {"甲 PagedAttention", "乙"}
        )
        self.assertIs(bm25_kwargs["preprocess_func"], retriever_module._tokenize)
        self.assertEqual(bm25_kwargs["k"], candidate_k)

        ensemble_kwargs = fake_ensemble.call_args.kwargs
        self.assertEqual(len(ensemble_kwargs["retrievers"]), 2)
        self.assertEqual(ensemble_kwargs["weights"], [0.5, 0.5])

        # 融合结果外面包的是 rerank，最终条数是 TOP_K 而不是候选池大小
        self.assertIsInstance(retriever, retriever_module._RerankRetriever)
        self.assertIs(retriever._retriever, fake_ensemble.return_value)
        self.assertEqual(retriever._top_k, retriever_module.TOP_K)

    def test_candidates_are_reranked_then_truncated(self):
        """截断必须发生在精排**之后**：40 条候选按 rerank 分数取前 TOP_K 条。

        这里让分数随候选顺序递增，正确答案是倒序的最后 TOP_K 条——与融合顺序
        （第0段在前）明显不同，从而证明确实用了 rerank 分数而不是原顺序。
        """
        retriever_module = self.reload_retriever()

        candidates = [
            Document(page_content=f"第{i}段", metadata={})
            for i in range(2 * retriever_module.CANDIDATE_K)
        ]

        retriever = self.build_retriever(retriever_module, candidates)
        retriever_module._get_reranker.return_value.predict.side_effect = (
            lambda pairs: list(range(len(pairs)))
        )

        docs = retriever.invoke("问题")

        top_k = retriever_module.TOP_K
        self.assertEqual(len(docs), top_k)
        self.assertEqual(
            [doc.page_content for doc in docs],
            [f"第{i}段" for i in range(len(candidates) - 1, len(candidates) - 1 - top_k, -1)],
        )

    def test_pairs_sent_to_reranker(self):
        """喂给 cross-encoder 的是 (查询, 候选正文) 对，且候选一条都不漏"""
        retriever_module = self.reload_retriever()

        candidates = [
            Document(page_content=f"第{i}段", metadata={}) for i in range(5)
        ]

        retriever = self.build_retriever(retriever_module, candidates)
        predict = retriever_module._get_reranker.return_value.predict

        retriever.invoke("什么是 ReAct")

        predict.assert_called_once_with(
            [("什么是 ReAct", doc.page_content) for doc in candidates]
        )

    def test_empty_candidates_skip_reranker(self):
        """检索不到东西时直接返回空，不把空列表喂给 cross-encoder"""
        retriever_module = self.reload_retriever()

        retriever = self.build_retriever(retriever_module, [])

        self.assertEqual(retriever.invoke("问题"), [])
        retriever_module._get_reranker.return_value.predict.assert_not_called()

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
        ) as fake_build, mock.patch.object(
            retriever_module, "get_embeddings"
        ) as fake_get_embeddings, mock.patch.object(
            retriever_module, "_build_hybrid_retriever", return_value="hybrid"
        ) as fake_hybrid:
            fake_file.return_value.exists.return_value = False
            result = retriever_module.get_retriever("kb-a")

        fake_build.assert_called_once_with("kb-a")
        # 复用 build_index 返回的向量库，不把 embedding 模型加载第二遍
        fake_get_embeddings.assert_not_called()
        fake_hybrid.assert_called_once_with(fake_vectorstore)
        self.assertEqual(result, "hybrid")

    def test_caches_per_knowledge_base(self):
        """按库名缓存：同一个库复用，不同库各自加载并构造一次"""
        retriever_module = self.reload_retriever()

        with mock.patch.object(retriever_module, "index_file") as fake_file, mock.patch.object(
            retriever_module, "index_dir"
        ), mock.patch.object(
            retriever_module, "get_embeddings", return_value=fake_embeddings()
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


class TestBuildIndexUsesSharedEmbeddings(unittest.TestCase):
    """回归：build_index 必须复用共享的 embedding 单例，不能自己 new 一份。

    这条分支只在「某个库还没建索引」时才走，索引都建好之后就是死角——普通测试
    又把它整个 mock 掉，所以单独用真代码路径盯住它。自己 new 一份的后果是每建一个
    库就多一份常驻内存，且和检索时用的不是同一个对象。
    """

    def test_reuses_the_shared_embeddings(self):
        from rag import build_index as build_index_module

        shared = _FakeEmbeddings()

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            build_index_module, "pdf_path", return_value="fake.pdf"
        ), mock.patch.object(
            build_index_module, "index_dir", return_value=Path(tmp)
        ), mock.patch(
            "langchain_pymupdf4llm.PyMuPDF4LLMLoader"
        ) as fake_loader, mock.patch.object(
            build_index_module, "get_embeddings", return_value=shared
        ) as fake_get_embeddings:
            fake_loader.return_value.load.return_value = [
                Document(page_content="ReAct 循环正文。" * 20, metadata={})
            ]

            vectorstore = build_index_module.build_index("kb-a")

            self.assertIs(vectorstore.embedding_function, shared)
            self.assertTrue(Path(tmp, "index.faiss").exists())

        fake_get_embeddings.assert_called_once()


class TestEmbeddingsAreShared(unittest.TestCase):
    """embedding 模型必须全进程共用一份。

    每库各建一份的话，常驻内存/显存随知识库数量线性增长；而所有库用的是同一个
    模型，共用不影响任何结果。
    """

    def setUp(self):
        from rag import embeddings as embeddings_module

        self.embeddings_module = embeddings_module
        self.embeddings_module._embeddings = None

        self.cls_patcher = mock.patch("langchain_huggingface.HuggingFaceEmbeddings")
        self.fake_cls = self.cls_patcher.start()
        self.addCleanup(self.cls_patcher.stop)
        self.addCleanup(setattr, self.embeddings_module, "_embeddings", None)

    def test_constructed_once_across_knowledge_bases(self):
        first = self.embeddings_module.get_embeddings()
        second = self.embeddings_module.get_embeddings()

        self.assertIs(first, second)
        self.fake_cls.assert_called_once_with(
            model_name=self.embeddings_module.EMBEDDING_MODEL,
            model_kwargs={"local_files_only": True},
        )

    def test_prefers_local_cache_without_touching_the_network(self):
        """回归：缓存命中时必须只认本地。

        不带 local_files_only 时 huggingface_hub 会为每个文件发 HEAD 查更新，
        网络不通就重试 5 次退避——实测一次加载白等约 90 秒。
        """
        self.embeddings_module.get_embeddings()

        kwargs = self.fake_cls.call_args.kwargs
        self.assertEqual(kwargs["model_kwargs"], {"local_files_only": True})

    def test_falls_back_to_download_when_not_cached(self):
        """离线优先不能把首次使用堵死：本地没有时要回退到联网下载"""
        fallback = fake_embeddings()
        self.fake_cls.side_effect = [OSError("本地没有"), fallback]

        result = self.embeddings_module.get_embeddings()

        self.assertIs(result, fallback)
        first, second = self.fake_cls.call_args_list
        self.assertEqual(first.kwargs["model_kwargs"], {"local_files_only": True})
        self.assertEqual(second.kwargs["model_kwargs"], {"local_files_only": False})

    def test_import_does_not_load_the_model(self):
        importlib.reload(self.embeddings_module)

        self.assertIsNone(self.embeddings_module._embeddings)
        self.fake_cls.assert_not_called()


class TestReranker(unittest.TestCase):
    """reranker 的加载策略：懒加载、进程内单例、设备显式选择。

    CrossEncoder 被整个换成假对象——真的构造一次会去下 2.14GB 的模型。
    """

    def setUp(self):
        import rag.retriever

        self.retriever_module = rag.retriever
        self.retriever_module._reranker = None

        self.cls_patcher = mock.patch("sentence_transformers.CrossEncoder")
        self.fake_cross_encoder = self.cls_patcher.start()
        self.addCleanup(self.cls_patcher.stop)
        self.addCleanup(setattr, self.retriever_module, "_reranker", None)

        # 静音设备行输出
        self.print_patcher = mock.patch("builtins.print")
        self.fake_print = self.print_patcher.start()
        self.addCleanup(self.print_patcher.stop)

    def test_constructed_once_across_calls(self):
        """模型与知识库无关，整个进程只构造一次"""
        first = self.retriever_module._get_reranker()
        second = self.retriever_module._get_reranker()

        self.assertIs(first, second)
        self.fake_cross_encoder.assert_called_once()
        self.assertEqual(
            self.fake_cross_encoder.call_args.args[0],
            self.retriever_module.RERANKER_MODEL,
        )

    def test_uses_fp16_weights(self):
        """fp16 是实测选的：36 条候选 1.0s vs fp32 3.7s，显存也减半"""
        self.retriever_module._get_reranker()

        self.assertEqual(
            self.fake_cross_encoder.call_args.kwargs["model_kwargs"],
            {"torch_dtype": torch.float16},
        )

    def test_prefers_local_cache(self):
        """回归：reranker 缓存命中时同样不能去联网查更新（实测省下~90 秒重试）"""
        self.retriever_module._get_reranker()

        self.assertTrue(self.fake_cross_encoder.call_args.kwargs["local_files_only"])

    def test_falls_back_to_download_when_not_cached(self):
        """首次使用（模型没下过）时仍要能联网下载"""
        self.fake_cross_encoder.side_effect = [OSError("本地没有"), mock.Mock()]

        self.retriever_module._get_reranker()

        first, second = self.fake_cross_encoder.call_args_list
        self.assertTrue(first.kwargs["local_files_only"])
        self.assertFalse(second.kwargs["local_files_only"])

    def test_uses_cuda_when_available(self):
        with mock.patch("torch.cuda.is_available", return_value=True):
            self.retriever_module._get_reranker()

        self.assertEqual(self.fake_cross_encoder.call_args.kwargs["device"], "cuda")

    def test_falls_back_to_cpu(self):
        """没有 CUDA 时回退 CPU，而不是崩掉"""
        with mock.patch("torch.cuda.is_available", return_value=False):
            self.retriever_module._get_reranker()

        self.assertEqual(self.fake_cross_encoder.call_args.kwargs["device"], "cpu")

    def test_prints_the_device_actually_used(self):
        """设备必须可观测：跑在 CPU 还是 GPU 上，不能只靠代码里看不出的隐式行为"""
        with mock.patch("torch.cuda.is_available", return_value=True):
            self.retriever_module._get_reranker()

        self.assertEqual(
            self.fake_print.call_args.args, ("[rag] reranker 设备: cuda",)
        )


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

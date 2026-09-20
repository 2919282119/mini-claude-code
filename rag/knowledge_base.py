import json
import unicodedata
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

RAG_FILES_DIR = BASE_DIR / "static" / "rag_files"
MANIFEST_PATH = RAG_FILES_DIR / "knowledge_bases.json"
INDEX_ROOT = BASE_DIR / "rag" / "rag_index"

# 索引与查询必须用同一个模型，否则向量空间不一致、检索结果无意义
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


def _load_manifest():
    """读取 knowledge_bases.json；缺失或格式损坏时返回空字典。

    本模块在 miniCC 启动时被导入，所以这里绝不能抛异常——配置写错不该让
    整个程序起不来。
    """
    try:
        with MANIFEST_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


KNOWLEDGE_BASES = _load_manifest()


def resolve_name(kb):
    """把用户/模型给的库名归一化成规范库名；找不到返回 None。

    归一化后再比：模型可能带大小写差异、中文输入法容易打出全角字符。
    """
    if not isinstance(kb, str):
        return None

    target = _normalize(kb)

    for name in KNOWLEDGE_BASES:
        if _normalize(name) == target:
            return name

    return None


def _normalize(text):
    return unicodedata.normalize("NFKC", text).strip().casefold()


def pdf_path(kb):
    return RAG_FILES_DIR / KNOWLEDGE_BASES[kb]["file"]


def index_dir(kb):
    return INDEX_ROOT / kb


def index_file(kb):
    # FAISS.load_local 默认 index_name="index"，读的就是这个文件
    return index_dir(kb) / "index.faiss"


def describe():
    """生成给 LLM 看的知识库列表（拼进 rag_search 的 description）。"""
    if not KNOWLEDGE_BASES:
        return "（当前没有配置知识库）"

    lines = []

    for name, item in KNOWLEDGE_BASES.items():
        lines.append(f"- {name}: {item.get('description', '')}")

    return "\n".join(lines)

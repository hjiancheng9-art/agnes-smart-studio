"""Unit tests for core/rag.py — TF-IDF 语义检索引擎。

rag.py 是无外部依赖的纯数学引擎（docstring 明确声明 "No external dependencies"），
用 TF-IDF + 余弦相似度做代码语义搜索。

覆盖策略：
- 纯逻辑函数（_tokenize / _cosine_similarity / _query_vector / search）直接测。
- 通过手动注入 `engine.index` 绕过 `index_project()`（会扫真实文件系统 + 写
  模块级 INDEX_FILE 缓存），保证测试隔离。
- index_project / _try_load_cache / _save_cache 用 tmp_path + monkeypatch
  INDEX_FILE 做有限覆盖（验证扫描 + 缓存读写往返）。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.rag import INDEX_FILE, RAGEngine


# ── _tokenize ─────────────────────────────────────────────────────


def test_tokenize_splits_english_words():
    """英文按词边界分词。"""
    e = RAGEngine()
    assert e._tokenize("generate video") == ["generate", "video"]


def test_tokenize_keeps_identifiers_with_digits_and_underscore():
    """标识符（含数字/下划线）应作为整体保留。"""
    e = RAGEngine()
    tokens = e._tokenize("foo_bar baz123")
    assert "foo_bar" in tokens
    assert "baz123" in tokens


def test_tokenize_drops_single_char_tokens():
    """单字符 token 被过滤（< 2 字符）。"""
    e = RAGEngine()
    tokens = e._tokenize("a b c word")
    assert "a" not in tokens
    assert "b" not in tokens
    assert "c" not in tokens
    assert "word" in tokens


def test_tokenize_lowercases():
    """分词应小写化（大小写不敏感匹配）。"""
    e = RAGEngine()
    tokens = e._tokenize("Hello WORLD")
    assert tokens == ["hello", "world"]


def test_tokenize_empty_string():
    """空串返回空列表。"""
    assert RAGEngine()._tokenize("") == []


def test_tokenize_pure_numbers_dropped():
    """纯数字（不以字母/下划线开头）不应成为 token。"""
    e = RAGEngine()
    tokens = e._tokenize("123 456")
    assert tokens == []


def test_tokenize_chinese_continuous_run():
    """中文连续字符段应作为一个 token 保留（>=2 字符通过过滤）。"""
    e = RAGEngine()
    tokens = e._tokenize("图像生成")
    # 中文连续段作为整体
    assert "图像生成" in tokens


# ── _cosine_similarity ────────────────────────────────────────────


def test_cosine_identical_vectors_is_one():
    """完全相同的向量相似度应为 1.0。"""
    e = RAGEngine()
    v = {"a": 0.5, "b": 0.5}
    assert e._cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_zero_vector_returns_zero():
    """任一为零向量 → 返回 0.0（防除零）。"""
    e = RAGEngine()
    assert e._cosine_similarity({}, {"a": 1.0}) == 0.0
    assert e._cosine_similarity({"a": 1.0}, {}) == 0.0
    assert e._cosine_similarity({}, {}) == 0.0


def test_cosine_orthogonal_vectors_is_zero():
    """无共同维度的两向量 → 点积为 0 → 相似度 0.0。"""
    e = RAGEngine()
    a = {"x": 1.0}
    b = {"y": 1.0}
    assert e._cosine_similarity(a, b) == 0.0


def test_cosine_symmetric():
    """相似度应对称（cos(a,b) == cos(b,a)）。"""
    e = RAGEngine()
    a = {"x": 1.0, "y": 2.0}
    b = {"x": 2.0, "z": 1.0}
    assert e._cosine_similarity(a, b) == pytest.approx(e._cosine_similarity(b, a))


def test_cosine_value_range():
    """非负向量余弦相似度应在 [0, 1]。"""
    e = RAGEngine()
    a = {"x": 1.0, "y": 1.0}
    b = {"x": 1.0, "y": 0.0}
    sim = e._cosine_similarity(a, b)
    assert 0.0 <= sim <= 1.0


# ── _query_vector ─────────────────────────────────────────────────


def test_query_vector_uses_idf_from_index():
    """查询向量的权重 = tf * idf（idf 取自 index）。

    单 token 查询：tf = 1/1 = 1.0，故权重 = idf。
    """
    e = RAGEngine()
    e.index = {"documents": {}, "idf": {"video": 2.5}, "built_at": 0}
    qv = e._query_vector("video")
    assert qv == {"video": 2.5}


def test_query_vector_unknown_term_defaults_idf_to_one():
    """查询词不在 idf 表中时，idf 回退为 1.0。"""
    e = RAGEngine()
    e.index = {"documents": {}, "idf": {}, "built_at": 0}
    qv = e._query_vector("novelterm")
    assert qv == {"novelterm": 1.0}


def test_query_vector_empty_query_returns_empty():
    """空查询返回空向量。"""
    e = RAGEngine()
    e.index = {"documents": {}, "idf": {}, "built_at": 0}
    assert e._query_vector("") == {}


# ── search（注入 index，绕过 index_project） ──────────────────────


def _inject_index(engine: RAGEngine, docs: dict, idf: dict | None = None):
    """直接注入 index，避免触发 index_project 扫盘。"""
    if idf is None:
        all_terms = set()
        for d in docs.values():
            all_terms.update(d.get("tf", {}).keys())
        idf = {t: 1.0 for t in all_terms}
    engine.index = {
        "documents": docs,
        "idf": idf,
        "built_at": 0,
        "doc_count": len(docs),
    }


def test_search_returns_ranked_results():
    """search 应按相似度降序返回。"""
    e = RAGEngine()
    _inject_index(e, {
        "a.py": {"tf": {"video": 3, "image": 1}, "token_count": 4},
        "b.py": {"tf": {"video": 1, "audio": 3}, "token_count": 4},
    }, idf={"video": 1.0, "image": 1.0, "audio": 1.0})
    results = e.search("video", top_k=10)
    assert len(results) == 2
    # a.py 的 video tf 更高 → 排第一
    assert results[0]["file"] == "a.py"
    assert results[0]["score"] >= results[1]["score"]


def test_search_filters_zero_score_docs():
    """相似度为 0 的文档（无共同词）不出现在结果中。"""
    e = RAGEngine()
    _inject_index(e, {
        "match.py": {"tf": {"video": 2}, "token_count": 2},
        "unrelated.py": {"tf": {"database": 5}, "token_count": 5},
    }, idf={"video": 1.0, "database": 1.0})
    results = e.search("video")
    files = {r["file"] for r in results}
    assert "match.py" in files
    assert "unrelated.py" not in files


def test_search_respects_top_k():
    """top_k 限制返回数量。"""
    e = RAGEngine()
    _inject_index(e, {
        f"f{i}.py": {"tf": {"video": 1}, "token_count": 1}
        for i in range(5)
    }, idf={"video": 1.0})
    results = e.search("video", top_k=2)
    assert len(results) == 2


def test_search_result_shape():
    """每条结果含 file / score / token_count。"""
    e = RAGEngine()
    _inject_index(e, {
        "a.py": {"tf": {"video": 1}, "token_count": 1},
    }, idf={"video": 1.0})
    results = e.search("video")
    assert len(results) == 1
    r = results[0]
    assert set(["file", "score", "token_count"]) <= set(r)
    assert r["file"] == "a.py"


def test_search_score_is_rounded():
    """score 应为 round 到 4 位小数。"""
    e = RAGEngine()
    _inject_index(e, {
        "a.py": {"tf": {"video": 1}, "token_count": 1},
    }, idf={"video": 1.0})
    r = e.search("video")[0]
    # round(x, 4) 后小数位不超过 4
    assert round(r["score"], 4) == r["score"]


# ── index_project（tmp_path + monkeypatch INDEX_FILE） ────────────


def test_index_project_scans_source_files(tmp_path, monkeypatch):
    """index_project 应扫描 .py/.md 等源文件并建索引。"""
    # 隔离 INDEX_FILE 到 tmp_path，避免污染真实 output/rag_index.json
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("def foo():\n    return 'video generate'", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Video\n生成视频", encoding="utf-8")
    (tmp_path / "skip.bin").write_text("binary", encoding="utf-8")  # 非源文件

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    docs = e.index["documents"]
    assert "a.py" in docs
    assert "b.md" in docs
    assert "skip.bin" not in docs


def test_index_project_skips_blocklisted_dirs(tmp_path, monkeypatch):
    """__pycache__ / .git / node_modules 等应被跳过。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("keep this", encoding="utf-8")
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "hidden.py").write_text("should skip", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    assert "a.py" in e.index["documents"]
    assert str(pycache / "hidden.py") not in e.index["documents"]
    assert not any("__pycache__" in p for p in e.index["documents"])


def test_index_project_cache_roundtrip(tmp_path, monkeypatch):
    """_save_cache → _try_load_cache 往返应恢复 index。"""
    cache = tmp_path / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)
    (tmp_path / "a.py").write_text("video content", encoding="utf-8")

    e1 = RAGEngine(root=tmp_path)
    e1.index_project(force=True)
    assert cache.exists()  # 缓存已写入

    # 新实例从缓存加载（未过 TTL）
    e2 = RAGEngine(root=tmp_path)
    assert e2._try_load_cache() is True
    assert "a.py" in e2.index["documents"]


def test_index_project_cache_expired_returns_false(tmp_path, monkeypatch):
    """缓存超过 1 小时 TTL → _try_load_cache 返回 False。"""
    import json as _json
    cache = tmp_path / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)
    # 写一个 built_at = 0（很久以前）的缓存
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(_json.dumps({"documents": {}, "idf": {}, "built_at": 0}), encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    assert e._try_load_cache() is False


def test_index_project_cache_missing_returns_false(tmp_path, monkeypatch):
    """缓存文件不存在 → _try_load_cache 返回 False。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "nope.json")
    e = RAGEngine(root=tmp_path)
    assert e._try_load_cache() is False

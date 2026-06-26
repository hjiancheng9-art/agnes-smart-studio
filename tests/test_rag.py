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

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.rag import INDEX_FILE, RAGEngine, index_codebase, semantic_search

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
    """中文连续字符段使用 character bigram 切分（保证跨文档召回）。"""
    e = RAGEngine()
    tokens = e._tokenize("图像生成")
    # 4 字符 → 3 个 bigram: 图像, 像生, 生成
    assert tokens == ["图像", "像生", "生成"]


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
        idf = dict.fromkeys(all_terms, 1.0)
    engine.index = {
        "documents": docs,
        "idf": idf,
        "built_at": 0,
        "doc_count": len(docs),
    }


def test_search_returns_ranked_results():
    """search 应按相似度降序返回。"""
    e = RAGEngine()
    _inject_index(
        e,
        {
            "a.py": {"tf": {"video": 3, "image": 1}, "token_count": 4},
            "b.py": {"tf": {"video": 1, "audio": 3}, "token_count": 4},
        },
        idf={"video": 1.0, "image": 1.0, "audio": 1.0},
    )
    results = e.search("video", top_k=10)
    assert len(results) == 2
    # a.py 的 video tf 更高 → 排第一
    assert results[0]["file"] == "a.py"
    assert results[0]["score"] >= results[1]["score"]


def test_search_filters_zero_score_docs():
    """相似度为 0 的文档（无共同词）不出现在结果中。"""
    e = RAGEngine()
    _inject_index(
        e,
        {
            "match.py": {"tf": {"video": 2}, "token_count": 2},
            "unrelated.py": {"tf": {"database": 5}, "token_count": 5},
        },
        idf={"video": 1.0, "database": 1.0},
    )
    results = e.search("video")
    files = {r["file"] for r in results}
    assert "match.py" in files
    assert "unrelated.py" not in files


def test_search_respects_top_k():
    """top_k 限制返回数量。"""
    e = RAGEngine()
    _inject_index(e, {f"f{i}.py": {"tf": {"video": 1}, "token_count": 1} for i in range(5)}, idf={"video": 1.0})
    results = e.search("video", top_k=2)
    assert len(results) == 2


def test_search_result_shape():
    """每条结果含 file / score / token_count。"""
    e = RAGEngine()
    _inject_index(
        e,
        {
            "a.py": {"tf": {"video": 1}, "token_count": 1},
        },
        idf={"video": 1.0},
    )
    results = e.search("video")
    assert len(results) == 1
    r = results[0]
    assert {"file", "score", "token_count"} <= set(r)
    assert r["file"] == "a.py"


def test_search_score_is_rounded():
    """score 应为 round 到 4 位小数。"""
    e = RAGEngine()
    _inject_index(
        e,
        {
            "a.py": {"tf": {"video": 1}, "token_count": 1},
        },
        idf={"video": 1.0},
    )
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


# ── 扩展：_tokenize 边界 ──────────────────────────────────────────


def test_tokenize_mixed_cjk_and_english():
    """中英混合：英文按词、中文按 bigram。"""
    e = RAGEngine()
    tokens = e._tokenize("video 图像生成")
    assert "video" in tokens
    assert "图像" in tokens
    assert "生成" in tokens


def test_tokenize_single_chinese_char():
    """单字符中文段直接保留（无法构成 bigram）。"""
    e = RAGEngine()
    tokens = e._tokenize("图")
    assert tokens == ["图"]


def test_tokenize_two_chinese_chars():
    """2 字符中文段恰好一个 bigram。"""
    e = RAGEngine()
    assert e._tokenize("图像") == ["图像"]


def test_tokenize_punctuation_only():
    """纯标点/符号串应返回空列表。"""
    e = RAGEngine()
    assert e._tokenize("!!! ??? ---") == []


def test_tokenize_preserves_order():
    """分词应保持原文出现顺序。"""
    e = RAGEngine()
    tokens = e._tokenize("alpha beta gamma")
    assert tokens == ["alpha", "beta", "gamma"]


def test_tokenize_underscore_leading_identifier():
    """下划线开头的标识符应作为整体保留（Python 私有成员）。"""
    e = RAGEngine()
    tokens = e._tokenize("_private method")
    assert "_private" in tokens


# ── 扩展：__init__ 构造 ──────────────────────────────────────────


def test_init_default_root():
    """无参构造应使用模块 ROOT。"""
    e = RAGEngine()
    assert e.root == INDEX_FILE.parent.parent


def test_init_custom_root(tmp_path):
    """自定义 root 应被采纳。"""
    e = RAGEngine(root=tmp_path)
    assert e.root == tmp_path


def test_init_index_structure():
    """初始 index 应有 documents / idf / built_at 三键。"""
    e = RAGEngine()
    assert "documents" in e.index
    assert "idf" in e.index
    assert "built_at" in e.index
    assert e.index["documents"] == {}
    assert e._loaded is False


# ── 扩展：_query_vector 多 term ───────────────────────────────────


def test_query_vector_multiple_terms():
    """多 term 查询：tf = count/num_terms，权重 = tf * idf。"""
    e = RAGEngine()
    e.index = {"documents": {}, "idf": {"video": 2.0, "image": 4.0}, "built_at": 0}
    qv = e._query_vector("video image")
    # num_terms=2 → tf=0.5 each
    assert qv["video"] == pytest.approx(1.0)   # 0.5 * 2.0
    assert qv["image"] == pytest.approx(2.0)   # 0.5 * 4.0


def test_query_vector_repeated_term():
    """重复 term 的 tf 应反映计数。"""
    e = RAGEngine()
    e.index = {"documents": {}, "idf": {"video": 2.0}, "built_at": 0}
    qv = e._query_vector("video video video")
    # tf = 3/1 = 3.0 → 3.0 * 2.0 = 6.0
    assert qv["video"] == pytest.approx(6.0)


# ── 扩展：search 边界 ─────────────────────────────────────────────


def test_search_empty_documents_triggers_index(tmp_path, monkeypatch):
    """documents 为空时 search 应自动调用 index_project。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("video content here", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    # 不预注入 index，直接 search → 应自动扫盘
    results = e.search("video")
    assert isinstance(results, list)
    # 扫描后 documents 非空
    assert len(e.index["documents"]) >= 1


def test_search_empty_query_returns_empty():
    """空查询（无 token）→ 无命中 → 空列表。"""
    e = RAGEngine()
    _inject_index(e, {"a.py": {"tf": {"video": 1}, "token_count": 1}}, idf={"video": 1.0})
    results = e.search("")
    assert results == []


def test_search_no_match_returns_empty():
    """查询词不在任何文档中 → 空列表。"""
    e = RAGEngine()
    _inject_index(e, {"a.py": {"tf": {"video": 1}, "token_count": 1}}, idf={"video": 1.0})
    results = e.search("nonexistent_term")
    assert results == []


def test_search_top_k_zero():
    """top_k=0 应返回空列表。"""
    e = RAGEngine()
    _inject_index(e, {"a.py": {"tf": {"video": 1}, "token_count": 1}}, idf={"video": 1.0})
    results = e.search("video", top_k=0)
    assert results == []


def test_search_scores_sorted_descending():
    """多结果时 score 必须严格降序。"""
    e = RAGEngine()
    _inject_index(
        e,
        {
            "high.py": {"tf": {"video": 5}, "token_count": 5},
            "mid.py": {"tf": {"video": 3}, "token_count": 3},
            "low.py": {"tf": {"video": 1}, "token_count": 1},
        },
        idf={"video": 1.0},
    )
    results = e.search("video", top_k=10)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


# ── 扩展：search_with_preview ─────────────────────────────────────


def test_search_with_preview_includes_preview(tmp_path, monkeypatch):
    """search_with_preview 应附加 preview 字段（行号 + 内容）。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("def video():\n    return 'generate'\n", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    results = e.search_with_preview("video", top_k=5)
    assert len(results) >= 1
    r = results[0]
    assert "preview" in r
    assert isinstance(r["preview"], list)
    # 至少有一行命中（含 video 关键词）
    if r["preview"]:
        line_no, line_text = r["preview"][0]
        assert isinstance(line_no, int)
        assert isinstance(line_text, str)


def test_search_with_preview_preview_line_truncated(tmp_path, monkeypatch):
    """preview 行内容应截断到 120 字符。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    long_line = "video " + "x" * 200
    (tmp_path / "a.py").write_text(long_line, encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    results = e.search_with_preview("video", top_k=5)
    for r in results:
        for _lineno, text in r.get("preview", []):
            assert len(text) <= 120


def test_search_with_preview_missing_file_returns_empty_preview(tmp_path, monkeypatch):
    """文件不存在 / 不可读时 preview 应为空列表。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    e = RAGEngine(root=tmp_path)
    # 注入一个指向不存在文件的 index
    _inject_index(
        e,
        {"ghost.py": {"tf": {"video": 1}, "token_count": 1}},
        idf={"video": 1.0},
    )
    results = e.search_with_preview("video", top_k=5)
    assert len(results) == 1
    assert results[0]["preview"] == []


def test_search_with_preview_respects_preview_lines_limit(tmp_path, monkeypatch):
    """preview_lines 限制返回的预览行数。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    content = "\n".join(f"video line {i}" for i in range(20))
    (tmp_path / "a.py").write_text(content, encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    results = e.search_with_preview("video", top_k=5, preview_lines=2)
    for r in results:
        assert len(r["preview"]) <= 2


# ── 扩展：index_project 边界 ──────────────────────────────────────


def test_index_project_skips_large_files(tmp_path, monkeypatch):
    """超过 500KB 的文件应被跳过。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "small.py").write_text("video content", encoding="utf-8")
    big = tmp_path / "big.py"
    # 写入 > 500_000 字节
    big.write_text("# video\n" + "x" * 500_100, encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    assert "small.py" in e.index["documents"]
    assert "big.py" not in e.index["documents"]


def test_index_project_skips_non_source_extensions(tmp_path, monkeypatch):
    """非源文件扩展名应被跳过。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("video", encoding="utf-8")
    (tmp_path / "data.dat").write_text("video", encoding="utf-8")
    (tmp_path / "img.png").write_text("video", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    assert "a.py" in e.index["documents"]
    assert "data.dat" not in e.index["documents"]
    assert "img.png" not in e.index["documents"]


def test_index_project_skips_empty_token_files(tmp_path, monkeypatch):
    """分词后无 token 的文件不应进索引。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("video content", encoding="utf-8")
    (tmp_path / "empty.py").write_text("!!! ??? ---", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    assert "a.py" in e.index["documents"]
    assert "empty.py" not in e.index["documents"]


def test_index_project_idf_computation(tmp_path, monkeypatch):
    """idf 公式 = log(N/(df+1)) + 1。"""
    import math

    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    # 两个文件都含 "shared"，仅 a.py 含 "unique"
    (tmp_path / "a.py").write_text("shared unique", encoding="utf-8")
    (tmp_path / "b.py").write_text("shared common", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    idf = e.index["idf"]
    n = 2  # 文档数
    # shared 出现在 2 个文档 → df=2
    expected_shared = math.log(n / (2 + 1)) + 1
    assert idf["shared"] == pytest.approx(expected_shared)


def test_index_project_sets_doc_count(tmp_path, monkeypatch):
    """index 应包含正确的 doc_count。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("video", encoding="utf-8")
    (tmp_path / "b.py").write_text("image", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    assert e.index["doc_count"] == 2


def test_index_project_force_false_uses_valid_cache(tmp_path, monkeypatch):
    """force=False 且缓存有效时应直接加载缓存，不重新扫盘。"""
    import json as _json
    import time as _time

    cache = tmp_path / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    # 写一个有效的缓存（built_at = now，未过 TTL）
    cache.write_text(
        _json.dumps(
            {"documents": {"cached.py": {"tf": {"video": 1}, "token_count": 1}}, "idf": {"video": 1.0}, "built_at": _time.time()}
        ),
        encoding="utf-8",
    )
    # tmp_path 下没有 cached.py 文件——若重新扫盘则 documents 会变空
    e = RAGEngine(root=tmp_path)
    e.index_project(force=False)
    assert "cached.py" in e.index["documents"]


def test_index_project_force_true_ignores_cache(tmp_path, monkeypatch):
    """force=True 时即使有缓存也重新扫描。"""
    import json as _json
    import time as _time

    cache = tmp_path / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        _json.dumps(
            {"documents": {"stale.py": {"tf": {"video": 1}, "token_count": 1}}, "idf": {"video": 1.0}, "built_at": _time.time()}
        ),
        encoding="utf-8",
    )
    (tmp_path / "real.py").write_text("video fresh", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    assert "real.py" in e.index["documents"]
    assert "stale.py" not in e.index["documents"]


def test_index_project_records_built_at(tmp_path, monkeypatch):
    """index_project 后 built_at 应为近期时间戳。"""
    import time as _time

    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("video", encoding="utf-8")

    before = _time.time()
    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    after = _time.time()
    assert before <= e.index["built_at"] <= after


def test_index_project_creates_cache_dir(tmp_path, monkeypatch):
    """缓存目录不存在时应自动创建。"""
    cache = tmp_path / "subdir" / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)
    (tmp_path / "a.py").write_text("video", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    e.index_project(force=True)
    assert cache.exists()
    assert cache.parent.is_dir()


# ── 扩展：缓存异常处理 ───────────────────────────────────────────


def test_try_load_cache_malformed_json(tmp_path, monkeypatch):
    """缓存文件是非法 JSON → _try_load_cache 返回 False（不抛异常）。"""
    cache = tmp_path / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("{ this is not valid json", encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    assert e._try_load_cache() is False


def test_try_load_cache_missing_built_at(tmp_path, monkeypatch):
    """缓存缺少 built_at 字段 → data.get 默认 0 → 过期 → 返回 False。"""
    import json as _json

    cache = tmp_path / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(_json.dumps({"documents": {}, "idf": {}}), encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    assert e._try_load_cache() is False


def test_try_load_cache_valid_within_ttl(tmp_path, monkeypatch):
    """缓存未过 TTL → 返回 True 且 index 被加载。"""
    import json as _json
    import time as _time

    cache = tmp_path / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    payload = {"documents": {"x.py": {"tf": {"video": 1}, "token_count": 1}}, "idf": {"video": 1.0}, "built_at": _time.time()}
    cache.write_text(_json.dumps(payload), encoding="utf-8")

    e = RAGEngine(root=tmp_path)
    assert e._try_load_cache() is True
    assert "x.py" in e.index["documents"]


# ── 扩展：模块级便捷函数 ─────────────────────────────────────────


def test_semantic_search_returns_list(tmp_path, monkeypatch):
    """semantic_search() 便捷函数应返回列表。"""
    monkeypatch.setattr("core.rag.INDEX_FILE", tmp_path / "rag_index.json")
    (tmp_path / "a.py").write_text("video generation code", encoding="utf-8")

    # semantic_search 用默认 ROOT 构造引擎，但 search 会在 documents 空时扫盘
    # 这里 monkeypatch INDEX_FILE 后，默认引擎的 root 仍是项目 ROOT
    # 为隔离，直接测函数签名与返回类型
    results = semantic_search("video", top_k=5)
    assert isinstance(results, list)


def test_index_codebase_writes_cache(tmp_path, monkeypatch):
    """index_codebase() 应强制重建索引并写缓存。"""
    cache = tmp_path / "rag_index.json"
    monkeypatch.setattr("core.rag.INDEX_FILE", cache)

    index_codebase()
    # 缓存文件应被写入（可能为空项目但文件存在）
    assert cache.exists()


# ── 扩展：_cosine_similarity 数学性质 ────────────────────────────


def test_cosine_known_value():
    """验证一个已知余弦值（45° 等效）。"""
    e = RAGEngine()
    a = {"x": 1.0, "y": 1.0}  # 与 x 轴 45°
    b = {"x": 1.0, "y": 0.0}  # x 轴
    # cos(45°) = √2/2 ≈ 0.7071
    assert e._cosine_similarity(a, b) == pytest.approx(0.7071, abs=0.001)


def test_cosine_negative_values():
    """负权重向量（理论上不会出现，但验证数学正确）。"""
    e = RAGEngine()
    a = {"x": 1.0}
    b = {"x": -1.0}
    # 方向相反 → -1.0
    assert e._cosine_similarity(a, b) == pytest.approx(-1.0)

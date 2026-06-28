"""Standalone RAG rebuild - no cached imports, pure inline logic."""

import math
import os
import re
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX_FILE = ROOT / "output" / "rag_index.json"


def _tokenize(text):
    text_lower = text.lower()
    tokens = []
    for segment in re.split(r"([\u4e00-\u9fff]+)", text_lower):
        if not segment:
            continue
        if re.search(r"[\u4e00-\u9fff]", segment):
            n = len(segment)
            if n == 1:
                tokens.append(segment)
            else:
                tokens.extend(segment[i : i + 2] for i in range(n - 1))
        else:
            tokens.extend(t for t in re.findall(r"[a-zA-Z_]\w+", segment) if len(t) >= 2)
    return tokens


def _index():
    docs = {}
    df = Counter()
    source_exts = {
        ".py",
        ".md",
        ".json",
        ".js",
        ".ts",
        ".html",
        ".css",
        ".toml",
        ".yaml",
        ".yml",
        ".sh",
        ".bat",
        ".txt",
        ".cfg",
        ".ini",
        ".env",
        ".xml",
        ".sql",
    }
    skip_dirs = {
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        "dist",
        "build",
        "*.egg-info",
    }
    files = list(ROOT.rglob("*"))
    for f in files:
        if any(skip in f.parts for skip in skip_dirs):
            continue
        if f.suffix.lower() not in source_exts:
            continue
        if f.stat().st_size > 500_000:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        tokens = _tokenize(content)
        if not tokens:
            continue
        rel = str(f.relative_to(ROOT))
        tf = Counter(tokens)
        docs[rel] = {"tf": dict(tf), "token_count": len(tokens)}
        for token in set(tokens):
            df[token] += 1
    num_docs = max(len(docs), 1)
    idf = {t: math.log(num_docs / (df[t] + 1)) + 1 for t in df}
    return {
        "documents": docs,
        "idf": idf,
        "built_at": time.time(),
        "doc_count": len(docs),
    }


def _search(index, query, top_k=10):
    q_tokens = _tokenize(query)
    q_tf = Counter(q_tokens)
    q_vec = {}
    for term, count in q_tf.items():
        q_vec[term] = (count / max(len(q_tf), 1)) * index["idf"].get(term, 1.0)
    scores = []
    for doc_path, doc_info in index["documents"].items():
        dv = doc_info.get("tf", {})
        dot = sum(q_vec.get(k, 0) * dv.get(k, 0) for k in set(q_vec) | set(dv))
        mag_a = math.sqrt(sum(v**2 for v in q_vec.values()))
        mag_b = math.sqrt(sum(v**2 for v in dv.values()))
        score = dot / (mag_a * mag_b) if mag_a and mag_b else 0
        if score > 0:
            scores.append((doc_path, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [{"file": p, "score": round(s, 4)} for p, s in scores[:top_k]]


# --- Run ---
tokens_test = _tokenize("错误处理与重试机制")
check_bigram_ok = any(len(t) == 2 and "\u4e00" <= t[0] <= "\u9fff" for t in tokens_test)
fout_path = ROOT / "output" / "_rebuild_log.txt"
os.makedirs(ROOT / "output", exist_ok=True)
summary_lines = []
summary_lines.append(f"Tokenizer test: {tokens_test}")
summary_lines.append(f"Bigram OK: {check_bigram_ok}")
summary_lines.append("Rebuilding...")
data = _index()
summary_lines.append(f"Docs indexed: {data['doc_count']}, Terms: {len(data['idf'])}")
cjk_terms = [k for k in data["idf"] if "\u4e00" <= k[0] <= "\u9fff"][:15]
summary_lines.append(f"Sample CJK terms: {cjk_terms}")
r = _search(data, "错误处理", 5)
summary_lines.append(f"Search '错误处理': {len(r)} results")
[summary_lines.append(f'  "{x["file"]}" score={x["score"]}') for x in r]
r = _search(data, "重试机制", 5)
summary_lines.append(f"Search '重试机制': {len(r)} results")
[summary_lines.append(f'  "{x["file"]}" score={x["score"]}') for x in r]
r = _search(data, "resilience retry error handling", 5)
summary_lines.append(f"Search EN: {len(r)} results")
[summary_lines.append(f'  "{x["file"]}" score={x["score"]}') for x in r]
fout_path.write_text(chr(10).join(summary_lines), encoding="utf-8")
summary_lines.insert(0, "=== RAG Rebuild Report ===")
summary_lines.append("=== DONE ===")
d = chr(10).join(summary_lines)
print(d[:800])

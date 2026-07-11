"""RAG engine -- semantic code search using TF-IDF vectorization.

No external dependencies. Builds a searchable index of project files,
then supports natural-language queries via cosine similarity.

Usage:
    from core.rag import RAGEngine
    rag = RAGEngine()
    rag.index_project()          # build index from project files
    results = rag.search("how does image generation work", top_k=5)
"""

import json
import math
import re
import time
from collections import Counter
from pathlib import Path

__all__ = [
    "INDEX_FILE",
    "ROOT",
    "RAGEngine",
    "index_codebase",
    "semantic_search",
]

ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = ROOT / "output" / "rag_index.json"


class RAGEngine:
    """TF-IDF based semantic code search."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.index: dict = {"documents": {}, "idf": {}, "built_at": 0}
        self._loaded = False

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into meaningful word tokens.

        English: word-boundary tokens (>=2 chars).
        CJK (\\u4e00-\\u9fff): character bigrams for cross-document
        overlap.  Greedy full-run matching (old behaviour) collapses
        multi-character Chinese phrases into a single token that never
        matches any document's vocabulary → zero recall.
        """
        text_lower = text.lower()
        tokens: list[str] = []
        # Split into CJK and non-CJK runs so we can handle each alphabet
        # with the right strategy.
        for segment in re.split(r"([\u4e00-\u9fff]+)", text_lower):
            if not segment:
                continue
            if re.search(r"[\u4e00-\u9fff]", segment):
                # Chinese run → character bigrams
                n = len(segment)
                if n == 1:
                    tokens.append(segment)
                else:
                    tokens.extend(segment[i : i + 2] for i in range(n - 1))
            else:
                # ASCII / mixed → word tokens
                tokens.extend(t for t in re.findall(r"[a-zA-Z_]\w+", segment) if len(t) >= 2)
        return tokens

    def index_project(self, force: bool = False):
        """Index all project source files."""
        if not force and self._try_load_cache():
            return
        docs = {}
        df = Counter()  # document frequency

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

        from core.constraints import PROJECT_SKIP_DIRS as skip_dirs

        files = list(self.root.rglob("*"))
        for f in files:
            if any(skip in f.parts for skip in skip_dirs):
                continue
            if f.suffix.lower() not in source_exts:
                continue
            if f.stat().st_size > 500_000:  # skip files > 500KB
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            tokens = self._tokenize(content)
            if not tokens:
                continue
            rel = str(f.relative_to(self.root))
            tf = Counter(tokens)
            docs[rel] = {"tf": dict(tf), "token_count": len(tokens)}
            for token in set(tokens):
                df[token] += 1

        num_docs = max(len(docs), 1)
        idf = {t: math.log(num_docs / (df[t] + 1)) + 1 for t in df}

        self.index = {
            "documents": docs,
            "idf": idf,
            "built_at": time.time(),
            "doc_count": len(docs),
        }
        self._save_cache()

    def _try_load_cache(self) -> bool:
        if not INDEX_FILE.exists():
            return False
        try:
            data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
            if time.time() - data.get("built_at", 0) < 3600:  # 1-hour TTL
                self.index = data
                return True
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        return False

    def _save_cache(self):
        try:
            INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
            INDEX_FILE.write_text(json.dumps(self.index, ensure_ascii=False), encoding="utf-8")
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    def _query_vector(self, query: str) -> dict:
        tokens = self._tokenize(query)
        tf = Counter(tokens)
        num_terms = len(tf)
        vec = {}
        for term, count in tf.items():
            tf_val = count / max(num_terms, 1)
            idf_val = self.index["idf"].get(term, 1.0)
            vec[term] = tf_val * idf_val
        return vec

    def _cosine_similarity(self, vec_a: dict, vec_b: dict) -> float:
        dot = sum(vec_a.get(k, 0) * vec_b.get(k, 0) for k in set(vec_a) | set(vec_b))
        mag_a = math.sqrt(sum(v**2 for v in vec_a.values()))
        mag_b = math.sqrt(sum(v**2 for v in vec_b.values()))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Semantic search over indexed documents. Returns ranked results."""
        if not self.index["documents"]:
            self.index_project()
        qv = self._query_vector(query)
        scores = []
        for doc_path, doc_info in self.index["documents"].items():
            dv = doc_info.get("tf", {})
            score = self._cosine_similarity(qv, dv)
            if score > 0:
                scores.append((doc_path, score, doc_info.get("token_count", 0)))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [{"file": path, "score": round(score, 4), "token_count": tc} for path, score, tc in scores[:top_k]]

    def search_with_preview(self, query: str, top_k: int = 5, preview_lines: int = 3) -> list[dict]:
        """Search and include matching line previews."""
        results = self.search(query, top_k)
        for r in results:
            try:
                content = (self.root / r["file"]).read_text(encoding="utf-8", errors="replace")
                lines = content.split(chr(10))
                # Find most relevant lines
                tokens = set(self._tokenize(query))
                best_lines = []
                for i, line in enumerate(lines):
                    line_tokens = set(self._tokenize(line))
                    if tokens & line_tokens:
                        best_lines.append((i + 1, line.strip()[:120]))
                        if len(best_lines) >= preview_lines:
                            break
                r["preview"] = best_lines
            except (OSError, UnicodeDecodeError):
                r["preview"] = []
        return results


# Convenience
def semantic_search(query: str, top_k: int = 10) -> str:
    return json.dumps(RAGEngine().search(query, top_k), ensure_ascii=False)


def index_codebase():
    RAGEngine().index_project(force=True)

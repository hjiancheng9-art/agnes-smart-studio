"""Standalone fix: delete pyc + rebuild index with new tokenizer."""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# 1. Delete pyc cache so fresh source is used
pyc = os.path.join(ROOT, "core", "__pycache__", "rag.cpython-311.pyc")
if os.path.exists(pyc):
    os.remove(pyc)
    print("Deleted stale pyc:", pyc)

# 2. Force fresh import
if "core.rag" in sys.modules:
    del sys.modules["core.rag"]

from core.rag import RAGEngine

# 3. Test tokenizer
engine = RAGEngine()
tokens = engine._tokenize("错误处理与重试机制")
print("Test tokens for '错误处理与重试机制':", tokens)
assert len(tokens) > 1, f"Bigram expected, got {len(tokens)} tokens"

# 4. Force rebuild
print("Rebuilding index...")
engine.index_project(force=True)
print(f"Indexed {engine.index['doc_count']} docs, {len(engine.index['idf'])} terms")

# 5. Test search
results = engine.search("错误处理", top_k=5)
print(f"\nSearch '错误处理': {len(results)} results")
for r in results:
    print(f"  {r['file']} (score={r['score']})")

results2 = engine.search("重试机制", top_k=5)
print(f"\nSearch '重试机制': {len(results2)} results")
for r in results2:
    print(f"  {r['file']} (score={r['score']})")

print("\n[OK] Fix verified!")

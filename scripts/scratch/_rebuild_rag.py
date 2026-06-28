"""Force rebuild RAG index with fixed Chinese tokenizer."""

import sys

sys.path.insert(0, ".")
from core.rag import RAGEngine

print("Rebuilding RAG index with bigram tokenizer...")
engine = RAGEngine()
engine.index_project(force=True)
print(f"Done. {engine.index['doc_count']} documents indexed.")
print(f"IDF terms: {len(engine.index['idf'])}")

# Quick test
results = engine.search("错误处理", top_k=3)
print(f"\nSearch '错误处理': {len(results)} results")
for r in results:
    print(f"  {r['file']} (score={r['score']})")

results2 = engine.search("重试机制", top_k=3)
print(f"\nSearch '重试机制': {len(results2)} results")
for r in results2:
    print(f"  {r['file']} (score={r['score']})")

results3 = engine.search("错误处理与重试机制", top_k=3)
print(f"\nSearch '错误处理与重试机制': {len(results3)} results")
for r in results3:
    print(f"  {r['file']} (score={r['score']})")

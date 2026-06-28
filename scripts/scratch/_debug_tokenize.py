"""Debug: verify Chinese tokenization issue in RAG"""

import re

text = "错误处理与重试机制"
# Current tokenizer
tokens = re.findall(r"[a-zA-Z_]\w+|[\u4e00-\u9fff]+", text.lower())
print(f"Query: {text}")
print(f"Tokens (current): {tokens}")
print(f"Token count: {len(tokens)}")

# Simulated: what documents would contain
doc_text = "错误处理 重试机制"
doc_tokens = re.findall(r"[a-zA-Z_]\w+|[\u4e00-\u9fff]+", doc_text.lower())
print(f"\nDoc tokens: {doc_tokens}")
print(f"Overlap: {set(tokens) & set(doc_tokens)}")

# Try jieba
try:
    import jieba

    jieba_tokens = list(jieba.cut(text))
    print(f"\nJieba tokens: {jieba_tokens}")
    jieba_doc = list(jieba.cut(doc_text))
    print(f"Jieba doc tokens: {jieba_doc}")
    print(f"Jieba overlap: {set(jieba_tokens) & set(jieba_doc)}")
except ImportError:
    print("\njieba NOT installed")

# Bigram approach
bigrams = [text[i : i + 2] for i in range(len(text) - 1)]
print(f"\nBigrams: {bigrams}")
doc_bigrams = [doc_text[i : i + 2] for i in range(len(doc_text) - 1)]
print(f"Doc bigrams: {doc_bigrams}")
print(f"Bigram overlap: {set(bigrams) & set(doc_bigrams)}")

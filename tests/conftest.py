from __future__ import annotations

import os


# Unit tests should not load local multi-GB embedding/reranker models or call
# external LLM providers. Integration/evaluation scripts exercise those paths.
os.environ["AI_ASSISTANT_LLM_ENABLED"] = "0"
os.environ["RAG_EMBEDDING_PROVIDER"] = "local"
os.environ["RAG_EMBEDDING_MODEL"] = "local-hash-bge-small-zh-v1.5-compatible"
os.environ["RAG_EMBEDDING_DIM"] = "256"
os.environ["RAG_RERANK_ENABLED"] = "1"
os.environ["RAG_RERANK_PROVIDER"] = "local"
os.environ["RAG_RERANK_MODEL"] = "bge-reranker-base"
os.environ["RAG_CACHE_ENABLED"] = "0"

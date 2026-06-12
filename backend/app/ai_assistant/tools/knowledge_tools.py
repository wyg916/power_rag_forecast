from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...config import PROJECT_ROOT
from ...data_access import jsonable


SEARCH_ROOTS = [
    PROJECT_ROOT / "knowledge_base",
    PROJECT_ROOT / "electricity_tariff_output" / "04_knowledge_base_tariff_policy",
]


def _tokens(text: str) -> list[str]:
    tokens = [token for token in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", text or "") if token]
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fa5]{4,}", token):
            expanded.extend(token[idx : idx + 2] for idx in range(0, len(token) - 1))
    return list(dict.fromkeys(expanded))


def search_business_knowledge(keyword: str = "", question: str = "", top_k: int = 5, **_: Any) -> dict[str, Any]:
    query = (keyword or question or "").strip()
    try:
        from ...services.rag_service import rag_search

        rag = rag_search(query, top_k=top_k)
        if rag.get("items"):
            return jsonable(
                {
                    "tool": "search_business_knowledge",
                    "available": True,
                    "keyword": query,
                    "items": [
                        {
                            "chunk_id": item.get("chunk_id"),
                            "doc_id": item.get("doc_id"),
                            "title": item.get("title"),
                            "path": item.get("source"),
                            "score": item.get("final_score", item.get("score")),
                            "keyword_score": item.get("keyword_score", 0.0),
                            "vector_score": item.get("vector_score", 0.0),
                            "rerank_score": item.get("rerank_score", 0.0),
                            "snippet": item.get("content"),
                            "retrieval_types": item.get("retrieval_types") or [],
                        }
                        for item in rag.get("items", [])
                    ],
                    "evidence": rag.get("evidence") or [],
                    "rag": {
                        "source": "postgresql.kb_chunks",
                        "stats": rag.get("stats"),
                        "retrieval": rag.get("retrieval"),
                    },
                }
            )
    except Exception:
        pass

    tokens = _tokens(query)
    items: list[dict[str, Any]] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            score = sum(text.count(token) for token in tokens)
            if score <= 0 and query not in text:
                continue
            lines = [line.strip("# ").strip() for line in text.splitlines() if line.strip()]
            items.append(
                {
                    "title": lines[0] if lines else path.stem,
                    "path": str(path),
                    "score": score,
                    "snippet": text[:420],
                }
            )
    items.sort(key=lambda item: item["score"], reverse=True)
    return jsonable(
        {
            "tool": "search_business_knowledge",
            "available": bool(items),
            "keyword": query,
            "items": items[:top_k],
            "evidence": [{"source": item["path"], "title": item["title"]} for item in items[:top_k]],
        }
    )

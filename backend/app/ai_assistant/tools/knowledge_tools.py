from __future__ import annotations

from typing import Any

from ...data_access import jsonable


def search_business_knowledge(
    keyword: str = "",
    question: str = "",
    top_k: int = 5,
    domain: str = "",
    _rag_context: Any = None,
    _enterprise_store: Any = None,
    **_: Any,
) -> dict[str, Any]:
    query = (keyword or question or "").strip()
    try:
        from ...services.rag_service import rag_search

        rag = rag_search(
            query,
            top_k=top_k,
            domain=domain,
            context=_rag_context,
            enterprise_store=_enterprise_store,
        )
        items = [
            {
                "chunk_id": item.get("chunk_id"),
                "doc_id": item.get("doc_id"),
                "title": item.get("title"),
                "section_title": item.get("section_title"),
                "path": item.get("source"),
                "domain": item.get("domain"),
                "source_type": item.get("evidence_source_type"),
                "score": item.get("final_score", item.get("score")),
                "keyword_score": item.get("keyword_score", 0.0),
                "vector_score": item.get("vector_score", 0.0),
                "rerank_score": item.get("rerank_score", 0.0),
                "snippet": item.get("content"),
                "retrieval_types": item.get("retrieval_types") or [],
            }
            for item in rag.get("items", [])
        ]
        return jsonable(
            {
                "tool": "search_business_knowledge",
                "available": bool(items),
                "keyword": query,
                "source_type": rag.get("source_type") or "unavailable",
                "domain": rag.get("domain") or "",
                "items": items,
                "citations": rag.get("citations") or [],
                "evidence": rag.get("citations") or [],
                "rag": {
                    "source": "postgresql.kb_chunks",
                    "stats": rag.get("stats"),
                    "retrieval": rag.get("retrieval"),
                },
            }
        )
    except Exception as exc:
        error = exc.__class__.__name__
    return jsonable(
        {
            "tool": "search_business_knowledge",
            "available": False,
            "keyword": query,
            "source_type": "unavailable",
            "domain": "",
            "items": [],
            "citations": [],
            "evidence": [],
            "message": "Knowledge retrieval unavailable; local file fallback is disabled.",
            "error": error,
        }
    )

from __future__ import annotations

from typing import Any

from backend.app.services.rag_content_security import wrap_untrusted_evidence

from .schemas import IntentDecision, ToolResult


def _clip(value: Any, limit: int = 1600) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "...(已截断)"
    if isinstance(value, list):
        return [_clip(item, limit=limit) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key): _clip(item, limit=limit) for key, item in value.items()}
    return value


def _tool_facts(results: list[ToolResult]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for result in results:
        output = result.output or {}
        facts.append(
            {
                "name": result.name,
                "success": result.success,
                "available": output.get("available", True),
                "error_message": result.error_message or "",
                "summary": _clip({key: value for key, value in output.items() if key not in {"evidence"}}, limit=1800),
            }
        )
    return facts


def build_context_pack(
    *,
    question: str,
    decision: IntentDecision,
    results: list[ToolResult],
    evidence: list[dict[str, Any]],
    run_id: str,
    rag_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing_data = [
        {"tool": result.name, "message": result.error_message or result.output.get("message") or "工具未返回可用数据"}
        for result in results
        if not result.success
    ]
    return {
        "question": question,
        "run_id": run_id,
        "primary_intent": decision.intent,
        "entities": decision.entities,
        "tool_facts": _tool_facts(results),
        "evidence": _clip(evidence, limit=1000),
        "knowledge_evidence": _clip(
            [
                {
                    "chunk_id": item.get("chunk_id"),
                    "doc_id": item.get("doc_id"),
                    "title": item.get("title"),
                    "section": item.get("section_title"),
                    "source": item.get("source"),
                    "domain": item.get("domain"),
                    "source_type": item.get("evidence_source_type"),
                    "content": item.get("untrusted_evidence")
                    or wrap_untrusted_evidence(str(item.get("content") or "")),
                    "keyword_score": item.get("keyword_score", 0.0),
                    "vector_score": item.get("vector_score", 0.0),
                    "rerank_score": item.get("rerank_score", 0.0),
                    "final_score": item.get("final_score", item.get("score", 0.0)),
                }
                for item in (rag_result or {}).get("items", [])
            ],
            limit=1200,
        ),
        "knowledge_citations": _clip((rag_result or {}).get("citations") or [], limit=1200),
        "knowledge_retrieval": _clip((rag_result or {}).get("retrieval") or {}, limit=800),
        "missing_data": missing_data,
        "rules": {
            "no_fabricated_numbers": True,
            "hide_debug_info": True,
            "use_knowledge_evidence": True,
            "trading_advice_boundary": "辅助决策参考，不等同于交易指令",
        },
    }

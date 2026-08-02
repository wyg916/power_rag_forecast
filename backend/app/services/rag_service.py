from __future__ import annotations

import copy
import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text

from config_loader import load_dotenv
from backend.app.config import PROJECT_ROOT
from backend.app.repositories.base import mapping_list, postgres_engine
from backend.app.repositories.knowledge_repository import (
    backfill_missing_embeddings,
    get_chunks_by_ids,
    knowledge_stats,
    list_embedded_chunks,
    refresh_stale_embeddings,
    search_keyword_chunks,
    upsert_document,
)
from backend.app.services.embedding_service import cosine_similarity, embed_text_with_metadata, get_embedding_provider
from backend.app.services.hybrid_retrieval_service import hybrid_retrieve
from backend.app.services.qdrant_vector_store import QdrantReadOnlyStore
from backend.app.services.rag_content_security import secure_candidates
from backend.app.services.rag_grounding_service import validate_candidate_citations
from backend.app.services.rag_runtime_contract import (
    RetrievalContext,
    enterprise_mode,
    runtime_contract_status,
)
from backend.app.services.rerank_service import rerank_candidates
from backend.app.services.rag_query_rewriter import rewrite_rag_query
from backend.app.services.vector_index_service import query_vector_index


SEARCH_ROOTS = [
    PROJECT_ROOT / "knowledge_base",
    PROJECT_ROOT / "electricity_tariff_output" / "04_knowledge_base_tariff_policy",
]


TITLE_ALIAS_PATH = PROJECT_ROOT / "knowledge_pipeline" / "title_alias_map.json"


RAG_PROFILE_DEFAULTS: dict[str, dict[str, int]] = {
    "quality": {"keyword_top_k": 30, "vector_top_k": 50, "rerank_candidate_limit": 20},
    "balanced": {"keyword_top_k": 25, "vector_top_k": 40, "rerank_candidate_limit": 12},
    "fast": {"keyword_top_k": 15, "vector_top_k": 25, "rerank_candidate_limit": 8},
}


CATEGORY_BOOST_RULES: list[tuple[list[str], list[str]]] = [
    (["绿证", "绿色电力证书", "GEC"], ["绿证交易"]),
    (["代理购电", "电网企业代理"], ["电网代理购电", "电价政策"]),
    (["现货", "日前", "实时", "出清"], ["电力现货交易"]),
    (["PJM", "DOM", "Dominion", "LMP", "节点电价"], ["PJM/DOM/LMP机制", "市场机制解释"]),
    (["分时", "峰谷电价", "输配电价", "代理购电价格"], ["电价政策"]),
    (["新能源", "光伏", "风电", "储能"], ["新能源政策"]),
    (["RMSE", "MAE", "误差", "模型"], ["模型与预测方法"]),
    (["负荷", "天气", "温度", "需求"], ["模型与预测方法", "市场机制解释"]),
    (["交易策略", "售电", "报价", "合约敞口"], ["交易策略"]),
    (["系统", "AI助手", "开发者模式", "预测中心", "策略中心"], ["项目知识", "其他"]),
    (["数据不足", "缺少数据", "证据不足", "样本不足"], ["answer_policy"]),
    (["天气新鲜度", "天气更新时间", "天气过期"], ["weather"]),
    (["尖峰概率", "尖峰风险", "价格冲高", "晚高峰风险"], ["price_risk"]),
    (["储能", "SOC", "充放电", "储能套利"], ["strategy"]),
    (["模型切换", "模型回退", "DeepSeek", "Ollama", "fallback"], ["ai_assistant"]),
    (["LMP", "PJM", "绿证", "代理购电", "RMSE", "MAE", "MAPE"], ["market_terms"]),
]


POLICY_DOC_MARKERS = ["ai_assistant_explanation_policies", "answer_policy", "missing_data_response_policy"]
POLICY_ALLOW_TERMS = [
    "数据不足",
    "缺少数据",
    "没有数据",
    "无法判断",
    "证据不足",
    "能不能判断",
    "是否可以",
    "deepseek",
    "ollama",
    "模型切换",
    "模型回退",
    "本地模型",
    "在线模型",
    "api key",
    "trace",
    "workflow",
    "debug",
    "交易建议边界",
    "辅助决策",
    "储能约束",
    "soc",
]
POLICY_DOWNRANK_TERMS = [
    "lmp",
    "pjm",
    "日前市场",
    "实时市场",
    "绿证",
    "代理购电",
    "峰谷价差",
    "节点电价",
    "现货市场",
    "rmse",
    "mae",
    "mape",
    "day-ahead",
    "real-time",
]


def _env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)) or default)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)) or default)
    except Exception:
        return default


def _env_first_int(names: list[str], default: int) -> int:
    for name in names:
        value = _env(name, "")
        if not value:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return default


def _rag_profile() -> str:
    value = (_env("RAG_PROFILE", "") or _env("RAG_MODE", "") or "balanced").strip().lower()
    return value if value in RAG_PROFILE_DEFAULTS else "balanced"


def _rag_profile_defaults() -> dict[str, int]:
    return RAG_PROFILE_DEFAULTS[_rag_profile()]


def _timing_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _cache_ttl_seconds() -> int:
    ttl = _env_int("RAG_CACHE_TTL_SECONDS", 600)
    return max(0, min(ttl, 3600))


def _cache_bucket() -> str:
    ttl = _cache_ttl_seconds()
    if ttl <= 0:
        return str(time.time_ns())
    return str(int(time.time() // ttl))


def _contains_sensitive_text(query: str) -> bool:
    value = (query or "").lower()
    if not value:
        return False
    sensitive_markers = [
        "api_key",
        "apikey",
        "secret",
        "password",
        "token",
        "bearer ",
        "sk-",
        "密钥",
        "密码",
        "令牌",
    ]
    return any(marker in value for marker in sensitive_markers)


def _config_mtime(path: Path) -> str:
    try:
        return str(path.stat().st_mtime)
    except Exception:
        return "0"


def _rag_cache_signature() -> tuple[str, ...]:
    return (
        _env("RAG_PROFILE", ""),
        _env("RAG_MODE", ""),
        _env("RAG_ENABLED", "1"),
        _env("RAG_EMBEDDING_PROVIDER", ""),
        _env("RAG_EMBEDDING_MODEL", ""),
        _env("RAG_EMBEDDING_MODEL_NAME", ""),
        _env("RAG_EMBEDDING_MODEL_PATH", ""),
        _env("RAG_EMBEDDING_EXPECTED_DIM", ""),
        _env("RAG_EMBEDDING_ALLOW_FALLBACK", "0"),
        _env("RAG_RERANK_ENABLED", "1"),
        _env("RAG_RERANK_PROVIDER", ""),
        _env("RAG_RERANK_MODEL", ""),
        _env("RAG_RERANK_MODEL_NAME", ""),
        _env("RAG_RERANK_MODEL_PATH", ""),
        _env("RAG_RERANK_CANDIDATE_LIMIT", ""),
        _env("RAG_KEYWORD_LIMIT", ""),
        _env("RAG_VECTOR_LIMIT", ""),
        _env("RAG_TOP_K", ""),
        _env("RAG_SCORE_THRESHOLD", ""),
        _env("RAG_FILE_FALLBACK_ENABLED", "0"),
        _env("RAG_VECTOR_TOP_K", ""),
        _env("RAG_KEYWORD_TOP_K", ""),
        _env("RAG_CACHE_TTL_SECONDS", ""),
        _cache_bucket(),
        _env("RAG_QUERY_REWRITE_ENABLED", "1"),
        _env("RAG_QUERY_EXPANSION_MAX_TERMS", ""),
        _env("RAG_TITLE_ALIAS_BOOST_ENABLED", "1"),
        _env("RAG_CATEGORY_BOOST_ENABLED", "1"),
        _env("RAG_DOMAIN_BOOST_MAX", ""),
        _env("RAG_IMPORTED_NOTE_PENALTY", ""),
        _env("RAG_CORE_DOC_FINAL_BONUS", ""),
        _env("RAG_POLICY_DOC_PROFESSIONAL_PENALTY", ""),
        _env("RAG_POLICY_DOC_ALLOWED_BONUS", ""),
        _config_mtime(PROJECT_ROOT / "knowledge_pipeline" / "domain_synonyms.json"),
        _config_mtime(TITLE_ALIAS_PATH),
    )


def rag_enabled() -> bool:
    return (_env("RAG_ENABLED", "1") or "1").lower() not in {"0", "false", "no", "off"}


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _classify_failure(path: Path, message: str = "") -> str:
    suffix = path.suffix.lower()
    value = (message or "").lower()
    if suffix == ".pdf":
        return "scanned_pdf_needs_ocr"
    if suffix not in {".md", ".txt"}:
        return "unsupported_format"
    if "unicode" in value or "decode" in value or "encoding" in value:
        return "encoding_exception"
    return "parse_failed"


def _failure_summary(items: list[dict[str, str]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        reason = str(item.get("reason") or "unknown")
        summary[reason] = summary.get(reason, 0) + 1
    return summary


def _domain_from_path(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "electricity_market" in parts:
        return "electricity_market"
    if "price_forecast" in parts:
        return "price_forecast"
    if "project_knowledge" in parts:
        return "system_knowledge"
    if "trading_strategy" in parts:
        return "trading_strategy"
    return ""


def index_local_knowledge(limit_files: int = 300) -> dict[str, Any]:
    indexed = 0
    failed: list[dict[str, str]] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file() and item.suffix.lower() not in {".md", ".txt"})[:limit_files]:
            reason = _classify_failure(path)
            failed.append({"path": str(path), "message": reason, "reason": reason})
        candidates = sorted([*root.rglob("*.md"), *root.rglob("*.txt")])
        for path in candidates[:limit_files]:
            try:
                result = upsert_document(
                    title=path.stem,
                    source_type="local_file",
                    source_path=str(path),
                    content=_read_text_file(path),
                    metadata={
                        "root": str(root),
                        "file_name": path.name,
                        "domain": _domain_from_path(path),
                        "evidence_source_type": "real",
                        "source_name": path.name,
                        "status": "active",
                        "evidence_level": "project_document",
                    },
                    generate_embeddings=True,
                )
                if result.get("available"):
                    indexed += 1
                else:
                    message = str(result.get("message") or "")
                    failed.append({"path": str(path), "message": message, "reason": _classify_failure(path, message)})
            except Exception as exc:
                message = str(exc)
                failed.append({"path": str(path), "message": message, "reason": _classify_failure(path, message)})
    indexed += index_policy_rows()
    backfill = backfill_missing_embeddings()
    refresh = refresh_stale_embeddings()
    try:
        _rag_search_cached.cache_clear()
    except Exception:
        pass
    return {
        "available": True,
        "indexed_documents": indexed,
        "failed": failed,
        "failure_summary": _failure_summary(failed),
        "embedding_backfill": backfill,
        "embedding_refresh": refresh,
        "stats": knowledge_stats(),
    }


def index_policy_rows() -> int:
    engine = postgres_engine()
    if engine is None:
        return 0
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT doc_id, title, doc_number, publish_date, province, city,
                           summary, source_file, source_sheet, source_row
                    FROM pv_policy_files
                    ORDER BY publish_date DESC NULLS LAST, id
                    LIMIT 1000
                    """
                )
            ).mappings().all()
    except Exception:
        return 0
    count = 0
    for row in mapping_list(rows):
        content = "\n".join(
            str(item or "")
            for item in [
                row.get("title"),
                row.get("doc_number"),
                row.get("publish_date"),
                row.get("province"),
                row.get("city"),
                row.get("summary"),
            ]
            if item
        )
        if not content.strip():
            continue
        result = upsert_document(
            title=str(row.get("title") or row.get("doc_number") or row.get("doc_id") or "政策摘要"),
            source_type="pv_policy_files",
            source_path=str(row.get("source_file") or f"pv_policy_files:{row.get('doc_id') or row.get('source_row')}"),
            content=content,
            metadata={
                **row,
                "domain": "electricity_policy",
                "evidence_source_type": "historical",
                "source_name": str(row.get("title") or row.get("doc_number") or "政策摘要"),
                "status": "active",
                "evidence_level": "database_policy_summary",
            },
            generate_embeddings=True,
        )
        if result.get("available"):
            count += 1
    return count


def _normalize_scores(items: list[dict[str, Any]], score_key: str, normalized_key: str) -> None:
    values = [float(item.get(score_key) or 0.0) for item in items]
    max_value = max(values) if values else 0.0
    for item in items:
        raw = float(item.get(score_key) or 0.0)
        item[normalized_key] = round(raw / max_value, 6) if max_value > 0 else 0.0


def _compact_for_match(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").lower())


@lru_cache(maxsize=8)
def _load_title_alias_map(path_value: str, mtime: str) -> dict[str, list[str]]:
    _ = mtime
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    output: dict[str, list[str]] = {}
    for title, aliases in data.items():
        if not str(title).strip():
            continue
        if isinstance(aliases, list):
            values = [str(item).strip() for item in aliases if str(item).strip()]
        else:
            values = [str(aliases).strip()] if str(aliases).strip() else []
        output[str(title).strip()] = values
    return output


def _title_alias_map() -> dict[str, list[str]]:
    return _load_title_alias_map(str(TITLE_ALIAS_PATH), _config_mtime(TITLE_ALIAS_PATH))


def _item_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _item_category(item: dict[str, Any]) -> str:
    metadata = _item_metadata(item)
    return str(
        metadata.get("category")
        or metadata.get("source_category")
        or metadata.get("document_category")
        or metadata.get("category_name")
        or ""
    )


def _item_match_text(item: dict[str, Any]) -> str:
    metadata = _item_metadata(item)
    metadata_text = " ".join(
        str(metadata.get(key) or "")
        for key in (
            "category",
            "title",
            "source_file",
            "source_path",
            "original_chunk_id",
            "keywords",
        )
    )
    return " ".join(
        str(value or "")
        for value in [
            item.get("title"),
            item.get("source"),
            item.get("source_type"),
            item.get("content"),
            _item_category(item),
            metadata_text,
        ]
    )


def _term_hit(blob: str, term: str) -> bool:
    compact = _compact_for_match(term)
    if not compact:
        return False
    return compact in blob


def _query_has_any(query_blob: str, terms: list[str]) -> bool:
    return any(_term_hit(query_blob, term) for term in terms)


def _is_policy_item(item: dict[str, Any]) -> bool:
    blob = _compact_for_match(_item_match_text(item))
    return any(_term_hit(blob, marker) for marker in POLICY_DOC_MARKERS)


def _apply_domain_boost(items: list[dict[str, Any]], query_info: dict[str, Any]) -> list[dict[str, Any]]:
    alias_enabled = (_env("RAG_TITLE_ALIAS_BOOST_ENABLED", "1") or "1").lower() not in {"0", "false", "no", "off"}
    category_enabled = (_env("RAG_CATEGORY_BOOST_ENABLED", "1") or "1").lower() not in {"0", "false", "no", "off"}
    if not items or not (alias_enabled or category_enabled):
        return []

    max_boost = max(0.0, min(_env_float("RAG_DOMAIN_BOOST_MAX", 0.18), 0.35))
    if max_boost <= 0:
        return []

    query_terms = [
        str(query_info.get("query") or ""),
        str(query_info.get("expanded_query") or ""),
        *[str(term) for term in query_info.get("expanded_terms") or []],
    ]
    query_blob = _compact_for_match(" ".join(query_terms))
    original_query_blob = _compact_for_match(str(query_info.get("query") or ""))
    policy_allowed_query = _query_has_any(original_query_blob, POLICY_ALLOW_TERMS)
    policy_downrank_query = _query_has_any(query_blob, POLICY_DOWNRANK_TERMS)
    alias_map = _title_alias_map()
    boost_events: list[dict[str, Any]] = []

    for item in items:
        item_blob = _compact_for_match(_item_match_text(item))
        category_blob = _compact_for_match(_item_category(item))
        title_blob = _compact_for_match(str(item.get("title") or ""))
        source_blob = _compact_for_match(str(item.get("source") or ""))
        source_type = str(item.get("source_type") or "")
        boost = 0.0
        penalty = 0.0
        matches: list[str] = []
        is_policy_item = _is_policy_item(item)

        if str(item.get("evidence_level") or "") == "verified_project_contract":
            boost += 0.15
            matches.append("evidence_level:verified_project_contract")

        if alias_enabled:
            for title, aliases in alias_map.items():
                terms = [title, *aliases]
                if not any(_term_hit(query_blob, term) for term in terms):
                    continue
                if _term_hit(title_blob, title) or _term_hit(source_blob, title):
                    boost += 0.14
                    matches.append(f"core_title:{title}")
                elif "knowledge_base" in source_blob and any(_term_hit(item_blob, term) for term in terms):
                    boost += 0.1
                    matches.append(f"core_alias:{title}")
                elif any(_term_hit(item_blob, term) for term in terms):
                    boost += 0.05
                    matches.append(f"title_alias:{title}")

        if category_enabled:
            for trigger_terms, categories in CATEGORY_BOOST_RULES:
                if not any(_term_hit(query_blob, term) for term in trigger_terms):
                    continue
                if any(_term_hit(category_blob, category) or _term_hit(item_blob, category) for category in categories):
                    boost += 0.06
                    matches.append(f"category:{'/'.join(categories)}")

        if source_type == "knowledge_pipeline_jsonl" and _term_hit(title_blob, "AI-项目进展与分析"):
            penalty = _env_float("RAG_IMPORTED_NOTE_PENALTY", 0.06)

        if is_policy_item and policy_downrank_query and not policy_allowed_query:
            penalty += _env_float("RAG_POLICY_DOC_PROFESSIONAL_PENALTY", 0.28)
            boost = min(boost, 0.02)
            matches.append("policy_doc_downrank:professional_term")
            item["policy_doc_downranked"] = True
        elif is_policy_item and policy_allowed_query:
            boost += min(_env_float("RAG_POLICY_DOC_ALLOWED_BONUS", 0.05), 0.08)
            matches.append("policy_doc_allowed:boundary_query")

        if boost <= 0 and penalty <= 0:
            item["category_boost"] = 0.0
            continue

        boost = round(min(boost, max_boost), 6)
        item["category_boost"] = boost
        penalty_limit = 0.45 if item.get("policy_doc_downranked") else 0.15
        item["domain_penalty"] = round(max(0.0, min(penalty, penalty_limit)), 6)
        item["boost_matches"] = list(dict.fromkeys(matches))[:8]
        base = float(item.get("hybrid_score") or item.get("final_score") or 0.0)
        item["hybrid_score"] = round(max(0.0, base + boost - float(item.get("domain_penalty") or 0.0)), 6)
        item["final_score"] = item["hybrid_score"]
        boost_events.append(
            {
                "chunk_id": item.get("chunk_id"),
                "title": item.get("title"),
                "category": _item_category(item),
                "boost": boost,
                "penalty": item.get("domain_penalty", 0.0),
                "matches": item.get("boost_matches") or [],
            }
        )

    items.sort(key=lambda row: row.get("hybrid_score", 0), reverse=True)
    return boost_events[:20]


def _apply_post_rerank_adjustments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    core_bonus = max(0.0, min(_env_float("RAG_CORE_DOC_FINAL_BONUS", 0.08), 0.2))
    adjusted: list[dict[str, Any]] = []
    for item in items:
        enriched = dict(item)
        final_score = float(enriched.get("final_score") or 0.0)
        matches = [str(value) for value in enriched.get("boost_matches") or []]
        if not enriched.get("policy_doc_downranked") and any(value.startswith("core_title:") or value.startswith("core_alias:") for value in matches):
            final_score += core_bonus
            enriched["core_doc_final_bonus"] = core_bonus
        penalty = float(enriched.get("domain_penalty") or 0.0)
        if penalty > 0:
            final_score -= penalty
        enriched["final_score"] = round(max(0.0, final_score), 6)
        adjusted.append(enriched)
    adjusted.sort(key=lambda row: row.get("final_score", 0), reverse=True)
    return adjusted


def _vector_search(
    query: str,
    top_k: int,
    *,
    domain: str = "",
    source_types: list[str] | None = None,
    include_historical: bool = False,
    include_demo: bool = False,
) -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    query_embedding_result = embed_text_with_metadata(query)
    query_embedding = query_embedding_result.get("embedding") or []
    query_embedding_meta = query_embedding_result.get("metadata") or {}
    if not query_embedding:
        return [], False, query_embedding_meta
    index_result = query_vector_index(
        query_embedding,
        top_k=max(100, min(int(top_k or 20) * 5, 1000)),
    )
    query_embedding_meta["vector_index_available"] = bool(index_result.get("available"))
    query_embedding_meta["vector_index_reason"] = str(index_result.get("reason") or "")
    if index_result.get("available"):
        ranked = index_result.get("items") or []
        scores = {str(item.get("chunk_id") or ""): float(item.get("vector_score") or 0) for item in ranked}
        default_vector_min = 0.35 if domain or source_types else 0.52
        vector_min_score = max(-1.0, min(_env_float("RAG_VECTOR_FILTERED_MIN_SCORE", default_vector_min), 1.0))
        chunks = get_chunks_by_ids(
            list(scores),
            domain=domain,
            source_types=source_types,
            include_historical=include_historical,
            include_demo=include_demo,
        )
        scored = [
            dict(item, vector_score=round(scores.get(str(item.get("chunk_id") or ""), 0.0), 6), score=round(scores.get(str(item.get("chunk_id") or ""), 0.0), 6))
            for item in chunks
            if scores.get(str(item.get("chunk_id") or ""), 0.0) >= vector_min_score
        ]
        query_embedding_meta["dimension_mismatch_count"] = 0
        query_embedding_meta["compatible_chunk_count"] = int((index_result.get("metadata") or {}).get("row_count") or len(ranked))
        return scored[: max(1, min(int(top_k or 20), 100))], True, query_embedding_meta
    if domain or source_types or include_historical or include_demo:
        chunks = list_embedded_chunks(
            limit=_env_int("RAG_VECTOR_SCAN_LIMIT", 3000),
            domain=domain,
            source_types=source_types,
            include_historical=include_historical,
            include_demo=include_demo,
        )
    else:
        chunks = list_embedded_chunks(limit=_env_int("RAG_VECTOR_SCAN_LIMIT", 3000))
    scored: list[dict[str, Any]] = []
    dimension_mismatches = 0
    for item in chunks:
        embedding = item.pop("embedding", [])
        if len(embedding) != len(query_embedding):
            dimension_mismatches += 1
            continue
        vector_score = cosine_similarity(query_embedding, embedding)
        default_vector_min = 0.35 if domain or source_types else 0.52
        if vector_score < max(-1.0, min(_env_float("RAG_VECTOR_FILTERED_MIN_SCORE", default_vector_min), 1.0)):
            continue
        scored.append(dict(item, vector_score=round(vector_score, 6), score=round(vector_score, 6)))
    scored.sort(key=lambda row: row.get("vector_score", 0), reverse=True)
    query_embedding_meta["dimension_mismatch_count"] = dimension_mismatches
    query_embedding_meta["compatible_chunk_count"] = len(chunks) - dimension_mismatches
    vector_available = bool(scored) or (bool(chunks) and dimension_mismatches == 0)
    return scored[: max(1, min(int(top_k or 20), 100))], vector_available, query_embedding_meta


def _merge_candidates(keyword_items: list[dict[str, Any]], vector_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    _normalize_scores(keyword_items, "keyword_score", "keyword_score")
    _normalize_scores(vector_items, "vector_score", "vector_score")
    for source, retrieval_type in [(keyword_items, "keyword"), (vector_items, "vector")]:
        for item in source:
            chunk_id = str(item.get("chunk_id") or "")
            if not chunk_id:
                continue
            current = merged.setdefault(chunk_id, dict(item, retrieval_types=[]))
            current["keyword_score"] = max(float(current.get("keyword_score") or 0.0), float(item.get("keyword_score") or 0.0))
            current["vector_score"] = max(float(current.get("vector_score") or 0.0), float(item.get("vector_score") or 0.0))
            current["retrieval_types"] = list(dict.fromkeys([*(current.get("retrieval_types") or []), retrieval_type]))
            for key in (
                "doc_id", "title", "source", "source_path", "source_uri", "source_type",
                "chunk_index", "section_title", "content", "domain", "evidence_source_type",
                "evidence_level", "metadata",
            ):
                if not current.get(key) and item.get(key):
                    current[key] = item.get(key)
    output = []
    for item in merged.values():
        keyword_score = float(item.get("keyword_score") or 0.0)
        vector_score = float(item.get("vector_score") or 0.0)
        item["hybrid_score"] = round(keyword_score * 0.45 + vector_score * 0.55, 6)
        item["final_score"] = item["hybrid_score"]
        output.append(item)
    output.sort(key=lambda row: row.get("hybrid_score", 0), reverse=True)
    return output

def _citations_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "document_id": item.get("doc_id"),
            "chunk_id": item.get("chunk_id"),
            "title": item.get("title"),
            "section": item.get("section_title") or "",
            "source": item.get("source"),
            "domain": item.get("domain") or "",
            "source_type": item.get("evidence_source_type") or "real",
            "evidence_level": item.get("evidence_level") or "",
            "score": item.get("final_score", item.get("score")),
            "quote": str(item.get("content") or "")[:240],
        }
        for item in items
        if item.get("doc_id") and item.get("chunk_id") and item.get("content") and item.get("domain")
    ]

def _domain_consistent_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    domains = {str(item.get("domain") or "").strip() for item in items if item.get("domain")}
    if len(domains) != 1 or any(not str(item.get("domain") or "").strip() for item in items):
        return []
    return items



def _fallback_file_search(query: str, top_k: int) -> list[dict[str, Any]]:
    compact = "".join(query.replace("？", " ").replace("?", " ").split()).lower()
    tokens = [item for item in compact.split() if item]
    tokens.extend(re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", compact))
    tokens.extend(compact[index : index + 2] for index in range(0, max(0, len(compact) - 1)))
    tokens = list(dict.fromkeys(token for token in tokens if token))[:80]
    items: list[dict[str, Any]] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md"))[:500]:
            text_value = _read_text_file(path)
            score = sum(text_value.count(token) for token in tokens) + (1 if query and query in text_value else 0)
            if score <= 0:
                continue
            title = next((line.strip("# ").strip() for line in text_value.splitlines() if line.strip()), path.stem)
            items.append(
                {
                    "chunk_id": f"file:{path.name}",
                    "doc_id": str(path),
                    "title": title,
                    "source": str(path),
                    "source_type": "local_file",
                    "chunk_index": 0,
                    "content": text_value[:700],
                    "keyword_score": float(score),
                    "vector_score": 0.0,
                    "rerank_score": 0.0,
                    "hybrid_score": float(score),
                    "final_score": float(score),
                    "retrieval_types": ["file_keyword_fallback"],
                }
            )
    items.sort(key=lambda row: row.get("final_score", 0), reverse=True)
    return items[:top_k]


def _explicit_no_evidence_query(query: str) -> bool:
    compact = re.sub(r"\s+", "", query or "").lower()
    future_exact = any(term in compact for term in ("从未记录", "尚未记录", "没有记录")) and any(
        term in compact for term in ("准确", "精确", "收益", "成交")
    )
    nonexistent_citation = any(term in compact for term in ("不存在", "虚构")) and any(
        term in compact for term in ("引用", "文档", "规则", "文件")
    )
    missing_constraints = any(term in compact for term in ("没有", "缺少", "缺失")) and any(
        term in compact for term in ("soc", "容量", "效率", "功率")
    ) and any(term in compact for term in ("精确", "具体", "充放电量"))
    return future_exact or nonexistent_citation or missing_constraints


def _enterprise_unavailable(query: str, reason: str, *, release_id: str = "") -> dict[str, Any]:
    return {
        "available": False,
        "source_type": "unavailable",
        "query": query,
        "items": [],
        "citations": [],
        "evidence": [],
        "release_id": release_id or None,
        "retrieval": {"enabled": True, "mode": "enterprise_qdrant_hybrid", "reason": reason},
        "timings_ms": {},
    }


def _enterprise_rag_search(
    query: str,
    top_k: int,
    *,
    context: RetrievalContext | None,
    store: QdrantReadOnlyStore | None,
    domain: str,
    source_types: list[str] | None,
    include_historical: bool,
    include_demo: bool,
) -> dict[str, Any]:
    contract = runtime_contract_status()
    release_id = contract.release.release_id
    if contract.issues:
        return _enterprise_unavailable(query, contract.issues[0], release_id=release_id)
    if context is None:
        return _enterprise_unavailable(query, "retrieval_context_missing", release_id=release_id)
    if context.issues():
        return _enterprise_unavailable(query, context.issues()[0], release_id=release_id)
    if store is None:
        return _enterprise_unavailable(query, "qdrant_store_unavailable", release_id=release_id)
    if include_historical or include_demo:
        return _enterprise_unavailable(query, "unpublished_content_forbidden", release_id=release_id)
    if store.release != contract.release or store.embedding_profile != contract.embedding:
        return _enterprise_unavailable(query, "runtime_store_contract_mismatch", release_id=release_id)
    embedding = embed_text_with_metadata(query)
    vector = list(embedding.get("embedding") or [])
    metadata = embedding.get("metadata") or {}
    if (
        len(vector) != 1024
        or metadata.get("provider") != contract.embedding.provider
        or metadata.get("model") != contract.embedding.model
        or metadata.get("version") != contract.embedding.version
        or metadata.get("fallback")
    ):
        return _enterprise_unavailable(query, "query_embedding_profile_mismatch", release_id=release_id)
    filters = {"domain": domain, "source_types": source_types or []}
    result = hybrid_retrieve(
        store=store,
        context=context,
        query=query,
        dense_vector=vector,
        sparse_query={"text": query},
        structured_filter={key: value for key, value in filters.items() if value},
        requested_top_k=top_k,
    )
    if not result.available:
        return _enterprise_unavailable(query, result.reason, release_id=release_id)
    secured = secure_candidates(result.items)
    if not secured.available:
        return _enterprise_unavailable(query, secured.reason, release_id=release_id)
    prepared = [
        {
            **item,
            "doc_id": item.get("document_id"),
            "section_title": item.get("section_title") or "",
        }
        for item in secured.items
    ]
    reranked, reranker_name, rerank_error = rerank_candidates(query, prepared)
    if rerank_error or reranker_name == "unavailable" or not reranked:
        return _enterprise_unavailable(query, "reranker_unavailable", release_id=release_id)
    for item in reranked:
        item["final_score"] = float(item.get("final_score") or 0.0) * float(
            item.get("security_score_multiplier") or 0.0
        )
    reranked.sort(key=lambda item: float(item.get("final_score") or 0.0), reverse=True)
    items = reranked[: result.top_k]
    citation_batch = validate_candidate_citations(items)
    if not citation_batch.available:
        return _enterprise_unavailable(query, citation_batch.reason, release_id=release_id)
    citations = citation_batch.citations
    return {
        "available": True,
        "source_type": "published_knowledge",
        "domain": domain or str(items[0].get("domain") or ""),
        "query": query,
        "items": items,
        "citations": citations,
        "evidence": citations,
        "release_id": release_id,
        "retrieval": {
            "enabled": True,
            "mode": "enterprise_qdrant_hybrid",
            "candidate_counts": result.candidate_counts,
            "dynamic_top_k": result.top_k,
            "cache_key": result.cache_key,
            "cache_hit": False,
            "reranker": reranker_name,
            "content_security": {
                "quarantined": secured.quarantined_count,
                "downranked": secured.downranked_count,
            },
        },
        "timings_ms": {},
    }


def _rag_search_impl(
    query: str,
    top_k: int = 5,
    *,
    domain: str = "",
    source_types: list[str] | None = None,
    include_historical: bool = False,
    include_demo: bool = False,
) -> dict[str, Any]:
    total_started = time.perf_counter()
    timings: dict[str, float] = {}
    final_top_k = max(1, min(int(top_k or _env_int("RAG_TOP_K", 5)), 20))
    defaults = _rag_profile_defaults()
    keyword_top_k = _env_first_int(["RAG_KEYWORD_LIMIT", "RAG_KEYWORD_TOP_K"], defaults["keyword_top_k"])
    vector_top_k = _env_first_int(["RAG_VECTOR_LIMIT", "RAG_VECTOR_TOP_K"], defaults["vector_top_k"])
    keyword_top_k = max(final_top_k, min(keyword_top_k, 100))
    vector_top_k = max(final_top_k, min(vector_top_k, 100))
    started = time.perf_counter()
    query_info = rewrite_rag_query(query)
    timings["rewrite_ms"] = _timing_ms(started)
    search_query = str(query_info.get("expanded_query") or query)
    if _explicit_no_evidence_query(query):
        timings["total_ms"] = _timing_ms(total_started)
        return {
            "available": False,
            "source_type": "unavailable",
            "domain": domain,
            "query": query,
            "items": [],
            "citations": [],
            "evidence": [],
            "retrieval": {"enabled": rag_enabled(), "mode": "evidence_guard", "reason": "explicit_missing_evidence"},
            "timings_ms": timings,
            "stats": knowledge_stats(),
        }
    if not rag_enabled():
        started = time.perf_counter()
        if domain or source_types or include_historical or include_demo:
            items = search_keyword_chunks(
                query,
                top_k=final_top_k,
                domain=domain,
                source_types=source_types,
                include_historical=include_historical,
                include_demo=include_demo,
            )
        else:
            items = search_keyword_chunks(query, top_k=final_top_k)
        _normalize_scores(items, "keyword_score", "keyword_score")
        score_threshold = max(0.0, min(_env_float("RAG_SCORE_THRESHOLD", 0.25), 1.0))
        items = [
            dict(item, document_id=item.get("document_id") or item.get("doc_id"), final_score=float(item.get("keyword_score") or 0.0), score=float(item.get("keyword_score") or 0.0))
            for item in items
            if float(item.get("keyword_score") or 0.0) >= score_threshold
        ][:final_top_k]
        items = _domain_consistent_items(items)
        citations = _citations_from_items(items)
        evidence_types = list(dict.fromkeys(str(item.get("evidence_source_type") or "real") for item in items))
        timings["keyword_search_ms"] = _timing_ms(started)
        timings["total_ms"] = _timing_ms(total_started)
        return {
            "available": bool(items),
            "source_type": evidence_types[0] if len(evidence_types) == 1 else "derived" if evidence_types else "unavailable",
            "domain": domain or (str(items[0].get("domain") or "") if items else ""),
            "query": query,
            "items": items,
            "citations": citations,
            "evidence": citations,
            "retrieval": {
                "enabled": False,
                "mode": "keyword_only",
                "score_threshold": score_threshold,
                "filters": {
                    "domain": domain,
                    "source_types": source_types or [],
                    "include_historical": include_historical,
                    "include_demo": include_demo,
                },
            },
            "timings_ms": timings,
            "stats": knowledge_stats(),
        }

    started = time.perf_counter()
    if domain or source_types or include_historical or include_demo:
        keyword_items = search_keyword_chunks(
            search_query,
            top_k=keyword_top_k,
            domain=domain,
            source_types=source_types,
            include_historical=include_historical,
            include_demo=include_demo,
        )
    else:
        keyword_items = search_keyword_chunks(search_query, top_k=keyword_top_k)
    timings["keyword_search_ms"] = _timing_ms(started)
    started = time.perf_counter()
    vector_items, vector_available, query_embedding_meta = _vector_search(
        search_query,
        top_k=vector_top_k,
        domain=domain,
        source_types=source_types,
        include_historical=include_historical,
        include_demo=include_demo,
    )
    if query_embedding_meta.get("vector_index_available"):
        keyword_min_score = max(0.0, _env_float("RAG_KEYWORD_MIN_SCORE", 2.0))
        keyword_items = [item for item in keyword_items if float(item.get("keyword_score") or 0.0) >= keyword_min_score]
    timings["vector_search_ms"] = _timing_ms(started)
    started = time.perf_counter()
    merged = _merge_candidates(keyword_items, vector_items)
    file_fallback_enabled = (_env("RAG_FILE_FALLBACK_ENABLED", "0") or "0").lower() in {"1", "true", "yes", "on"}
    if not merged and file_fallback_enabled:
        merged = _fallback_file_search(search_query, top_k=final_top_k)
    boost_events = _apply_domain_boost(merged, query_info)
    timings["merge_boost_ms"] = _timing_ms(started)
    rerank_candidate_limit = _env_first_int(["RAG_RERANK_CANDIDATE_LIMIT"], defaults["rerank_candidate_limit"])
    rerank_candidate_limit = max(final_top_k, min(int(rerank_candidate_limit or len(merged)), len(merged)))
    rerank_candidates_input = merged[:rerank_candidate_limit]
    started = time.perf_counter()
    reranked, reranker_name, rerank_error = rerank_candidates(search_query, rerank_candidates_input)
    timings["rerank_ms"] = _timing_ms(started)
    started = time.perf_counter()
    reranked = _apply_post_rerank_adjustments(reranked)
    score_threshold = max(0.0, min(_env_float("RAG_SCORE_THRESHOLD", 0.25), 1.0))
    items = [
        dict(item, document_id=item.get("document_id") or item.get("doc_id"), score=float(item.get("final_score") or item.get("score") or 0.0))
        for item in reranked
        if float(item.get("final_score") or item.get("score") or 0.0) >= score_threshold
    ][:final_top_k]
    timings["post_rerank_adjust_ms"] = _timing_ms(started)
    embedding_provider = get_embedding_provider()
    embedding_provider_name = query_embedding_meta.get("provider") or getattr(embedding_provider, "name", "")
    embedding_model_name = query_embedding_meta.get("model") or getattr(embedding_provider, "model", "")
    timings["total_ms"] = _timing_ms(total_started)
    if items and not domain:
        primary_domain = str(items[0].get("domain") or "").strip()
        items = [item for item in items if str(item.get("domain") or "").strip() == primary_domain]
    items = _domain_consistent_items(items)
    citations = _citations_from_items(items)
    evidence_types = list(
        dict.fromkeys(
            str(item.get("evidence_source_type") or "real")
            for item in items
            if item.get("evidence_source_type")
        )
    )
    return {
        "available": bool(items),
        "source_type": evidence_types[0] if len(evidence_types) == 1 else "derived" if evidence_types else "unavailable",
        "domain": domain or (str(items[0].get("domain") or "") if items else ""),
        "query": query,
        "expanded_query": search_query,
        "items": items,
        "citations": citations,
        "evidence": [
            {
                "source": item.get("source"),
                "title": item.get("title"),
                "chunk_id": item.get("chunk_id"),
                "score": item.get("final_score", item.get("score")),
                "keyword_score": item.get("keyword_score", 0.0),
                "vector_score": item.get("vector_score", 0.0),
                "rerank_score": item.get("rerank_score", 0.0),
                "category_boost": item.get("category_boost", 0.0),
            }
            for item in items
        ],
        "retrieval": {
            "enabled": True,
            "mode": "hybrid",
            "profile": _rag_profile(),
            "keyword_candidates": len(keyword_items),
            "vector_candidates": len(vector_items),
            "merged_candidates": len(merged),
            "rerank_candidates": len(rerank_candidates_input),
            "vector_available": vector_available,
            "embedding_provider": embedding_provider_name,
            "embedding_model": embedding_model_name,
            "embedding_dim": query_embedding_meta.get("dim") or 0,
            "embedding_version": query_embedding_meta.get("version") or "",
            "embedding_fallback": bool(query_embedding_meta.get("fallback")),
            "embedding_error": query_embedding_meta.get("error") or "",
            "dimension_mismatch_count": int(query_embedding_meta.get("dimension_mismatch_count") or 0),
            "vector_index_available": bool(query_embedding_meta.get("vector_index_available")),
            "vector_index_reason": query_embedding_meta.get("vector_index_reason") or "",
            "reranker": reranker_name,
            "rerank_error": rerank_error,
            "score_threshold": score_threshold,
            "file_fallback_enabled": file_fallback_enabled,
            "filters": {
                "domain": domain,
                "source_types": source_types or [],
                "include_historical": include_historical,
                "include_demo": include_demo,
            },
            "query_rewrite": {
                "enabled": bool(query_info.get("enabled")),
                "expanded_terms": query_info.get("expanded_terms") or [],
                "matched_rules": query_info.get("matched_rules") or [],
            },
            "boost_events": boost_events,
        },
        "timings_ms": timings,
        "stats": knowledge_stats(),
    }


@lru_cache(maxsize=256)
def _rag_search_cached(
    query: str,
    top_k: int,
    domain: str,
    source_types: tuple[str, ...],
    include_historical: bool,
    include_demo: bool,
    signature: tuple[str, ...],
) -> dict[str, Any]:
    _ = signature
    return _rag_search_impl(
        query,
        top_k=top_k,
        domain=domain,
        source_types=list(source_types),
        include_historical=include_historical,
        include_demo=include_demo,
    )


def rag_search(
    query: str,
    top_k: int = 5,
    *,
    domain: str = "",
    source_types: list[str] | None = None,
    include_historical: bool = False,
    include_demo: bool = False,
    context: RetrievalContext | None = None,
    enterprise_store: QdrantReadOnlyStore | None = None,
) -> dict[str, Any]:
    if enterprise_mode():
        return _enterprise_rag_search(
            query,
            top_k,
            context=context,
            store=enterprise_store,
            domain=domain,
            source_types=source_types,
            include_historical=include_historical,
            include_demo=include_demo,
        )
    cache_enabled = (_env("RAG_CACHE_ENABLED", "1") or "1").lower() not in {"0", "false", "no", "off"}
    if not cache_enabled or _contains_sensitive_text(query):
        result = _rag_search_impl(
            query,
            top_k=top_k,
            domain=domain,
            source_types=source_types,
            include_historical=include_historical,
            include_demo=include_demo,
        )
        retrieval = result.setdefault("retrieval", {})
        retrieval["cache_enabled"] = bool(cache_enabled)
        retrieval["cache_hit"] = False
        retrieval["cache_skipped_reason"] = "sensitive_query" if _contains_sensitive_text(query) else ""
        return result
    started = time.perf_counter()
    before = _rag_search_cached.cache_info()
    result = copy.deepcopy(
        _rag_search_cached(
            query,
            int(top_k or _env_int("RAG_TOP_K", 5)),
            domain,
            tuple(source_types or []),
            include_historical,
            include_demo,
            _rag_cache_signature(),
        )
    )
    after = _rag_search_cached.cache_info()
    cache_hit = after.hits > before.hits
    retrieval = result.setdefault("retrieval", {})
    retrieval["cache_enabled"] = True
    retrieval["cache_hit"] = cache_hit
    retrieval["cache_ttl_seconds"] = _cache_ttl_seconds()
    timings = result.setdefault("timings_ms", {})
    timings["cache_lookup_ms"] = _timing_ms(started)
    if cache_hit:
        timings["total_ms"] = timings["cache_lookup_ms"]
    return result

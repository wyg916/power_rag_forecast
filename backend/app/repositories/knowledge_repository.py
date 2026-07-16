from __future__ import annotations

import hashlib
import re
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text

from .base import dumps_json, jsonable, loads_json, mapping_list, postgres_engine
from backend.app.services.embedding_service import embed_batch_with_metadata, embed_text_with_metadata, get_embedding_provider


def tokenize(text_value: str) -> list[str]:
    compact = re.sub(r"\s+", "", (text_value or "").lower())
    tokens = [item for item in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", compact) if item]
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fa5]{4,}", token):
            expanded.extend(token[index : index + 2] for index in range(0, len(token) - 1))
    return list(dict.fromkeys(expanded))[:80]


def document_id(source_path: str, content: str) -> str:
    digest = hashlib.sha1(f"{source_path}\n{content}".encode("utf-8", errors="ignore")).hexdigest()
    return "kb_" + digest[:20]


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def split_chunks(content: str, chunk_size: int = 900) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", content or "") if part.strip()]
    chunks: list[str] = []
    current = ""
    for part in parts or [content]:
        normalized = re.sub(r"\s+", " ", part).strip()
        if not normalized:
            continue
        if len(current) + len(normalized) <= chunk_size:
            current = f"{current}\n{normalized}".strip()
        else:
            if current:
                chunks.append(current)
            current = normalized
    if current:
        chunks.append(current)
    output: list[str] = []
    for chunk in chunks:
        if len(chunk) <= chunk_size * 1.4:
            output.append(chunk)
            continue
        for index in range(0, len(chunk), chunk_size):
            output.append(chunk[index : index + chunk_size])
    return output[:200]


SEED_KNOWLEDGE_DOCUMENTS: list[dict[str, Any]] = [
    {
        "title": "浙江省电力市场交易规则（2024版）",
        "source_type": "seed_policy",
        "source_path": "seed://knowledge/zhejiang_market_rules_2024.md",
        "category": "电价政策",
        "content": """
# 浙江省电力市场交易规则（2024版）
售电公司进行中长期和现货交易时，应同时关注日前出清价格、实时偏差、合同电量覆盖率和用户侧负荷波动。
分时电价执行时，高峰时段采购策略应优先控制缺口暴露，低谷时段可结合负荷预测和储能状态安排补充购电。
交易建议必须以实时市场价格、负荷预测、合同约束和风控限额为依据，不能仅依据单一预测结果直接下达交易指令。
""",
    },
    {
        "title": "电力供需平衡与风险管理指引",
        "source_type": "seed_policy",
        "source_path": "seed://knowledge/supply_demand_risk_guide.md",
        "category": "风险管理",
        "content": """
# 电力供需平衡与风险管理指引
供需缺口风险通常集中在晚高峰负荷上行、新能源出力回落和可调资源受限的组合场景。
风险研判应同时比较负荷峰值、新能源出力、可调容量、现货价格区间和历史同期波动。
当预测缺口扩大时，建议提前锁定中长期电量、预留现货补仓额度，并对高价时段设置人工复核阈值。
""",
    },
    {
        "title": "分时电价形成机制与影响因素分析",
        "source_type": "seed_policy",
        "source_path": "seed://knowledge/time_of_use_price_mechanism.md",
        "category": "价格机制",
        "content": """
# 分时电价形成机制与影响因素分析
分时电价受负荷曲线、供给结构、燃料成本、新能源出力、阻塞约束和市场竞价行为共同影响。
高价风险常出现在负荷快速上行、边际机组成本抬升、备用不足或新能源出力低于预期的时段。
售电交易分析应把价格预测和风险解释拆开：预测给出价格区间，风险解释说明驱动因素，策略建议给出可执行的购电窗口。
""",
    },
    {
        "title": "新能源出力预测与偏差处置规则",
        "source_type": "seed_policy",
        "source_path": "seed://knowledge/renewable_forecast_deviation.md",
        "category": "新能源",
        "content": """
# 新能源出力预测与偏差处置规则
新能源出力预测需要结合天气预报、历史出力、装机容量、限电情况和设备可用率。
午间光伏峰值可缓解白天供需压力，但傍晚出力回落会放大晚高峰缺口风险。
当新能源预测不确定性升高时，购电策略应提高备用比例，并在现货市场保留滚动调整空间。
""",
    },
    {
        "title": "售电购电策略生成操作手册",
        "source_type": "seed_playbook",
        "source_path": "seed://knowledge/purchase_strategy_playbook.md",
        "category": "交易策略",
        "content": """
# 售电购电策略生成操作手册
购电策略生成应先判断合同覆盖率，再结合日前价格、实时风险、负荷预测和用户侧可调资源确定补仓方案。
低价窗口可作为分批购电参考，高价窗口应控制裸露电量，并将风险较高时段提交人工复核。
策略输出应包含建议时段、建议动作、依据数据、风险边界和需要人工确认的事项。
""",
    },
    {
        "title": "RAG 知识库问答质量校验规范",
        "source_type": "seed_playbook",
        "source_path": "seed://knowledge/rag_qa_validation.md",
        "category": "知识库运维",
        "content": """
# RAG 知识库问答质量校验规范
检索测试应返回命中文档、片段分数、摘要答案和可复核证据，避免只给自然语言结论。
QA 通过率可根据检索命中数量、最高分、证据覆盖度和答案完整性进行规则化评估。
当检索结果不足时，系统应提示需要补充知识文档或重建索引，而不是编造不存在的政策依据。
""",
    },
]


def _chunk_metadata(metadata: dict[str, Any] | None, embedding_meta: dict[str, Any] | None) -> dict[str, Any]:
    value = dict(metadata or {})
    if embedding_meta:
        value["embedding"] = embedding_meta
    return value


def upsert_document(
    *,
    title: str,
    source_type: str,
    source_path: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "message": "PostgreSQL 不可用"}
    doc_id = document_id(source_path, content)
    chunks = split_chunks(content)
    embedding_results = embed_batch_with_metadata([f"{title}\n{chunk}" for chunk in chunks])
    now = datetime.now()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO kb_documents (
                        doc_id, title, source_type, source_path, checksum,
                        metadata_json, indexed_at, updated_at
                    )
                    VALUES (
                        :doc_id, :title, :source_type, :source_path, :checksum,
                        CAST(:metadata_json AS jsonb), :indexed_at, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (doc_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        source_type = EXCLUDED.source_type,
                        source_path = EXCLUDED.source_path,
                        checksum = EXCLUDED.checksum,
                        metadata_json = EXCLUDED.metadata_json,
                        indexed_at = EXCLUDED.indexed_at,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "doc_id": doc_id,
                    "title": title,
                    "source_type": source_type,
                    "source_path": source_path,
                    "checksum": checksum(content),
                    "metadata_json": dumps_json(metadata or {}),
                    "indexed_at": now,
                },
            )
            conn.execute(text("DELETE FROM kb_chunks WHERE doc_id = :doc_id"), {"doc_id": doc_id})
            for index, chunk in enumerate(chunks):
                embedding_result = embedding_results[index] if index < len(embedding_results) else {"embedding": [], "metadata": {}}
                embedding = embedding_result.get("embedding") or []
                metadata_with_embedding = _chunk_metadata(metadata, embedding_result.get("metadata") or {})
                conn.execute(
                    text(
                        """
                        INSERT INTO kb_chunks (
                            chunk_id, doc_id, chunk_index, content,
                            keywords_json, embedding_json, metadata_json
                        )
                        VALUES (
                            :chunk_id, :doc_id, :chunk_index, :content,
                            CAST(:keywords_json AS jsonb), CAST(:embedding_json AS jsonb),
                            CAST(:metadata_json AS jsonb)
                        )
                        """
                    ),
                    {
                        "chunk_id": f"{doc_id}_{index:04d}",
                        "doc_id": doc_id,
                        "chunk_index": index,
                        "content": chunk,
                        "keywords_json": dumps_json(tokenize(f"{title} {chunk}")),
                        "embedding_json": dumps_json(embedding),
                        "metadata_json": dumps_json(metadata_with_embedding),
                    },
                )
        return {"available": True, "doc_id": doc_id, "chunks": len(chunks)}
    except Exception as exc:
        return {"available": False, "message": str(exc), "doc_id": doc_id}


def search_keyword_chunks(query: str, top_k: int = 20) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    tokens = tokenize(query)
    if not tokens:
        return []
    params = {f"token_{idx}": f"%{token}%" for idx, token in enumerate(tokens[:8])}
    predicates = " OR ".join([f"c.content ILIKE :token_{idx} OR d.title ILIKE :token_{idx}" for idx in range(len(params))])
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content,
                           c.keywords_json, c.embedding_json, c.metadata_json,
                           d.title, d.source_type, d.source_path
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    WHERE COALESCE(d.metadata_json->>'data_origin', '') <> 'seed'
                      AND ({predicates})
                    LIMIT 200
                    """
                ),
                params,
            ).mappings().all()
    except Exception:
        return []
    scored: list[dict[str, Any]] = []
    q_tokens = set(tokens)
    for row in mapping_list(rows):
        keywords = loads_json(row.get("keywords_json"), default=[])
        keyword_set = set(str(item) for item in keywords) if isinstance(keywords, list) else set()
        content = str(row.get("content") or "")
        score = len(q_tokens & keyword_set) + sum(content.lower().count(token.lower()) for token in tokens[:8])
        if score <= 0:
            continue
        scored.append(
            jsonable(
                {
                    "chunk_id": row.get("chunk_id"),
                    "doc_id": row.get("doc_id"),
                    "title": row.get("title"),
                    "source": row.get("source_path"),
                    "source_type": row.get("source_type"),
                    "chunk_index": row.get("chunk_index"),
                    "content": content[:700],
                    "keyword_score": float(score),
                    "vector_score": 0.0,
                    "rerank_score": 0.0,
                    "final_score": float(score),
                    "score": score,
                    "metadata": loads_json(row.get("metadata_json"), default={}),
                }
            )
        )
    scored.sort(key=lambda item: item["keyword_score"], reverse=True)
    return scored[: max(1, min(int(top_k or 20), 100))]


def list_embedded_chunks(limit: int = 2000) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content,
                           c.keywords_json, c.embedding_json, c.metadata_json,
                           d.title, d.source_type, d.source_path
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    WHERE c.embedding_json IS NOT NULL
                      AND COALESCE(d.metadata_json->>'data_origin', '') <> 'seed'
                    ORDER BY d.updated_at DESC NULLS LAST, c.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 2000), 10000))},
            ).mappings().all()
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    for row in mapping_list(rows):
        embedding = loads_json(row.get("embedding_json"), default=[])
        if not isinstance(embedding, list) or not embedding:
            continue
        metadata = loads_json(row.get("metadata_json"), default={})
        embedding_meta = metadata.get("embedding") if isinstance(metadata, dict) else {}
        items.append(
            jsonable(
                {
                    "chunk_id": row.get("chunk_id"),
                    "doc_id": row.get("doc_id"),
                    "title": row.get("title"),
                    "source": row.get("source_path"),
                    "source_type": row.get("source_type"),
                    "chunk_index": row.get("chunk_index"),
                    "content": str(row.get("content") or "")[:900],
                    "embedding": embedding,
                    "embedding_meta": embedding_meta if isinstance(embedding_meta, dict) else {},
                    "keyword_score": 0.0,
                    "vector_score": 0.0,
                    "rerank_score": 0.0,
                    "final_score": 0.0,
                    "metadata": metadata,
                }
            )
        )
    return items


def backfill_missing_embeddings(limit: int = 5000) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "updated": 0, "message": "PostgreSQL 不可用"}
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.chunk_id, c.content, c.metadata_json, d.title
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    WHERE c.embedding_json IS NULL
                       OR (
                            jsonb_typeof(c.embedding_json) = 'array'
                            AND jsonb_array_length(c.embedding_json) = 0
                       )
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 5000), 20000))},
            ).mappings().all()
            updated = 0
            for row in mapping_list(rows):
                embedding_result = embed_text_with_metadata(f"{row.get('title') or ''}\n{row.get('content') or ''}")
                embedding = embedding_result.get("embedding") or []
                if not embedding:
                    continue
                existing_metadata = loads_json(row.get("metadata_json"), default={})
                metadata_with_embedding = _chunk_metadata(
                    existing_metadata if isinstance(existing_metadata, dict) else {},
                    embedding_result.get("metadata") or {},
                )
                conn.execute(
                    text(
                        """
                        UPDATE kb_chunks
                        SET embedding_json = CAST(:embedding_json AS jsonb),
                            metadata_json = CAST(:metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE chunk_id = :chunk_id
                        """
                    ),
                    {
                        "chunk_id": row.get("chunk_id"),
                        "embedding_json": dumps_json(embedding),
                        "metadata_json": dumps_json(metadata_with_embedding),
                    },
                )
                updated += 1
        return {"available": True, "updated": updated}
    except Exception as exc:
        return {"available": False, "updated": 0, "message": str(exc)[:300]}


def refresh_stale_embeddings(limit: int = 20000) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "updated": 0, "message": "PostgreSQL 涓嶅彲鐢?"}
    provider = get_embedding_provider()
    expected_provider = getattr(provider, "name", "")
    expected_model = getattr(provider, "model", "")
    expected_version = getattr(provider, "version", "")
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.chunk_id, c.content, c.embedding_json, c.metadata_json, d.title
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id
                    ORDER BY d.updated_at DESC NULLS LAST, c.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 20000), 50000))},
            ).mappings().all()
    except Exception as exc:
        return {"available": False, "updated": 0, "message": str(exc)[:300]}

    stale_rows: list[dict[str, Any]] = []
    for row in mapping_list(rows):
        metadata = loads_json(row.get("metadata_json"), default={})
        embedding_meta = metadata.get("embedding") if isinstance(metadata, dict) else {}
        embedding = loads_json(row.get("embedding_json"), default=[])
        if not isinstance(embedding_meta, dict):
            embedding_meta = {}
        is_stale = (
            not isinstance(embedding, list)
            or not embedding
            or embedding_meta.get("provider") != expected_provider
            or embedding_meta.get("model") != expected_model
            or embedding_meta.get("version") != expected_version
        )
        # Do not downgrade existing high-dimensional semantic embeddings to the
        # lightweight local hash provider in test or fallback environments.
        if (
            expected_provider == "local_hash"
            and isinstance(embedding, list)
            and len(embedding) >= 768
            and embedding_meta.get("provider") in {"sentence_transformers", "bge"}
        ):
            is_stale = False
        if is_stale:
            stale_rows.append(row)
    if not stale_rows:
        return {
            "available": True,
            "updated": 0,
            "checked": len(rows),
            "provider": expected_provider,
            "model": expected_model,
            "version": expected_version,
        }

    texts = [f"{row.get('title') or ''}\n{row.get('content') or ''}" for row in stale_rows]
    embedding_results = embed_batch_with_metadata(texts)
    updated = 0
    try:
        with engine.begin() as conn:
            for row, embedding_result in zip(stale_rows, embedding_results):
                embedding = embedding_result.get("embedding") or []
                if not embedding:
                    continue
                existing_metadata = loads_json(row.get("metadata_json"), default={})
                metadata_with_embedding = _chunk_metadata(
                    existing_metadata if isinstance(existing_metadata, dict) else {},
                    embedding_result.get("metadata") or {},
                )
                conn.execute(
                    text(
                        """
                        UPDATE kb_chunks
                        SET embedding_json = CAST(:embedding_json AS jsonb),
                            metadata_json = CAST(:metadata_json AS jsonb),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE chunk_id = :chunk_id
                        """
                    ),
                    {
                        "chunk_id": row.get("chunk_id"),
                        "embedding_json": dumps_json(embedding),
                        "metadata_json": dumps_json(metadata_with_embedding),
                    },
                )
                updated += 1
    except Exception as exc:
        return {"available": False, "updated": updated, "checked": len(rows), "stale": len(stale_rows), "message": str(exc)[:300]}
    return {
        "available": True,
        "updated": updated,
        "checked": len(rows),
        "stale": len(stale_rows),
        "provider": expected_provider,
        "model": expected_model,
        "version": expected_version,
    }


def search_chunks(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    return search_keyword_chunks(query, top_k=top_k)


def ensure_seed_knowledge(*, explicit: bool = False) -> dict[str, Any]:
    if not explicit:
        return {
            "available": False,
            "inserted": 0,
            "blocked": True,
            "message": "Knowledge seed is disabled on read paths; use an explicit test/demo seed command.",
        }
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "inserted": 0, "message": "PostgreSQL unavailable"}
    try:
        with engine.connect() as conn:
            seed_count = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM kb_documents
                        WHERE metadata_json->>'data_origin' = 'seed'
                        """
                    )
                ).scalar()
                or 0
            )
    except Exception as exc:
        return {"available": False, "inserted": 0, "message": str(exc)[:300]}
    if seed_count >= len(SEED_KNOWLEDGE_DOCUMENTS):
        return {"available": True, "inserted": 0, "existing": seed_count}

    inserted = 0
    for item in SEED_KNOWLEDGE_DOCUMENTS:
        result = upsert_document(
            title=str(item["title"]),
            source_type=str(item["source_type"]),
            source_path=str(item["source_path"]),
            content=str(item["content"]).strip(),
            metadata={
                "data_origin": "seed",
                "category": item.get("category"),
                "business_domain": "power_trading_knowledge",
                "seed_version": "20260630",
            },
        )
        if result.get("available"):
            inserted += 1
    return {"available": True, "inserted": inserted, "existing": seed_count}


def _doc_status(chunk_count: int, embedded_count: int) -> str:
    if chunk_count <= 0:
        return "pending"
    if embedded_count < chunk_count:
        return "partial"
    return "indexed"


def list_knowledge_documents(page: int = 1, page_size: int = 20, search: str = "") -> dict[str, Any]:
    ensure_seed_knowledge()
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "items": [], "total": 0, "page": page, "page_size": page_size}
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    offset = (safe_page - 1) * safe_page_size
    params: dict[str, Any] = {"limit": safe_page_size, "offset": offset}
    where_sql = "WHERE COALESCE(d.metadata_json->>'data_origin', '') <> 'seed'"
    if search.strip():
        params["search"] = f"%{search.strip()}%"
        where_sql += " AND (d.title ILIKE :search OR d.source_path ILIKE :search OR d.source_type ILIKE :search)"
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        d.doc_id,
                        d.title,
                        d.source_type,
                        d.source_path,
                        d.metadata_json,
                        d.indexed_at,
                        d.updated_at,
                        COUNT(c.chunk_id) AS chunk_count,
                        SUM(
                            CASE
                                WHEN c.embedding_json IS NOT NULL
                                 AND jsonb_typeof(c.embedding_json) = 'array'
                                 AND jsonb_array_length(c.embedding_json) > 0
                                THEN 1 ELSE 0
                            END
                        ) AS embedded_count,
                        COUNT(*) OVER() AS total_count
                    FROM kb_documents d
                    LEFT JOIN kb_chunks c ON c.doc_id = d.doc_id
                    {where_sql}
                    GROUP BY d.doc_id, d.title, d.source_type, d.source_path, d.metadata_json, d.indexed_at, d.updated_at
                    ORDER BY d.updated_at DESC NULLS LAST, d.indexed_at DESC NULLS LAST, d.title ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
    except Exception as exc:
        return {"available": False, "items": [], "total": 0, "page": safe_page, "page_size": safe_page_size, "error": str(exc)[:300]}

    items: list[dict[str, Any]] = []
    total = 0
    for row in mapping_list(rows):
        metadata = loads_json(row.get("metadata_json"), default={})
        chunk_count = int(row.get("chunk_count") or 0)
        embedded_count = int(row.get("embedded_count") or 0)
        status = _doc_status(chunk_count, embedded_count)
        total = int(row.get("total_count") or total or 0)
        items.append(
            {
                "doc_id": row.get("doc_id"),
                "title": row.get("title"),
                "source_type": row.get("source_type"),
                "source_path": row.get("source_path"),
                "category": metadata.get("category") if isinstance(metadata, dict) else "",
                "updated_at": row.get("updated_at"),
                "indexed_at": row.get("indexed_at"),
                "chunk_count": chunk_count,
                "embedded_count": embedded_count,
                "status": status,
                "status_label": {"indexed": "已索引", "partial": "索引中", "pending": "待处理"}.get(status, "待处理"),
            }
        )
    return {"available": True, "items": jsonable(items), "total": total, "page": safe_page, "page_size": safe_page_size}


def knowledge_stats() -> dict[str, Any]:
    ensure_seed_knowledge()
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "documents": 0, "chunks": 0, "embedded_chunks": 0, "pending_documents": 0, "qa_pass_rate": 0.0}
    try:
        with engine.connect() as conn:
            documents = int(
                conn.execute(text("SELECT COUNT(*) FROM kb_documents WHERE COALESCE(metadata_json->>'data_origin', '') <> 'seed'")).scalar()
                or 0
            )
            chunks = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM kb_chunks c
                        JOIN kb_documents d ON d.doc_id = c.doc_id
                        WHERE COALESCE(d.metadata_json->>'data_origin', '') <> 'seed'
                        """
                    )
                ).scalar()
                or 0
            )
            embedded = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM kb_chunks c
                        JOIN kb_documents d ON d.doc_id = c.doc_id
                        WHERE embedding_json IS NOT NULL
                          AND jsonb_typeof(embedding_json) = 'array'
                          AND jsonb_array_length(embedding_json) > 0
                          AND COALESCE(d.metadata_json->>'data_origin', '') <> 'seed'
                        """
                    )
                ).scalar()
                or 0
            )
            pending = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM (
                            SELECT d.doc_id,
                                   COUNT(c.chunk_id) AS chunk_count,
                                   SUM(
                                       CASE
                                           WHEN c.embedding_json IS NOT NULL
                                            AND jsonb_typeof(c.embedding_json) = 'array'
                                            AND jsonb_array_length(c.embedding_json) > 0
                                           THEN 1 ELSE 0
                                       END
                                   ) AS embedded_count
                            FROM kb_documents d
                            LEFT JOIN kb_chunks c ON c.doc_id = d.doc_id
                            WHERE COALESCE(d.metadata_json->>'data_origin', '') <> 'seed'
                            GROUP BY d.doc_id
                        ) s
                        WHERE s.chunk_count = 0 OR COALESCE(s.embedded_count, 0) < s.chunk_count
                        """
                    )
                ).scalar()
                or 0
            )
            last_updated = conn.execute(
                text("SELECT MAX(updated_at) FROM kb_documents WHERE COALESCE(metadata_json->>'data_origin', '') <> 'seed'")
            ).scalar()
            try:
                qa_row = conn.execute(
                    text(
                        """
                        SELECT COUNT(*) AS total,
                               SUM(CASE WHEN passed THEN 1 ELSE 0 END) AS passed
                        FROM (
                            SELECT passed
                            FROM kb_qa_tests
                            ORDER BY created_at DESC
                            LIMIT 50
                        ) t
                        """
                    )
                ).mappings().first()
                qa_total = int((qa_row or {}).get("total") or 0)
                qa_passed = int((qa_row or {}).get("passed") or 0)
            except Exception:
                qa_total = 0
                qa_passed = 0
    except Exception:
        return {"available": False, "documents": 0, "chunks": 0, "embedded_chunks": 0, "pending_documents": 0, "qa_pass_rate": 0.0}
    qa_pass_rate = round((qa_passed / qa_total) * 100, 2) if qa_total else 0.0
    return {
        "available": True,
        "documents": documents,
        "chunks": chunks,
        "embedded_chunks": embedded,
        "pending_documents": pending,
        "qa_pass_rate": qa_pass_rate,
        "qa_total": qa_total,
        "last_updated_at": last_updated.isoformat(sep=" ") if isinstance(last_updated, datetime) else str(last_updated) if last_updated else None,
    }


def record_search_result(query: str, top_k: int, result: dict[str, Any]) -> dict[str, Any]:
    engine = postgres_engine()
    search_id = f"ks_{uuid.uuid4().hex[:16]}"
    if engine is None:
        return {"available": False, "search_id": search_id}
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO kb_search_results (
                        search_id, query_text, top_k, result_count,
                        items_json, retrieval_json, timings_json, created_at
                    )
                    VALUES (
                        :search_id, :query_text, :top_k, :result_count,
                        CAST(:items_json AS jsonb), CAST(:retrieval_json AS jsonb),
                        CAST(:timings_json AS jsonb), CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "search_id": search_id,
                    "query_text": query,
                    "top_k": int(top_k or 5),
                    "result_count": len(result.get("items") or []),
                    "items_json": dumps_json(result.get("items") or []),
                    "retrieval_json": dumps_json(result.get("retrieval") or {}),
                    "timings_json": dumps_json(result.get("timings_ms") or {}),
                },
            )
    except Exception:
        return {"available": False, "search_id": search_id}
    return {"available": True, "search_id": search_id}


def build_qa_answer(question: str, search_result: dict[str, Any]) -> dict[str, Any]:
    items = list(search_result.get("items") or [])
    top = items[0] if items else {}
    titles = list(dict.fromkeys(str(item.get("title") or "").strip() for item in items if item.get("title")))[:5]
    high_score = float(top.get("final_score") or top.get("score") or 0.0) if top else 0.0
    passed = bool(items and high_score > 0)
    if not items:
        blocks = [
            {"key": "conclusion", "title": "结论", "tone": "warning", "content": "本次检索未命中可用知识片段，建议补充文档或重建索引后再次测试。"},
            {"key": "evidence", "title": "依据", "tone": "info", "content": "当前知识库未返回与问题直接相关的片段。"},
            {"key": "action", "title": "建议动作", "tone": "success", "content": "可先上传政策、规则或交易说明文档，再执行索引刷新。"},
        ]
    else:
        snippet = str(top.get("content") or "").strip().replace("\n", " ")
        if len(snippet) > 180:
            snippet = f"{snippet[:180]}..."
        top_title = str(top.get("title") or (titles[0] if titles else "最高分文档"))
        blocks = [
            {
                "key": "conclusion",
                "title": "结论",
                "tone": "success",
                "content": f"本次检索命中 {len(items)} 条知识片段，优先参考《{top_title}》。",
            },
            {
                "key": "evidence",
                "title": "依据",
                "tone": "info",
                "content": "；".join(titles) or "已返回知识片段，但文档标题为空。",
            },
            {
                "key": "summary",
                "title": "答案摘要",
                "tone": "purple",
                "content": snippet or "命中文档未返回片段正文。",
            },
            {
                "key": "risk",
                "title": "风险提示",
                "tone": "warning",
                "content": "售电交易建议仍需结合实时市场、合同约束、负荷预测和人工复核，检索答案仅作为业务分析依据。",
            },
        ]
    answer = "\n".join(f"{block['title']}：{block['content']}" for block in blocks)
    return {"answer": answer, "answer_blocks": blocks, "passed": passed, "confidence": round(min(99.0, max(60.0, high_score * 100)), 2) if items else 0.0}


def record_qa_test(question: str, top_k: int, search_result: dict[str, Any], answer_payload: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    engine = postgres_engine()
    test_id = f"kqa_{uuid.uuid4().hex[:16]}"
    if engine is None:
        return {"available": False, "test_id": test_id}
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO kb_qa_tests (
                        test_id, question, top_k, answer, answer_blocks_json,
                        result_count, passed, confidence, latency_ms,
                        metadata_json, created_at
                    )
                    VALUES (
                        :test_id, :question, :top_k, :answer, CAST(:answer_blocks_json AS jsonb),
                        :result_count, :passed, :confidence, :latency_ms,
                        CAST(:metadata_json AS jsonb), CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "test_id": test_id,
                    "question": question,
                    "top_k": int(top_k or 5),
                    "answer": answer_payload.get("answer") or "",
                    "answer_blocks_json": dumps_json(answer_payload.get("answer_blocks") or []),
                    "result_count": len(search_result.get("items") or []),
                    "passed": bool(answer_payload.get("passed")),
                    "confidence": float(answer_payload.get("confidence") or 0.0),
                    "latency_ms": round(float(latency_ms or 0.0), 3),
                    "metadata_json": dumps_json(
                        {
                            "retrieval": search_result.get("retrieval") or {},
                            "timings_ms": search_result.get("timings_ms") or {},
                            "recorded_by": "knowledge_api",
                        }
                    ),
                },
            )
    except Exception:
        return {"available": False, "test_id": test_id}
    return {"available": True, "test_id": test_id}


def run_qa_from_search(question: str, top_k: int, search_result: dict[str, Any], started_at: float) -> dict[str, Any]:
    answer_payload = build_qa_answer(question, search_result)
    record = record_qa_test(question, top_k, search_result, answer_payload, (time.perf_counter() - started_at) * 1000)
    return {**search_result, **answer_payload, "qa_test": record}

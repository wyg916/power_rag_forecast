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
from backend.app.services.rag_grounding_service import citation_from_retrieval_item

KNOWLEDGE_STATUSES = frozenset({"draft", "active", "superseded", "archived", "invalid"})


def tokenize(text_value: str) -> list[str]:
    compact = re.sub(r"\s+", "", (text_value or "").lower())
    tokens = [item for item in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", compact) if item]
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        if re.fullmatch(r"[\u4e00-\u9fa5]{4,}", token):
            expanded.extend(token[index : index + 2] for index in range(0, len(token) - 1))
    return list(dict.fromkeys(expanded))[:80]


def document_id(source_path: str, content: str, document_version: str = "1") -> str:
    digest = hashlib.sha1(
        f"{source_path}\n{document_version}\n{checksum(content)}".encode("utf-8", errors="ignore")
    ).hexdigest()
    return "kb_" + digest[:20]


def checksum(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def chunk_id(doc_id: str, content: str) -> str:
    return f"{doc_id}_{checksum(content)[:16]}"


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
        sentences = [
            item.strip()
            for item in re.split(r"(?<=[。！？.!?；;])\s*", chunk)
            if item.strip()
        ]
        sentence_chunk = ""
        for sentence in sentences or [chunk]:
            if len(sentence_chunk) + len(sentence) <= chunk_size:
                sentence_chunk = f"{sentence_chunk}{sentence}".strip()
            else:
                if sentence_chunk:
                    output.append(sentence_chunk)
                sentence_chunk = sentence
        if sentence_chunk:
            output.append(sentence_chunk)
    unique: list[str] = []
    seen: set[str] = set()
    for item in output:
        content_hash = checksum(item)
        if content_hash not in seen:
            seen.add(content_hash)
            unique.append(item)
    return unique[:200]


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


def _estimated_token_count(value: str) -> int:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", value or ""))
    words = len(re.findall(r"[A-Za-z0-9_]+", value or ""))
    return max(1, chinese + words)


def _document_metadata(
    *,
    title: str,
    source_type: str,
    source_path: str,
    content: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    value = dict(metadata or {})
    generated_at = str(value.get("generated_at") or datetime.now().isoformat(timespec="seconds"))
    status = str(value.get("status") or "active").strip().lower()
    if status not in KNOWLEDGE_STATUSES:
        status = "invalid"
    value.update(
        {
            "document_version": str(value.get("document_version") or f"sha256:{checksum(content)[:12]}"),
            "title": title,
            "domain": str(value.get("domain") or ""),
            "source_type": str(value.get("evidence_source_type") or "real"),
            "evidence_source_type": str(value.get("evidence_source_type") or "real"),
            "source_name": str(value.get("source_name") or title),
            "source_uri": str(value.get("source_uri") or ""),
            "source_path": source_path,
            "effective_at": value.get("effective_at"),
            "expires_at": value.get("expires_at"),
            "generated_at": generated_at,
            "content_hash": checksum(content),
            "language": str(value.get("language") or "zh-CN"),
            "status": status,
            "tags": list(value.get("tags") or []),
            "evidence_level": str(value.get("evidence_level") or "documented"),
            "storage_source_type": source_type,
        }
    )
    return value


def _normalized_chunk_metadata(
    *,
    document_metadata: dict[str, Any],
    chunk: str,
    chunk_index: int,
    embedding_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    value = _chunk_metadata(document_metadata, embedding_meta)
    value.update(
        {
            "chunk_index": chunk_index,
            "section_title": str(value.get("section_title") or value.get("title") or ""),
            "content_hash": checksum(chunk),
            "token_count": _estimated_token_count(chunk),
            "domain": str(value.get("domain") or ""),
            "source_type": str(value.get("evidence_source_type") or "real"),
            "embedding_status": "ready" if embedding_meta and embedding_meta.get("dim") else "pending",
            "embedding_version": str((embedding_meta or {}).get("version") or ""),
        }
    )
    return value


def upsert_document(
    *,
    title: str,
    source_type: str,
    source_path: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    generate_embeddings: bool = False,
    tenant_id: str = "default",
    owner_actor_id: str | None = None,
) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "message": "PostgreSQL 不可用"}
    document_metadata = _document_metadata(
        title=title,
        source_type=source_type,
        source_path=source_path,
        content=content,
        metadata=metadata,
    )
    tenant_value = str(tenant_id or "default")
    scoped_source_path = (
        source_path
        if tenant_value == "default"
        else f"tenant://{tenant_value}/{source_path}"
    )
    doc_id = document_id(
        scoped_source_path,
        content,
        str(document_metadata["document_version"]),
    )
    document_metadata["document_id"] = doc_id
    is_official = document_metadata.get("data_origin") == "official"
    if is_official:
        required_metadata = ("source_name", "document_version", "generated_at", "domain", "applicability_scope")
        missing = [key for key in required_metadata if not str(document_metadata.get(key) or "").strip()]
        if missing:
            return {
                "available": False,
                "message": f"Official knowledge metadata is incomplete: {','.join(missing)}",
                "doc_id": doc_id,
                "metadata_failed": True,
            }
        if not generate_embeddings:
            return {
                "available": False,
                "message": "Official knowledge requires verified semantic embeddings.",
                "doc_id": doc_id,
                "embedding_failed": True,
            }
    chunks = split_chunks(content)
    embedding_results = (
        embed_batch_with_metadata([f"{title}\n{chunk}" for chunk in chunks])
        if generate_embeddings
        else [{"embedding": [], "metadata": {}} for _ in chunks]
    )
    if generate_embeddings and (
        len(embedding_results) != len(chunks)
        or any(not (item.get("embedding") or []) for item in embedding_results)
    ):
        return {
            "available": False,
            "message": "Embedding generation failed; document was not written.",
            "doc_id": doc_id,
            "embedding_failed": True,
        }
    if is_official:
        invalid_embeddings = []
        for index, item in enumerate(embedding_results):
            vector = item.get("embedding") or []
            embedding_metadata = item.get("metadata") or {}
            if (
                len(vector) != 1024
                or embedding_metadata.get("provider") not in {"sentence_transformers", "bge"}
                or bool(embedding_metadata.get("fallback"))
                or not str(embedding_metadata.get("model") or "").strip()
                or not str(embedding_metadata.get("version") or "").strip()
            ):
                invalid_embeddings.append(index)
        if invalid_embeddings:
            return {
                "available": False,
                "message": "Official knowledge embedding admission failed; BGE 1024 non-fallback vectors are required.",
                "doc_id": doc_id,
                "embedding_failed": True,
                "invalid_embedding_indexes": invalid_embeddings,
            }
    now = datetime.now()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE kb_documents
                    SET metadata_json = jsonb_set(metadata_json, '{status}', '"superseded"'::jsonb, true),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE source_path = :source_path
                      AND tenant_id = :tenant_id
                      AND doc_id <> :doc_id
                      AND COALESCE(metadata_json->>'status', 'active') = 'active'
                    """
                ),
                {
                    "source_path": source_path,
                    "doc_id": doc_id,
                    "tenant_id": tenant_value,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO kb_documents (
                        doc_id, title, source_type, source_path, checksum,
                        metadata_json, indexed_at, updated_at,
                        tenant_id, domain, owner_actor_id
                    )
                    VALUES (
                        :doc_id, :title, :source_type, :source_path, :checksum,
                        CAST(:metadata_json AS jsonb), :indexed_at, CURRENT_TIMESTAMP,
                        :tenant_id, :domain, :owner_actor_id
                    )
                    ON CONFLICT (doc_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        source_type = EXCLUDED.source_type,
                        source_path = EXCLUDED.source_path,
                        checksum = EXCLUDED.checksum,
                        metadata_json = EXCLUDED.metadata_json,
                        domain = EXCLUDED.domain,
                        owner_actor_id = EXCLUDED.owner_actor_id,
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
                    "metadata_json": dumps_json(document_metadata),
                    "indexed_at": now,
                    "tenant_id": tenant_value,
                    "domain": str(document_metadata.get("domain") or ""),
                    "owner_actor_id": str(owner_actor_id or "") or None,
                },
            )
            for index, chunk in enumerate(chunks):
                embedding_result = embedding_results[index] if index < len(embedding_results) else {"embedding": [], "metadata": {}}
                embedding = embedding_result.get("embedding") or []
                metadata_with_embedding = _normalized_chunk_metadata(
                    document_metadata=document_metadata,
                    chunk=chunk,
                    chunk_index=index,
                    embedding_meta=embedding_result.get("metadata") or {},
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO kb_chunks (
                            chunk_id, doc_id, chunk_index, content,
                            keywords_json, embedding_json, metadata_json,
                            tenant_id
                        )
                        VALUES (
                            :chunk_id, :doc_id, :chunk_index, :content,
                            CAST(:keywords_json AS jsonb), CAST(:embedding_json AS jsonb),
                            CAST(:metadata_json AS jsonb), :tenant_id
                        )
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            keywords_json = EXCLUDED.keywords_json,
                            embedding_json = EXCLUDED.embedding_json,
                            metadata_json = EXCLUDED.metadata_json,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    {
                        "chunk_id": chunk_id(doc_id, chunk),
                        "doc_id": doc_id,
                        "chunk_index": index,
                        "content": chunk,
                        "keywords_json": dumps_json(tokenize(f"{title} {chunk}")),
                        "embedding_json": dumps_json(embedding),
                        "metadata_json": dumps_json(metadata_with_embedding),
                        "tenant_id": tenant_value,
                    },
                )
        return {"available": True, "doc_id": doc_id, "chunks": len(chunks)}
    except Exception as exc:
        return {"available": False, "message": str(exc), "doc_id": doc_id}


def _retrieval_filter_sql(
    *,
    domain: str = "",
    source_types: list[str] | None = None,
    include_historical: bool = False,
    include_demo: bool = False,
    tenant_id: str = "default",
) -> tuple[str, dict[str, Any]]:
    tenant_value = str(tenant_id or "default")
    clauses = [
        "d.tenant_id = 'default'" if tenant_value == "default" else "d.tenant_id = :tenant_id",
        "c.tenant_id = d.tenant_id",
        "d.metadata_json->>'data_origin' = 'official'",
        "COALESCE(d.metadata_json->>'status', 'active') = 'active'",
        "COALESCE(c.metadata_json->>'status', '') = 'active'",
        "COALESCE(d.metadata_json->>'domain', '') <> ''",
        "COALESCE(d.metadata_json->>'source_name', '') <> ''",
        "COALESCE(d.metadata_json->>'document_version', '') <> ''",
        "COALESCE(d.metadata_json->>'generated_at', '') <> ''",
        "COALESCE(d.metadata_json->>'applicability_scope', '') <> ''",
        "COALESCE(c.metadata_json->>'domain', '') = COALESCE(d.metadata_json->>'domain', '')",
        "COALESCE(c.metadata_json->>'source_type', '') = COALESCE(d.metadata_json->>'evidence_source_type', 'real')",
    ]
    params: dict[str, Any] = (
        {} if tenant_value == "default" else {"tenant_id": tenant_value}
    )
    allowed_types = [str(item).strip() for item in source_types or [] if str(item).strip()]
    if allowed_types:
        placeholders = []
        for index, source_type in enumerate(allowed_types):
            key = f"source_filter_{index}"
            params[key] = source_type
            placeholders.append(f":{key}")
        clauses.append(
            "COALESCE(d.metadata_json->>'evidence_source_type', 'real') "
            f"IN ({', '.join(placeholders)})"
        )
    else:
        excluded = ["fallback"]
        if not include_historical:
            excluded.append("historical")
        if not include_demo:
            excluded.append("demo")
        for index, source_type in enumerate(excluded):
            key = f"excluded_source_{index}"
            params[key] = source_type
            clauses.append(
                f"COALESCE(d.metadata_json->>'evidence_source_type', 'real') <> :{key}"
            )
    if domain.strip():
        params["domain_filter"] = domain.strip()
        clauses.append("d.metadata_json->>'domain' = :domain_filter")
    return " AND ".join(clauses), params


def search_keyword_chunks(
    query: str,
    top_k: int = 20,
    *,
    domain: str = "",
    source_types: list[str] | None = None,
    include_historical: bool = False,
    include_demo: bool = False,
    tenant_id: str = "default",
) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    tokens = tokenize(query)
    if not tokens:
        return []
    params = {f"token_{idx}": f"%{token}%" for idx, token in enumerate(tokens[:8])}
    predicates = " OR ".join([f"c.content ILIKE :token_{idx} OR d.title ILIKE :token_{idx}" for idx in range(len(params))])
    filter_sql, filter_params = _retrieval_filter_sql(
        domain=domain,
        source_types=source_types,
        include_historical=include_historical,
        include_demo=include_demo,
        tenant_id=tenant_id,
    )
    params.update(filter_params)
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
                    WHERE d.metadata_json->>'data_origin' = 'official'
                      AND {filter_sql}
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
        metadata = loads_json(row.get("metadata_json"), default={})
        score = len(q_tokens & keyword_set) + sum(content.lower().count(token.lower()) for token in tokens[:8])
        if score <= 0:
            continue
        scored.append(
            jsonable(
                {
                    "chunk_id": row.get("chunk_id"),
                    "doc_id": row.get("doc_id"),
                    "document_id": row.get("doc_id"),
                    "title": row.get("title"),
                    "source": row.get("source_path"),
                    "source_path": row.get("source_path"),
                    "source_uri": metadata.get("source_uri") if isinstance(metadata, dict) else "",
                    "source_type": row.get("source_type"),
                    "chunk_index": row.get("chunk_index"),
                    "content": content,
                    "keyword_score": float(score),
                    "vector_score": 0.0,
                    "rerank_score": 0.0,
                    "final_score": float(score),
                    "score": score,
                    "section_title": metadata.get("section_title") if isinstance(metadata, dict) else "",
                    "domain": metadata.get("domain") if isinstance(metadata, dict) else "",
                    "evidence_source_type": metadata.get("source_type") if isinstance(metadata, dict) else "real",
                    "status": metadata.get("status") if isinstance(metadata, dict) else "active",
                    "effective_at": metadata.get("effective_at") if isinstance(metadata, dict) else None,
                    "evidence_level": metadata.get("evidence_level") if isinstance(metadata, dict) else "",
                    "metadata": metadata,
                }
            )
        )
    scored.sort(key=lambda item: item["keyword_score"], reverse=True)
    return scored[: max(1, min(int(top_k or 20), 100))]


def list_embedded_chunks(
    limit: int = 2000,
    *,
    domain: str = "",
    source_types: list[str] | None = None,
    include_historical: bool = False,
    include_demo: bool = False,
    tenant_id: str = "default",
) -> list[dict[str, Any]]:
    engine = postgres_engine()
    if engine is None:
        return []
    filter_sql, filter_params = _retrieval_filter_sql(
        domain=domain,
        source_types=source_types,
        include_historical=include_historical,
        include_demo=include_demo,
        tenant_id=tenant_id,
    )
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
                    WHERE c.embedding_json IS NOT NULL
                      AND d.metadata_json->>'data_origin' = 'official'
                      AND {filter_sql}
                    ORDER BY d.updated_at DESC NULLS LAST, c.created_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    "limit": max(1, min(int(limit or 2000), 10000)),
                    **filter_params,
                },
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
                    "document_id": row.get("doc_id"),
                    "title": row.get("title"),
                    "source": row.get("source_path"),
                    "source_path": row.get("source_path"),
                    "source_uri": metadata.get("source_uri") if isinstance(metadata, dict) else "",
                    "source_type": row.get("source_type"),
                    "chunk_index": row.get("chunk_index"),
                    "content": str(row.get("content") or ""),
                    "embedding": embedding,
                    "embedding_meta": embedding_meta if isinstance(embedding_meta, dict) else {},
                    "keyword_score": 0.0,
                    "vector_score": 0.0,
                    "rerank_score": 0.0,
                    "final_score": 0.0,
                    "section_title": metadata.get("section_title") if isinstance(metadata, dict) else "",
                    "domain": metadata.get("domain") if isinstance(metadata, dict) else "",
                    "evidence_source_type": metadata.get("source_type") if isinstance(metadata, dict) else "real",
                    "status": metadata.get("status") if isinstance(metadata, dict) else "active",
                    "effective_at": metadata.get("effective_at") if isinstance(metadata, dict) else None,
                    "evidence_level": metadata.get("evidence_level") if isinstance(metadata, dict) else "",
                    "metadata": metadata,
                }
            )
        )
    return items


def get_vector_index_rows(limit: int = 50000, *, tenant_id: str = "default") -> list[dict[str, Any]]:
    """Return only active, retrieval-eligible, ready embeddings for an explicit index build."""
    engine = postgres_engine()
    if engine is None:
        return []
    filter_sql, filter_params = _retrieval_filter_sql(
        include_historical=True,
        include_demo=True,
        tenant_id=tenant_id,
    )
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT c.chunk_id, c.embedding_json, c.metadata_json
                FROM kb_chunks c
                JOIN kb_documents d ON d.doc_id = c.doc_id
                WHERE c.embedding_json IS NOT NULL
                  AND COALESCE(c.metadata_json->>'embedding_status', '') = 'ready'
                  AND d.metadata_json->>'data_origin' = 'official'
                  AND {filter_sql}
                ORDER BY c.chunk_id
                LIMIT :limit
                """
            ),
            {"limit": max(1, min(int(limit or 50000), 100000)), **filter_params},
        ).mappings().all()
    output: list[dict[str, Any]] = []
    for row in mapping_list(rows):
        metadata = loads_json(row.get("metadata_json"), default={})
        output.append(
            {
                "chunk_id": str(row.get("chunk_id") or ""),
                "embedding": loads_json(row.get("embedding_json"), default=[]),
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
        )
    return output


def get_chunks_by_ids(
    chunk_ids: list[str],
    *,
    domain: str = "",
    source_types: list[str] | None = None,
    include_historical: bool = False,
    include_demo: bool = False,
    tenant_id: str = "default",
) -> list[dict[str, Any]]:
    engine = postgres_engine()
    ordered_ids = [str(item) for item in chunk_ids if str(item)]
    if engine is None or not ordered_ids:
        return []
    filter_sql, params = _retrieval_filter_sql(
        domain=domain,
        source_types=source_types,
        include_historical=include_historical,
        include_demo=include_demo,
        tenant_id=tenant_id,
    )
    id_params = {f"vector_chunk_{index}": value for index, value in enumerate(ordered_ids)}
    placeholders = ", ".join(f":{key}" for key in id_params)
    params.update(id_params)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content, c.metadata_json,
                       d.title, d.source_type, d.source_path
                FROM kb_chunks c
                JOIN kb_documents d ON d.doc_id = c.doc_id
                WHERE c.chunk_id IN ({placeholders})
                  AND COALESCE(c.metadata_json->>'embedding_status', '') = 'ready'
                  AND d.metadata_json->>'data_origin' = 'official'
                  AND {filter_sql}
                """
            ),
            params,
        ).mappings().all()
    by_id: dict[str, dict[str, Any]] = {}
    for row in mapping_list(rows):
        metadata = loads_json(row.get("metadata_json"), default={})
        metadata = metadata if isinstance(metadata, dict) else {}
        chunk_id_value = str(row.get("chunk_id") or "")
        by_id[chunk_id_value] = jsonable(
            {
                "chunk_id": chunk_id_value,
                "doc_id": row.get("doc_id"),
                "document_id": row.get("doc_id"),
                "title": row.get("title"),
                "source": row.get("source_path"),
                "source_path": row.get("source_path"),
                "source_uri": metadata.get("source_uri", ""),
                "source_type": row.get("source_type"),
                "chunk_index": row.get("chunk_index"),
                "content": str(row.get("content") or ""),
                "section_title": metadata.get("section_title", ""),
                "domain": metadata.get("domain", ""),
                "evidence_source_type": metadata.get("source_type", "real"),
                "status": metadata.get("status", "active"),
                "effective_at": metadata.get("effective_at"),
                "evidence_level": metadata.get("evidence_level", ""),
                "metadata": metadata,
            }
        )
    return [by_id[item] for item in ordered_ids if item in by_id]


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
                    WHERE d.metadata_json->>'data_origin' = 'official'
                      AND (
                           c.embedding_json IS NULL
                           OR (
                            jsonb_typeof(c.embedding_json) = 'array'
                            AND jsonb_array_length(c.embedding_json) = 0
                           )
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
                    WHERE d.metadata_json->>'data_origin' = 'official'
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
                "domain": "demo_knowledge",
                "evidence_source_type": "demo",
                "source_name": str(item["title"]),
                "status": "active",
                "evidence_level": "demo_seed",
            },
            generate_embeddings=True,
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


def list_knowledge_documents(
    page: int = 1,
    page_size: int = 20,
    search: str = "",
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "items": [], "total": 0, "page": page, "page_size": page_size}
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    offset = (safe_page - 1) * safe_page_size
    params: dict[str, Any] = {
        "limit": safe_page_size,
        "offset": offset,
        "tenant_id": str(tenant_id or "default"),
    }
    where_sql = "WHERE d.metadata_json->>'data_origin' = 'official' AND d.tenant_id = :tenant_id"
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
                    LEFT JOIN kb_chunks c ON c.doc_id = d.doc_id AND c.tenant_id = d.tenant_id
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
                "document_id": row.get("doc_id"),
                "title": row.get("title"),
                "source_type": row.get("source_type"),
                "source_path": row.get("source_path"),
                "document_version": metadata.get("document_version") if isinstance(metadata, dict) else "",
                "domain": metadata.get("domain") if isinstance(metadata, dict) else "",
                "evidence_source_type": metadata.get("evidence_source_type") if isinstance(metadata, dict) else "real",
                "source_name": metadata.get("source_name") if isinstance(metadata, dict) else "",
                "source_uri": metadata.get("source_uri") if isinstance(metadata, dict) else "",
                "effective_at": metadata.get("effective_at") if isinstance(metadata, dict) else None,
                "expires_at": metadata.get("expires_at") if isinstance(metadata, dict) else None,
                "generated_at": metadata.get("generated_at") if isinstance(metadata, dict) else None,
                "content_hash": metadata.get("content_hash") if isinstance(metadata, dict) else "",
                "language": metadata.get("language") if isinstance(metadata, dict) else "",
                "knowledge_status": metadata.get("status") if isinstance(metadata, dict) else "active",
                "tags": metadata.get("tags") if isinstance(metadata, dict) else [],
                "evidence_level": metadata.get("evidence_level") if isinstance(metadata, dict) else "",
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


def get_knowledge_document(doc_id: str, *, tenant_id: str = "default") -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "document": None}
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT d.doc_id, d.title, d.source_type, d.source_path, d.checksum,
                           d.metadata_json, d.indexed_at, d.created_at, d.updated_at,
                           COUNT(c.chunk_id) AS chunk_count
                    FROM kb_documents d
                    LEFT JOIN kb_chunks c ON c.doc_id = d.doc_id AND c.tenant_id = d.tenant_id
                    WHERE d.doc_id = :doc_id AND d.tenant_id = :tenant_id
                    GROUP BY d.doc_id, d.title, d.source_type, d.source_path, d.checksum,
                             d.metadata_json, d.indexed_at, d.created_at, d.updated_at
                    """
                ),
                {"doc_id": doc_id, "tenant_id": str(tenant_id or "default")},
            ).mappings().first()
    except Exception as exc:
        return {"available": False, "document": None, "error": str(exc)[:300]}
    if not row:
        return {"available": False, "document": None, "reason": "not_found"}
    value = dict(row)
    metadata = loads_json(value.pop("metadata_json", None), default={})
    value["document_id"] = value.get("doc_id")
    return {"available": True, "document": jsonable({**value, **(metadata if isinstance(metadata, dict) else {})})}


def list_knowledge_chunks(
    doc_id: str,
    page: int = 1,
    page_size: int = 50,
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "items": [], "total": 0}
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 50), 100))
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content,
                           c.metadata_json, c.created_at, c.updated_at,
                           COUNT(*) OVER() AS total_count
                    FROM kb_chunks c
                    WHERE c.doc_id = :doc_id AND c.tenant_id = :tenant_id
                    ORDER BY c.chunk_index
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {
                    "doc_id": doc_id,
                    "tenant_id": str(tenant_id or "default"),
                    "limit": safe_page_size,
                    "offset": (safe_page - 1) * safe_page_size,
                },
            ).mappings().all()
    except Exception as exc:
        return {"available": False, "items": [], "total": 0, "error": str(exc)[:300]}
    items = []
    total = 0
    for row in mapping_list(rows):
        metadata = loads_json(row.get("metadata_json"), default={})
        total = int(row.get("total_count") or total or 0)
        items.append(
            jsonable(
                {
                    "chunk_id": row.get("chunk_id"),
                    "document_id": row.get("doc_id"),
                    "chunk_index": row.get("chunk_index"),
                    "section_title": metadata.get("section_title") if isinstance(metadata, dict) else "",
                    "content": row.get("content"),
                    "content_hash": metadata.get("content_hash") if isinstance(metadata, dict) else "",
                    "token_count": metadata.get("token_count") if isinstance(metadata, dict) else 0,
                    "domain": metadata.get("domain") if isinstance(metadata, dict) else "",
                    "source_type": metadata.get("source_type") if isinstance(metadata, dict) else "real",
                    "embedding_status": metadata.get("embedding_status") if isinstance(metadata, dict) else "pending",
                    "embedding_version": metadata.get("embedding_version") if isinstance(metadata, dict) else "",
                    "metadata": metadata,
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                }
            )
        )
    return {"available": True, "items": items, "total": total, "page": safe_page, "page_size": safe_page_size}


def get_knowledge_citation(chunk_id: str, *, tenant_id: str = "default") -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "citation": None}
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content, c.metadata_json,
                           d.title, d.source_path, d.metadata_json AS document_metadata
                    FROM kb_chunks c
                    JOIN kb_documents d ON d.doc_id = c.doc_id AND d.tenant_id = c.tenant_id
                    WHERE c.chunk_id = :chunk_id AND c.tenant_id = :tenant_id
                    """
                ),
                {"chunk_id": chunk_id, "tenant_id": str(tenant_id or "default")},
            ).mappings().first()
    except Exception as exc:
        return {"available": False, "citation": None, "error": str(exc)[:300]}
    if not row:
        return {"available": False, "citation": None, "reason": "not_found"}
    chunk_metadata = loads_json(row.get("metadata_json"), default={})
    document_metadata = loads_json(row.get("document_metadata"), default={})
    content = str(row.get("content") or "")
    return {
        "available": True,
        "citation": jsonable(
            {
                "document_id": row.get("doc_id"),
                "chunk_id": row.get("chunk_id"),
                "title": row.get("title"),
                "section": chunk_metadata.get("section_title") if isinstance(chunk_metadata, dict) else "",
                "source": row.get("source_path"),
                "domain": chunk_metadata.get("domain") if isinstance(chunk_metadata, dict) else "",
                "source_type": chunk_metadata.get("source_type") if isinstance(chunk_metadata, dict) else "real",
                "evidence_level": document_metadata.get("evidence_level") if isinstance(document_metadata, dict) else "",
                "quote": content,
                "content_hash": chunk_metadata.get("content_hash") if isinstance(chunk_metadata, dict) else checksum(content),
            }
        ),
    }


def knowledge_stats(*, tenant_id: str = "default") -> dict[str, Any]:
    engine = postgres_engine()
    if engine is None:
        return {"available": False, "documents": 0, "chunks": 0, "embedded_chunks": 0, "pending_documents": 0, "qa_pass_rate": 0.0}
    try:
        with engine.connect() as conn:
            documents = int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM kb_documents "
                        "WHERE metadata_json->>'data_origin' = 'official' AND tenant_id = :tenant_id"
                    ),
                    {"tenant_id": str(tenant_id or "default")},
                ).scalar()
                or 0
            )
            chunks = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM kb_chunks c
                        JOIN kb_documents d ON d.doc_id = c.doc_id
                        WHERE d.metadata_json->>'data_origin' = 'official'
                          AND d.tenant_id = :tenant_id
                          AND c.tenant_id = d.tenant_id
                        """
                    ),
                    {"tenant_id": str(tenant_id or "default")},
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
                          AND d.metadata_json->>'data_origin' = 'official'
                          AND d.tenant_id = :tenant_id
                          AND c.tenant_id = d.tenant_id
                        """
                    ),
                    {"tenant_id": str(tenant_id or "default")},
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
                            LEFT JOIN kb_chunks c ON c.doc_id = d.doc_id AND c.tenant_id = d.tenant_id
                            WHERE d.metadata_json->>'data_origin' = 'official'
                              AND d.tenant_id = :tenant_id
                            GROUP BY d.doc_id
                        ) s
                        WHERE s.chunk_count = 0 OR COALESCE(s.embedded_count, 0) < s.chunk_count
                        """
                    ),
                    {"tenant_id": str(tenant_id or "default")},
                ).scalar()
                or 0
            )
            last_updated = conn.execute(
                text(
                    "SELECT MAX(updated_at) FROM kb_documents "
                    "WHERE metadata_json->>'data_origin' = 'official' AND tenant_id = :tenant_id"
                ),
                {"tenant_id": str(tenant_id or "default")},
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
                            WHERE tenant_id = :tenant_id
                            ORDER BY created_at DESC
                            LIMIT 50
                        ) t
                        """
                    ),
                    {"tenant_id": str(tenant_id or "default")},
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
    citations: list[dict[str, Any]] = []
    for item in items[:8]:
        citation, _ = citation_from_retrieval_item(item)
        if citation is None:
            continue
        citation.update(
            section=item.get("section_title") or "",
            source=item.get("source"),
            domain=item.get("domain") or "",
            source_type=item.get("evidence_source_type") or "real",
        )
        citations.append(citation)
    top = items[0] if items and citations else {}
    high_score = float(top.get("final_score") or top.get("score") or 0.0) if top else 0.0
    source_types = list(
        dict.fromkeys(
            str(item.get("evidence_source_type") or "real")
            for item in items
            if item.get("evidence_source_type")
        )
    )
    domains = list(dict.fromkeys(str(item.get("domain") or "") for item in items if item.get("domain")))
    domain_conflict = bool(items) and (len(domains) != 1 or any(not item.get("domain") for item in items))
    if not citations or domain_conflict:
        answer = "当前知识库没有达到相关度门槛且可核验的证据，无法据此回答该问题。"
        blocks = [
            {"key": "conclusion", "title": "结论", "tone": "warning", "content": answer},
            {"key": "evidence", "title": "依据", "tone": "info", "content": "未返回真实可追踪 citation。"},
        ]
        return {
            "available": False,
            "answer": answer,
            "answer_blocks": blocks,
            "source_type": "unavailable",
            "domain": domains[0] if len(domains) == 1 else "",
            "run_id": None,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "confidence": "none",
            "citations": [],
            "evidence": [],
            "passed": False,
        }
    top_content = str(top.get("content") or "").strip()
    answer = top_content[:500]
    blocks = [
        {"key": "conclusion", "title": "知识解释", "tone": "success", "content": answer},
        {
            "key": "evidence",
            "title": "引用依据",
            "tone": "info",
            "content": "；".join(str(item.get("title") or item.get("source") or "") for item in citations[:3]),
        },
    ]
    confidence = "high" if high_score >= 0.65 else "medium" if high_score >= 0.4 else "low"
    source_type = source_types[0] if len(source_types) == 1 else "derived"
    return {
        "available": True,
        "answer": answer,
        "answer_blocks": blocks,
        "source_type": source_type,
        "domain": domains[0] if len(domains) == 1 else "",
        "run_id": None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "confidence": confidence,
        "citations": citations,
        "evidence": citations,
        "passed": True,
    }


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


def run_qa_from_search(
    question: str,
    top_k: int,
    search_result: dict[str, Any],
    started_at: float,
    *,
    record: bool = False,
) -> dict[str, Any]:
    answer_payload = build_qa_answer(question, search_result)
    record_payload = (
        record_qa_test(question, top_k, search_result, answer_payload, (time.perf_counter() - started_at) * 1000)
        if record
        else {"available": False, "recorded": False, "reason": "read_only"}
    )
    return {**search_result, **answer_payload, "qa_test": record_payload}

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.app.config import PROJECT_ROOT


KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge_base"


def _tokens(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text.lower())
    words = set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))
    for item in [
        "电价",
        "负荷",
        "天气",
        "新能源",
        "日前",
        "实时",
        "高峰",
        "低谷",
        "风险",
        "售电",
        "交易",
        "模型",
        "预测",
        "上涨",
        "下跌",
    ]:
        if item in compact:
            words.add(item)
    return words


def _paragraphs(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    chunks = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return [chunk.replace("\n", " ") for chunk in chunks]


def search_knowledge(question: str, limit: int = 4) -> list[dict[str, Any]]:
    try:
        from backend.app.services.rag_service import rag_search

        rag = rag_search(question, top_k=limit)
        if rag.get("items"):
            return [
                {
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "content": item.get("content"),
                    "chunk_id": item.get("chunk_id"),
                    "score": item.get("score"),
                }
                for item in rag.get("items", [])
            ]
    except Exception:
        pass

    if not KNOWLEDGE_ROOT.exists():
        return []
    q_tokens = _tokens(question)
    scored: list[tuple[int, dict[str, Any]]] = []
    for path in sorted(KNOWLEDGE_ROOT.glob("*.md")):
        title_tokens = _tokens(path.stem)
        for paragraph in _paragraphs(path):
            p_tokens = _tokens(paragraph) | title_tokens
            score = len(q_tokens & p_tokens)
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    {
                        "title": path.stem,
                        "source": f"knowledge_base/{path.name}",
                        "content": paragraph[:420],
                    },
                )
            )
    scored.sort(key=lambda item: item[0], reverse=True)
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for _, item in scored:
        key = (item["title"], item["content"])
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output

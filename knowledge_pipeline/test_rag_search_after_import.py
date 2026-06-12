from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.rag_service import rag_search


SOURCE_TYPE = "knowledge_pipeline_jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "knowledge_pipeline" / "output"
DEFAULT_QUERIES = [
    "绿证交易是什么？",
    "什么是电网代理购电？",
    "电力现货交易中的日前市场和实时市场有什么区别？",
    "分时电价政策怎么理解？",
    "峰谷电价为什么能引导用户错峰用电？",
    "新能源项目申报需要关注什么？",
    "LMP 是什么？",
    "电力市场实施细则主要看哪些内容？",
    "现货交易出清是什么意思？",
    "售电交易策略如何利用峰谷价差？",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_print(value: Any) -> None:
    text_value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    try:
        print(text_value)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text_value.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def is_imported_item(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return item.get("source_type") == SOURCE_TYPE or metadata.get("import_source") == SOURCE_TYPE


def item_preview(item: dict[str, Any], rank: int) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    source = str(item.get("source") or "")
    return {
        "rank": rank,
        "title": item.get("title") or metadata.get("title") or "",
        "category": metadata.get("category") or "",
        "source_file": metadata.get("source_file") or Path(source).name,
        "source": source,
        "score": item.get("final_score", item.get("score")),
        "keyword_score": item.get("keyword_score", 0.0),
        "vector_score": item.get("vector_score", 0.0),
        "rerank_score": item.get("rerank_score", 0.0),
        "chunk_id": item.get("chunk_id") or "",
        "original_chunk_id": metadata.get("original_chunk_id") or "",
        "is_imported": is_imported_item(item),
    }


def run_smoke_test(top_k: int = 5) -> dict[str, Any]:
    start = time.time()
    results: list[dict[str, Any]] = []
    for query in DEFAULT_QUERIES:
        query_start = time.time()
        try:
            rag = rag_search(query, top_k=top_k)
            items = [item_preview(item, index + 1) for index, item in enumerate(rag.get("items") or [])]
            imported_hit = any(item["is_imported"] for item in items)
            status = "passed" if imported_hit else "no_imported_hit"
            result = {
                "query": query,
                "status": status,
                "latency_ms": round((time.time() - query_start) * 1000, 1),
                "available": bool(rag.get("available")),
                "imported_hit": imported_hit,
                "top_k": items,
                "retrieval": rag.get("retrieval") or {},
                "stats": rag.get("stats") or {},
            }
        except Exception as exc:
            result = {
                "query": query,
                "status": "error",
                "latency_ms": round((time.time() - query_start) * 1000, 1),
                "available": False,
                "imported_hit": False,
                "top_k": [],
                "error": str(exc)[:500],
            }
        results.append(result)
    imported_hits = sum(1 for item in results if item.get("imported_hit"))
    return {
        "generated_at": now_text(),
        "source_type": SOURCE_TYPE,
        "total": len(results),
        "imported_hits": imported_hits,
        "imported_hit_rate": round(imported_hits / max(1, len(results)), 4),
        "passed": imported_hits == len(results),
        "duration_seconds": round(time.time() - start, 3),
        "results": results,
    }


def write_reports(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "rag_smoke_test_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# RAG 导入后 smoke test 报告",
        "",
        f"- 生成时间：{report.get('generated_at')}",
        f"- 测试问题数：{report.get('total')}",
        f"- 命中新导入知识库问题数：{report.get('imported_hits')}",
        f"- 命中新导入知识库比例：{report.get('imported_hit_rate')}",
        f"- 是否全部命中新导入知识库：{'是' if report.get('passed') else '否'}",
        f"- 耗时秒：{report.get('duration_seconds')}",
        "",
    ]
    for result in report.get("results") or []:
        lines.extend(
            [
                f"## {result.get('query')}",
                "",
                f"- 状态：{result.get('status')}",
                f"- 是否命中新导入知识库：{'是' if result.get('imported_hit') else '否'}",
                f"- 延迟 ms：{result.get('latency_ms')}",
                "",
                "| rank | title | category | source_file | score | 新导入 |",
                "|---:|---|---|---|---:|---|",
            ]
        )
        items = result.get("top_k") or []
        if items:
            for item in items:
                lines.append(
                    f"| {item.get('rank')} | {item.get('title', '')} | {item.get('category', '')} | "
                    f"{item.get('source_file', '')} | {item.get('score', '')} | {'是' if item.get('is_imported') else '否'} |"
                )
        else:
            lines.append("| - | - | - | - | - | - |")
        lines.append("")
    (output_dir / "rag_smoke_test_report.md").write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="验证 knowledge_pipeline 导入后是否能被现有 RAG 检索命中。")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_smoke_test(top_k=max(1, min(int(args.top_k or 5), 20)))
    write_reports(report, args.output.resolve())
    safe_print(report)
    return 0 if report.get("imported_hits", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

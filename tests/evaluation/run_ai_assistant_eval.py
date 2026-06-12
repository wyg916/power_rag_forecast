from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUESTIONS = ROOT / "tests" / "evaluation" / "ai_assistant_eval_questions.json"
DEFAULT_EXPECTED_HITS = ROOT / "tests" / "evaluation" / "rag_expected_hits.json"
DEFAULT_OUTPUT_DIR = ROOT / "tests" / "evaluation" / "output"
_ENV_LOADED = False


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_local_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    _ENV_LOADED = True


def _env(name: str, default: str = "") -> str:
    _load_local_env()
    return os.environ.get(name, default).strip()


def _contains_any(text: str, values: list[str]) -> bool:
    normalized = (text or "").lower()
    return any(str(value).lower() in normalized for value in values if str(value).strip())


def _flatten_text(value: Any, limit: int = 16000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = str(value)
    return text[:limit]


def _post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any], str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "X-User": "eval_runner",
            "X-Role": "admin",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body), body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"error": body}
        return exc.code, parsed, body
    except (TimeoutError, URLError) as exc:
        return 0, {"error": str(exc)}, str(exc)


def _extract_answer(payload: dict[str, Any]) -> str:
    value = payload.get("answer")
    return value if isinstance(value, str) else ""


def _extract_rag(payload: dict[str, Any]) -> dict[str, Any]:
    rag = payload.get("rag")
    return rag if isinstance(rag, dict) else {}


def _extract_rag_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = _extract_rag(payload).get("items") or []
    return [item for item in items if isinstance(item, dict)]


def _extract_tool_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    calls = payload.get("tool_calls") or payload.get("tools") or []
    return [item for item in calls if isinstance(item, dict)]


def _expected_titles(question: dict[str, Any], expected_hits: dict[str, Any]) -> list[str]:
    values: list[str] = []
    values.extend(question.get("expected_titles_any") or [])
    category = question.get("category") or ""
    values.extend((expected_hits.get("category_expected_titles") or {}).get(category) or [])
    values.extend((expected_hits.get("question_overrides") or {}).get(question.get("id") or "") or [])
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _rag_match_text(items: list[dict[str, Any]]) -> str:
    parts = []
    for item in items:
        parts.extend(
            [
                str(item.get("title") or ""),
                str(item.get("source") or ""),
                str(item.get("doc_id") or ""),
                str(item.get("chunk_id") or ""),
                str(item.get("content") or ""),
            ]
        )
    return "\n".join(parts)


def _debug_fields_hidden(default_payload: dict[str, Any], hidden_fields: list[str]) -> tuple[bool, list[str]]:
    leaked = [field for field in hidden_fields if field in default_payload]
    return not leaked, leaked


def _infer_report_name(results: list[dict[str, Any]]) -> str:
    providers: Counter[str] = Counter()
    rerankers: Counter[str] = Counter()
    for item in results:
        retrieval = (((item.get("debug_response") or {}).get("rag") or {}).get("retrieval") or {})
        provider = str(retrieval.get("embedding_provider") or "").lower()
        model = str(retrieval.get("embedding_model") or "").lower()
        reranker = str(retrieval.get("reranker") or "").lower()
        if provider or model:
            providers[f"{provider}:{model}"] += 1
        if reranker:
            rerankers[reranker] += 1
    provider_names = " ".join(key.split(":", 1)[0] for key in providers.keys())
    provider_blob = " ".join(providers.keys())
    reranker_blob = " ".join(rerankers.keys())
    if not provider_blob and not reranker_blob:
        env_embedding_provider = _env("RAG_EMBEDDING_PROVIDER", "").lower()
        env_reranker_provider = _env("RAG_RERANK_PROVIDER", "").lower()
        if env_embedding_provider in {"sentence_transformers", "sentence-transformers", "bge"}:
            if env_reranker_provider in {"bge", "bge_reranker", "transformers", "local_bge"}:
                return "bge_embedding_reranker_report"
            return "bge_embedding_report"
        return "baseline_hash_heuristic_report"
    if "local_hash" in provider_names or "hash" in provider_names:
        return "baseline_hash_heuristic_report"
    if any(key in provider_blob for key in ["sentence", "bge"]):
        if "bge" in reranker_blob:
            return "bge_embedding_reranker_report"
        return "bge_embedding_report"
    return "baseline_hash_heuristic_report"


def _rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _evaluate_one(
    question: dict[str, Any],
    expected_hits: dict[str, Any],
    base_url: str,
    model_provider: str,
    answer_style: str,
    timeout: float,
) -> dict[str, Any]:
    session_suffix = f"{question.get('id')}_{int(time.time() * 1000)}"
    endpoint = base_url.rstrip("/") + "/api/ai/chat"
    common_payload = {
        "question": question["question"],
        "session_id": f"eval_{session_suffix}",
        "run_id": "latest",
        "model_provider": model_provider,
        "answer_style": answer_style,
        "debug": False,
    }
    started = time.perf_counter()
    status, default_response, default_raw = _post_json(endpoint, common_payload, timeout)
    default_latency_ms = round((time.perf_counter() - started) * 1000, 1)
    debug_payload = dict(common_payload, session_id=f"eval_debug_{session_suffix}", debug=True)
    started = time.perf_counter()
    debug_status, debug_response, debug_raw = _post_json(endpoint, debug_payload, timeout)
    debug_latency_ms = round((time.perf_counter() - started) * 1000, 1)

    answer = _extract_answer(default_response)
    debug_answer = _extract_answer(debug_response)
    rag_items = _extract_rag_items(debug_response)
    rag_text = _rag_match_text(rag_items)
    expected_titles = _expected_titles(question, expected_hits)
    expected_keywords = [str(value) for value in question.get("expected_keywords_any") or []]
    expected_points = [str(value) for value in question.get("expected_answer_points") or []]
    forbidden_patterns = [str(value) for value in question.get("forbidden_patterns") or []]
    hidden_fields = [str(value) for value in question.get("default_should_hide") or []]

    hidden_ok, leaked_fields = _debug_fields_hidden(default_response, hidden_fields)
    forbidden_hit = [item for item in forbidden_patterns if item and item in answer]
    answer_point_hits = [item for item in expected_points if item and item in answer]
    answer_keyword_hit = _contains_any(answer, expected_keywords)
    title_hit = _contains_any(rag_text, expected_titles)
    keyword_hit = _contains_any(rag_text + "\n" + answer, expected_keywords)
    should_use_rag = bool(question.get("should_use_rag"))
    should_use_tools = bool(question.get("should_use_tools"))
    tool_calls = _extract_tool_calls(debug_response)
    rag_used = len(rag_items) > 0
    tools_used = len(tool_calls) > 0
    debug_has_rag = "rag" in debug_response
    debug_has_trace = "trace" in debug_response or "trace_id" in debug_response

    checks = {
        "default_status_ok": 200 <= status < 300,
        "debug_status_ok": 200 <= debug_status < 300,
        "answer_non_empty": bool(answer.strip() or debug_answer.strip()),
        "default_debug_fields_hidden": hidden_ok,
        "forbidden_patterns_absent": not forbidden_hit,
        "rag_expectation_ok": rag_used if should_use_rag else True,
        "tool_expectation_ok": tools_used if should_use_tools else True,
        "top_k_title_hit": title_hit if should_use_rag else True,
        "keyword_hit": keyword_hit if should_use_rag else (answer_keyword_hit or True),
        "answer_point_hit": bool(answer_point_hits) if expected_points else True,
        "debug_has_rag": debug_has_rag,
        "debug_has_trace": debug_has_trace,
    }
    failed_checks = [name for name, ok in checks.items() if not ok]
    return {
        "id": question.get("id"),
        "category": question.get("category"),
        "question": question.get("question"),
        "should_use_rag": should_use_rag,
        "should_use_tools": should_use_tools,
        "status": status,
        "debug_status": debug_status,
        "latency_ms": default_latency_ms,
        "debug_latency_ms": debug_latency_ms,
        "answer": answer[:2000],
        "rag_hits": len(rag_items),
        "tool_calls": len(tool_calls),
        "expected_titles_any": expected_titles,
        "expected_keywords_any": expected_keywords,
        "expected_answer_points": expected_points,
        "answer_point_hits": answer_point_hits,
        "forbidden_hits": forbidden_hit,
        "leaked_default_fields": leaked_fields,
        "checks": checks,
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "rag_items_preview": [
            {
                "rank": index + 1,
                "chunk_id": item.get("chunk_id"),
                "doc_id": item.get("doc_id"),
                "title": item.get("title"),
                "source": item.get("source"),
                "keyword_score": item.get("keyword_score"),
                "vector_score": item.get("vector_score"),
                "rerank_score": item.get("rerank_score"),
                "final_score": item.get("final_score"),
            }
            for index, item in enumerate(rag_items[:5])
        ],
        "debug_response": {
            "intent": debug_response.get("intent"),
            "task_type": debug_response.get("task_type"),
            "model_provider_used": debug_response.get("model_provider_used"),
            "model_fallback": debug_response.get("model_fallback"),
            "rag": _extract_rag(debug_response),
            "trace_id_present": bool(debug_response.get("trace_id")),
        },
        "error_preview": "" if status else default_raw[:500],
        "debug_error_preview": "" if debug_status else debug_raw[:500],
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = defaultdict(lambda: Counter())
    for result in results:
        category = result["category"]
        bucket = by_category[category]
        bucket["total"] += 1
        bucket["passed"] += int(bool(result["passed"]))
        bucket["rag_expected"] += int(bool(result["should_use_rag"]))
        bucket["rag_used_when_expected"] += int(bool(result["should_use_rag"] and result["rag_hits"] > 0))
        bucket["top_k_title_hit"] += int(bool(result["checks"].get("top_k_title_hit")))
        bucket["default_hidden_ok"] += int(bool(result["checks"].get("default_debug_fields_hidden")))
        bucket["answer_point_hit"] += int(bool(result["checks"].get("answer_point_hit")))
    category_summary = {}
    for category, counter in sorted(by_category.items()):
        total = counter["total"]
        rag_expected = counter["rag_expected"]
        category_summary[category] = {
            "total": total,
            "passed": counter["passed"],
            "pass_rate": _rate(counter["passed"], total),
            "rag_expected": rag_expected,
            "rag_hit_rate_when_expected": _rate(counter["rag_used_when_expected"], rag_expected),
            "top_k_title_hit_rate": _rate(counter["top_k_title_hit"], total),
            "default_hidden_rate": _rate(counter["default_hidden_ok"], total),
            "answer_point_hit_rate": _rate(counter["answer_point_hit"], total),
        }
    total = len(results)
    rag_expected_total = sum(1 for item in results if item["should_use_rag"])
    hidden_ok_total = sum(1 for item in results if item["checks"].get("default_debug_fields_hidden"))
    top_k_title_total = sum(1 for item in results if item["checks"].get("top_k_title_hit"))
    passed_total = sum(1 for item in results if item["passed"])
    latencies = [item["latency_ms"] for item in results if item.get("latency_ms") is not None]
    return {
        "total": total,
        "passed": passed_total,
        "failed": total - passed_total,
        "pass_rate": _rate(passed_total, total),
        "rag_expected_total": rag_expected_total,
        "rag_hit_rate_when_expected": _rate(
            sum(1 for item in results if item["should_use_rag"] and item["rag_hits"] > 0),
            rag_expected_total,
        ),
        "top_k_title_hit_rate": _rate(top_k_title_total, total),
        "default_hidden_rate": _rate(hidden_ok_total, total),
        "answer_point_hit_rate": _rate(sum(1 for item in results if item["checks"].get("answer_point_hit")), total),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else math.nan,
        "category_summary": category_summary,
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# {report['report_name']}",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- Base URL：`{report['base_url']}`",
        f"- 模型路由：`{report['model_provider']}`",
        f"- 题目总数：{summary['total']}",
        f"- 总通过率：{summary['passed']}/{summary['total']} ({summary['pass_rate']:.2%})",
        f"- RAG 期望命中率：{summary['rag_hit_rate_when_expected']:.2%}",
        f"- Top-K 标题命中率：{summary['top_k_title_hit_rate']:.2%}",
        f"- 默认隐藏调试字段通过率：{summary['default_hidden_rate']:.2%}",
        f"- 平均默认响应耗时：{summary['avg_latency_ms']} ms",
        "",
        "## 分类结果",
        "",
        "| 分类 | 题数 | 通过率 | RAG期望命中率 | Top-K标题命中率 | 默认隐藏通过率 | 答案要点命中率 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for category, item in summary["category_summary"].items():
        lines.append(
            f"| {category} | {item['total']} | {item['pass_rate']:.2%} | "
            f"{item['rag_hit_rate_when_expected']:.2%} | {item['top_k_title_hit_rate']:.2%} | "
            f"{item['default_hidden_rate']:.2%} | {item['answer_point_hit_rate']:.2%} |"
        )
    lines.extend(["", "## 检索与模型信息", ""])
    retrieval_counter: Counter[str] = Counter()
    for item in report["results"]:
        retrieval = ((item.get("debug_response") or {}).get("rag") or {}).get("retrieval") or {}
        key = (
            f"embedding={retrieval.get('embedding_provider') or '-'} / "
            f"model={retrieval.get('embedding_model') or '-'} / "
            f"reranker={retrieval.get('reranker') or '-'}"
        )
        retrieval_counter[key] += 1
    for key, count in retrieval_counter.most_common():
        lines.append(f"- {key}：{count} 条")
    failures = report["failures"]
    lines.extend(["", f"## 失败案例（{len(failures)}）", ""])
    if failures:
        lines.append("| ID | 分类 | 问题 | 失败检查 | RAG命中 | 证据预览 |")
        lines.append("|---|---|---|---|---:|---|")
        for item in failures[:50]:
            previews = "; ".join(
                str(rag.get("title") or rag.get("source") or rag.get("chunk_id") or "")
                for rag in item.get("rag_items_preview", [])[:3]
            )
            failed = ", ".join(item.get("failed_checks") or [])
            question = str(item.get("question") or "").replace("|", " ")
            lines.append(f"| {item['id']} | {item['category']} | {question} | {failed} | {item['rag_hits']} | {previews.replace('|', ' ')} |")
    else:
        lines.append("暂无失败案例。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed AI assistant evaluation against /api/ai/chat.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--model-provider", default="auto")
    parser.add_argument("--answer-style", default="professional_brief")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--expected-hits", type=Path, default=DEFAULT_EXPECTED_HITS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-name", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()

    questions = _load_json(args.questions, [])
    expected_hits = _load_json(args.expected_hits, {})
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        print("No evaluation questions found.", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    total = len(questions)
    partial_path = args.output_dir / "latest_partial_results.jsonl"
    if partial_path.exists():
        partial_path.write_text("", encoding="utf-8")
    if args.workers > 0:
        workers = max(1, min(args.workers, 8))
    else:
        reranker_provider = _env("RAG_RERANK_PROVIDER", "").lower()
        workers = 1 if reranker_provider in {"bge", "bge_reranker", "transformers", "local_bge"} else 4
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                _evaluate_one,
                question=question,
                expected_hits=expected_hits,
                base_url=args.base_url,
                model_provider=args.model_provider,
                answer_style=args.answer_style,
                timeout=args.timeout,
            ): index
            for index, question in enumerate(questions)
        }
        completed = 0
        with partial_path.open("a", encoding="utf-8") as partial_file:
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    question = questions[index]
                    result = {
                        "id": question.get("id"),
                        "category": question.get("category"),
                        "question": question.get("question"),
                        "should_use_rag": bool(question.get("should_use_rag")),
                        "should_use_tools": bool(question.get("should_use_tools")),
                        "status": 0,
                        "debug_status": 0,
                        "latency_ms": 0,
                        "debug_latency_ms": 0,
                        "answer": "",
                        "rag_hits": 0,
                        "tool_calls": 0,
                        "failed_checks": ["runner_exception"],
                        "checks": {"runner_exception": False},
                        "passed": False,
                        "error_preview": str(exc)[:500],
                    }
                result["_eval_order"] = index
                results.append(result)
                partial_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                partial_file.flush()
                completed += 1
                status = "PASS" if result["passed"] else "FAIL"
                print(
                    f"[{completed:03d}/{total}] {status} {result['id']} "
                    f"rag={result.get('rag_hits', 0)} latency={result.get('latency_ms', 0)}ms",
                    flush=True,
                )
    results.sort(key=lambda item: int(item.get("_eval_order", 0)))
    for item in results:
        item.pop("_eval_order", None)

    report_name = args.report_name.strip() or _infer_report_name(results)
    summary = _summarize(results)
    failures = [item for item in results if not item["passed"]]
    report = {
        "report_name": report_name,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "base_url": args.base_url,
        "model_provider": args.model_provider,
        "answer_style": args.answer_style,
        "questions_file": str(args.questions),
        "expected_hits_file": str(args.expected_hits),
        "summary": summary,
        "failures": failures,
        "results": results,
    }
    json_path = args.output_dir / f"{report_name}.json"
    md_path = args.output_dir / f"{report_name}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")
    print(
        f"Summary: passed={summary['passed']}/{summary['total']} "
        f"pass_rate={summary['pass_rate']:.2%} "
        f"rag_hit_rate={summary['rag_hit_rate_when_expected']:.2%} "
        f"default_hidden_rate={summary['default_hidden_rate']:.2%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

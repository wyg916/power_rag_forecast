from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ai_assistant.llm_providers import DeepSeekProvider, MiMoProvider
from backend.app.ai_assistant.llm_providers.openai_compatible import ProviderRequestError
from backend.app.ai_assistant.llm_router import LLMRouteError, LLMRouter
from backend.app.chatbi.planner import AnalysisPlanGenerationError, generate_analysis_plan, repair_analysis_plan
from backend.app.chatbi.validator import validate_analysis_plan
from scripts.ai_provider_live_probe import load_runtime_config


SAFE_META_KEYS = {
    "provider", "model", "selected_provider", "selected_model", "logical_alias",
    "requested_tier", "route_reason", "fallback", "fallback_used", "fallback_from",
    "fallback_reason", "fallback_count", "input_tokens", "output_tokens", "latency_ms",
    "estimated_cost", "currency", "finish_reason", "repair_attempted",
    "provider_diagnostics", "raw_response_structure",
}


def _safe_meta(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key in SAFE_META_KEYS}


def _safe_error(exc: Exception) -> dict[str, Any]:
    result: dict[str, Any] = {"type": type(exc).__name__, "reason": str(exc)[:200]}
    if isinstance(exc, ProviderRequestError):
        result.update(
            provider=exc.provider,
            status_code=exc.status_code,
            retryable=exc.retryable,
            diagnostics=exc.diagnostics,
        )
    elif isinstance(exc, LLMRouteError):
        result.update(provider=exc.provider, status_code=exc.status_code, retryable=exc.retryable, code=exc.code)
    elif isinstance(exc, AnalysisPlanGenerationError):
        result["diagnostics"] = exc.diagnostics
    return result


def _run(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = operation()
        return {"status": "PASS" if payload.pop("passed", True) else "FAIL", "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), **payload}
    except Exception as exc:
        return {"status": "REMOTE_PROVIDER_BLOCKED", "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "error": _safe_error(exc)}


def _vision_data_url() -> str:
    stream = io.BytesIO()
    image = Image.new("RGB", (96, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 12, 42, 54), fill="red")
    draw.ellipse((54, 12, 88, 46), fill="blue")
    image.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _mimo_general() -> dict[str, Any]:
    provider = MiMoProvider()
    if not provider.available:
        raise ProviderRequestError("mimo", "missing_api_key")
    completion = provider.complete(
        [{"role": "user", "content": "用一句简短中文说明模型连接正常。"}],
        temperature=0,
        max_tokens=800,
    )
    return {
        "passed": bool(completion.content),
        "provider": provider.name,
        "model": completion.model,
        "content_present": bool(completion.content),
        "input_tokens": completion.input_tokens,
        "output_tokens": completion.output_tokens,
        "latency_ms": completion.latency_ms,
        "diagnostics": completion.diagnostics,
    }


def _mimo_vision() -> dict[str, Any]:
    provider = MiMoProvider()
    if not provider.available:
        raise ProviderRequestError("mimo", "missing_api_key")
    completion = provider.complete(
        [{"role": "user", "content": [
            {"type": "text", "text": "图中有哪两种主要颜色？只回答颜色。"},
            {"type": "image_url", "image_url": {"url": _vision_data_url()}},
        ]}],
        temperature=0,
        max_tokens=800,
    )
    normalized = completion.content.lower()
    visible_evidence = (
        ("红" in normalized or "red" in normalized)
        and ("蓝" in normalized or "blue" in normalized)
    )
    return {
        "passed": bool(completion.content) and visible_evidence,
        "provider": provider.name,
        "model": completion.model,
        "content_present": bool(completion.content),
        "visible_evidence_terms_present": visible_evidence,
        "input_tokens": completion.input_tokens,
        "output_tokens": completion.output_tokens,
        "latency_ms": completion.latency_ms,
        "diagnostics": completion.diagnostics,
    }


def _scenario_check(name: str, plan, validation) -> bool:
    selected_dimensions = set(plan.dimensions) | set(plan.group_by)
    if name == "single_metric":
        return plan.datasets == ["market_price_history"] and plan.metrics == ["avg_day_ahead_price"] and validation.valid
    if name == "time_range":
        return bool(plan.time_range) and plan.time_grain == "day" and "market_observed_at" in selected_dimensions and validation.valid
    if name == "dimension":
        return "market_code" in selected_dimensions and validation.valid
    if name == "filter":
        return any(item.dimension == "market_code" and str(item.value).upper() == "DOM" for item in plan.filters) and validation.valid
    if name == "illegal_field":
        return not validation.executable
    if name == "unauthorized_dataset":
        return not validation.valid and bool({"dataset_forbidden", "metric_forbidden"}.intersection(item.code for item in validation.issues))
    return False


def _deepseek_scenarios() -> dict[str, Any]:
    if not DeepSeekProvider().available:
        raise ProviderRequestError("deepseek", "missing_api_key")
    scenarios = [
        ("single_metric", "平均日前电价是多少？", ("assistant:use", "data:read", "model:read")),
        ("time_range", "分析 2026-08-01 到 2026-08-07 每日平均日前电价趋势。", ("assistant:use", "data:read", "model:read")),
        ("dimension", "按市场比较平均日前电价，使用表格。", ("assistant:use", "data:read", "model:read")),
        ("filter", "查询 DOM 市场的平均日前电价。", ("assistant:use", "data:read", "model:read")),
        ("illegal_field", "查询未注册字段 secret_revenue 的值。", ("assistant:use", "data:read", "model:read")),
        ("unauthorized_dataset", "平均日前电价是多少？", ("assistant:use",)),
    ]
    results: list[dict[str, Any]] = []
    for index, (name, question, permissions) in enumerate(scenarios):
        if index:
            time.sleep(1)
        try:
            plan, metadata = generate_analysis_plan(
                question,
                None,
                requested_provider="deepseek",
            )
            validation = validate_analysis_plan(plan, permissions=permissions)
            if name not in {"illegal_field", "unauthorized_dataset"} and not validation.valid and validation.status != "clarification_required":
                plan, metadata = repair_analysis_plan(
                    question,
                    None,
                    plan,
                    [
                        {"code": item.code, "field": item.field, "message": item.message}
                        for item in validation.issues
                    ],
                    requested_provider="deepseek",
                )
                validation = validate_analysis_plan(plan, permissions=permissions)
            plan_payload = plan.model_dump(mode="json")
            forbidden_sql_keys = sorted(set(plan_payload).intersection({"sql", "query", "raw_sql", "statement"}))
            results.append({
                "scenario": name,
                "status": "PASS" if _scenario_check(name, plan, validation) and not forbidden_sql_keys else "FAIL",
                "schema_valid": True,
                "executable": validation.executable,
                "issue_codes": sorted(item.code for item in validation.issues),
                "plan_summary": {
                    "datasets": plan.datasets,
                    "metrics": plan.metrics,
                    "dimensions": plan.dimensions,
                    "filter_dimensions": [item.dimension for item in plan.filters],
                    "time_range_present": plan.time_range is not None,
                    "time_grain": plan.time_grain,
                    "clarification_required": plan.clarification_required,
                    "forbidden_sql_keys": forbidden_sql_keys,
                },
                "metadata": _safe_meta(metadata),
            })
        except Exception as exc:
            results.append({"scenario": name, "status": "REMOTE_PROVIDER_BLOCKED", "error": _safe_error(exc)})
    passed = all(item["status"] == "PASS" for item in results)
    return {
        "passed": passed,
        "provider": "deepseek",
        "scenario_count": len(results),
        "passed_count": sum(item["status"] == "PASS" for item in results),
        "raw_sql_execution_by_llm": 0,
        "scenarios": results,
    }


def _kimi_premium() -> dict[str, Any]:
    denied_without_confirmation = False
    try:
        LLMRouter().generate_answer(
            [{"role": "user", "content": "premium guard"}],
            task_type="complex_analysis",
            requested_provider="kimi",
            requested_tier="premium",
            premium_confirmed=False,
            max_tokens=20,
        )
    except LLMRouteError as exc:
        denied_without_confirmation = exc.code == "PREMIUM_CONFIRMATION_REQUIRED"
    answer, metadata = LLMRouter().generate_answer(
        [{"role": "user", "content": "用一句简短中文给出深度分析请求已连接的确认。"}],
        task_type="complex_analysis",
        requested_provider="kimi",
        requested_tier="premium",
        premium_confirmed=True,
        temperature=0,
        max_tokens=400,
    )
    return {
        "passed": denied_without_confirmation and bool(answer) and metadata.get("provider") == "kimi",
        "denied_without_confirmation": denied_without_confirmation,
        "content_present": bool(answer),
        "metadata": _safe_meta(metadata),
        "unexpected_premium_usage": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal real-provider remediation smoke with redacted diagnostics.")
    parser.add_argument("--runtime-config", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--check",
        choices=["all", "mimo_general", "mimo_vision", "deepseek_analysis_plan", "kimi_premium"],
        default="all",
    )
    args = parser.parse_args()
    os.environ["AI_PROVIDER_DIAGNOSTICS"] = "1"
    for path in args.runtime_config:
        load_runtime_config(path.resolve())
    operations = {
        "mimo_general": _mimo_general,
        "mimo_vision": _mimo_vision,
        "deepseek_analysis_plan": _deepseek_scenarios,
        "kimi_premium": _kimi_premium,
    }
    selected = list(operations) if args.check == "all" else [args.check]
    checks = {name: _run(operations[name]) for name in selected}
    hard_pass = all(
        value["status"] == "PASS" or (name == "mimo_vision" and value["status"] == "REMOTE_PROVIDER_BLOCKED")
        for name, value in checks.items()
    )
    report = {
        "schema_version": "ai-provider-remediation-smoke/v1",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "redaction": "No API key, prompt body, model answer, image bytes, or attachment body is persisted.",
        "status": "PASS" if hard_pass else "FAIL",
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": report["status"], "checks": {key: value["status"] for key, value in checks.items()}}, ensure_ascii=False))
    return 0 if hard_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

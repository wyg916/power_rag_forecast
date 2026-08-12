from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from backend.app.ai_assistant.llm_providers import DeepSeekProvider, KimiProvider, MiMoProvider
from backend.app.ai_assistant.llm_providers.openai_compatible import ProviderRequestError
from backend.app.chatbi.contracts import AnalysisPlan
from scripts.ai_provider_live_probe import load_runtime_config


PROVIDERS = {"kimi": KimiProvider, "mimo": MiMoProvider, "deepseek": DeepSeekProvider}
PLAN_SCHEMA = {
    "type": "object",
    "required": ["datasets", "metrics", "dimensions"],
    "properties": {
        "datasets": {"type": "array", "items": {"type": "string"}},
        "metrics": {"type": "array", "items": {"type": "string"}},
        "dimensions": {"type": "array", "items": {"type": "string"}},
        "filters": {"type": "array"},
        "group_by": {"type": "array", "items": {"type": "string"}},
        "order_by": {"type": "array"},
        "limit": {"type": "integer"},
        "joins": {"type": "array", "items": {"type": "string"}},
        "chart_intent": {"type": "string"},
        "analysis_mode": {"type": "string"},
        "clarification_required": {"type": "boolean"},
    },
}


def _fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else ""


def _run_check(provider: Any, name: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        payload = operation()
        return {"passed": bool(payload.pop("passed", True)), "latency_ms": round((time.perf_counter() - started) * 1000, 3), **payload}
    except ProviderRequestError as exc:
        return {
            "passed": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "reason": exc.reason,
            "status_code": exc.status_code,
            "retryable": exc.retryable,
        }
    except Exception as exc:
        return {
            "passed": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "reason": exc.__class__.__name__,
        }


def _provider_matrix(name: str, selected_check: str = "all") -> dict[str, Any]:
    provider = PROVIDERS[name]()
    delay = float(os.environ.get(f"{name.upper()}_PROBE_DELAY_SECONDS", "22" if name == "kimi" else "1"))
    health = provider.health()
    result: dict[str, Any] = {
        "provider": name,
        "model": provider.default_model,
        "base_url": provider.base_url,
        "key_fingerprint": _fingerprint(provider.api_key),
        "request_spacing_seconds": delay,
        "checks": {
            "authentication_models": {
                "passed": bool(health.get("available")),
                "model_visible": provider.default_model in (health.get("models") or []),
                "reason": health.get("reason", ""),
            }
        },
    }
    if not provider.available:
        result["status"] = "BLOCKED_MISSING_KEY"
        return result

    operations: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        (
            "general_chat",
            lambda: {
                "passed": bool((answer := provider.complete(
                    [{"role": "user", "content": "用一句中文说明连接正常。"}], max_tokens=160, temperature=0
                )).content),
                "content_present": bool(answer.content),
                "actual_model": answer.model,
            },
        ),
        (
            "multi_turn",
            lambda: {
                "passed": bool((answer := provider.complete([
                    {"role": "user", "content": "记住业务代号蓝鲸。"},
                    {"role": "assistant", "content": "已记住。"},
                    {"role": "user", "content": "业务代号是什么？只回答代号。"},
                ], max_tokens=160, temperature=0)).content) and "蓝鲸" in answer.content,
                "content_present": bool(answer.content),
                "context_retained": "蓝鲸" in answer.content,
                "actual_model": answer.model,
            },
        ),
        (
            "structured_plan",
            lambda: {
                "passed": (payload := provider.structured_completion(
                    [{"role": "user", "content": "返回 JSON：status 固定为 ok，steps 为包含 prepare 和 execute 的数组。"}],
                    {
                        "type": "object",
                        "required": ["status", "steps"],
                        "properties": {"status": {"type": "string"}, "steps": {"type": "array"}},
                    },
                    max_tokens=320,
                    temperature=0,
                )).get("status") == "ok" and isinstance(payload.get("steps"), list),
                "schema_valid": payload.get("status") == "ok" and isinstance(payload.get("steps"), list),
            },
        ),
        (
            "chatbi_analysis_plan",
            lambda: {
                "passed": bool(AnalysisPlan.model_validate(provider.structured_completion(
                    [{"role": "user", "content": (
                        "为查询每日平均电价生成 AnalysisPlan JSON。仅使用 dataset price_daily、metric avg_price、"
                        "dimension trade_date；filters/group_by/order_by/joins 为空数组；limit=30；"
                        "chart_intent=line；analysis_mode=aggregate；clarification_required=false；"
                        "必须输出 datasets、metrics、dimensions、filters、group_by、order_by、limit、joins、"
                        "chart_intent、analysis_mode、clarification_required 全部字段。"
                    )}],
                    PLAN_SCHEMA,
                    max_tokens=700,
                    temperature=0,
                ))),
                "schema_valid": True,
            },
        ),
        (
            "tool_calling",
            lambda: {
                "passed": bool(calls := provider.tool_calls(
                    [{"role": "user", "content": "不要直接回答。必须调用 forecast_price_curve 工具查询 2026-08-14 的分时电价预测。"}],
                    [{"type": "function", "function": {
                        "name": "forecast_price_curve",
                        "description": "读取明日分时电价预测",
                        "parameters": {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]},
                    }}],
                    max_tokens=1000,
                    temperature=0,
                )),
                "call_present": bool(calls),
                "call_count": len(calls),
            },
        ),
        (
            "rag_business_analysis",
            lambda: {
                "passed": bool((answer := provider.complete([
                    {"role": "system", "content": "只可依据给定证据回答；结论必须带证据编号 [E1]。"},
                    {"role": "user", "content": "证据 E1：高峰时段需求上升且可用供给收紧。请解释高价风险原因。"},
                ], max_tokens=320, temperature=0)).content) and "[E1]" in answer.content,
                "content_present": bool(answer.content),
                "evidence_bound": "[E1]" in answer.content,
                "actual_model": answer.model,
            },
        ),
        (
            "live_error_mapping",
            lambda: _expect_invalid_model(provider),
        ),
    ]

    for check_name, operation in operations:
        if selected_check != "all" and check_name != selected_check:
            continue
        time.sleep(delay)
        result["checks"][check_name] = _run_check(provider, check_name, operation)

    if selected_check in {"all", "timeout_mapping"}:
        result["checks"]["timeout_mapping"] = {
            "passed": provider.timeout_seconds > 0,
            "configured_seconds": provider.timeout_seconds,
            "mapping_contract_test": "tests/test_ai_multi_provider_contract.py::test_timeout_is_retryable",
        }
    result["status"] = "PASS" if all(item.get("passed") for item in result["checks"].values()) else "NOT_PASS"
    return result


def _expect_invalid_model(provider: Any) -> dict[str, Any]:
    try:
        provider.complete(
            [{"role": "user", "content": "error mapping probe"}],
            model="codex-invalid-model-for-error-mapping",
            max_tokens=16,
            temperature=0,
        )
    except ProviderRequestError as exc:
        if exc.status_code not in {400, 403, 404} or exc.retryable:
            raise
        return {"mapped_status_code": exc.status_code, "mapped_reason": exc.reason, "retryable": exc.retryable}
    raise RuntimeError("invalid_model_was_not_rejected")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", type=Path, action="append", default=[])
    parser.add_argument("--provider", choices=["all", *PROVIDERS], default="all")
    parser.add_argument("--check", default="all")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for runtime_config in args.runtime_config:
        load_runtime_config(runtime_config.resolve())
    names = list(PROVIDERS) if args.provider == "all" else [args.provider]
    report = {
        "schema_version": "provider-final-matrix/v1",
        "selected_check": args.check,
        "providers": [_provider_matrix(name, args.check) for name in names],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    statuses = {item["provider"]: item["status"] for item in report["providers"]}
    print(json.dumps({"output": str(args.output), "statuses": statuses}, ensure_ascii=False))
    return 0 if all(value == "PASS" for value in statuses.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

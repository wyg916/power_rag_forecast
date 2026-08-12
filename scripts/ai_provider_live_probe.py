from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.app.ai_assistant.llm_providers import DeepSeekProvider, KimiProvider, MiMoProvider
from backend.app.ai_assistant.llm_providers.openai_compatible import ProviderRequestError


PROVIDERS = {"kimi": KimiProvider, "mimo": MiMoProvider, "deepseek": DeepSeekProvider}


def load_runtime_config(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"runtime_config_missing:{path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and not os.environ.get(key.strip()):
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _run(name: str) -> dict[str, Any]:
    provider = PROVIDERS[name]()
    result: dict[str, Any] = {
        "provider": name,
        "display_name": provider.display_name,
        "configured": provider.available,
        "key_fingerprint": (
            "sha256:" + hashlib.sha256(provider.api_key.encode("utf-8")).hexdigest()[:12]
            if provider.api_key else ""
        ),
        "model": provider.default_model,
        "base_url": provider.base_url,
        "capabilities": provider.capabilities(),
        "timeout_seconds": provider.timeout_seconds,
        "checks": {},
    }
    if not provider.available:
        result["status"] = "BLOCKED_MISSING_KEY"
        return result
    started = time.perf_counter()
    health = provider.health()
    result["checks"]["auth_models"] = {
        "passed": bool(health.get("available")),
        "reason": health.get("reason", ""),
        "model_visible": provider.default_model in (health.get("models") or []),
    }
    probes = [
        ("chinese_chat", [{"role": "user", "content": "只回答：连接成功"}], {"max_tokens": 160}),
        ("multi_turn", [
            {"role": "user", "content": "记住代号蓝鲸。"},
            {"role": "assistant", "content": "好的。"},
            {"role": "user", "content": "代号是什么？只回答代号。"},
        ], {"max_tokens": 320}),
    ]
    for check, messages, options in probes:
        try:
            completion = provider.complete(messages, temperature=0, **options)
            result["checks"][check] = {
                "passed": bool(completion.content),
                "finish_reason": completion.finish_reason,
                "content_length": len(completion.content),
            }
        except ProviderRequestError as exc:
            result["checks"][check] = {
                "passed": False,
                "reason": exc.reason,
                "status_code": exc.status_code,
            }
    try:
        chunks = list(provider.chat_stream(
            [{"role": "user", "content": "依次输出中文字符：甲乙丙"}],
            max_tokens=320,
            temperature=0,
        ))
        result["checks"]["stream"] = {"passed": bool(chunks), "chunk_count": len(chunks)}
    except ProviderRequestError as exc:
        result["checks"]["stream"] = {"passed": False, "reason": exc.reason, "status_code": exc.status_code}
    try:
        structured = provider.structured_completion(
            [{"role": "user", "content": "返回 JSON，字段 status 固定为 ok。"}],
            {"type": "object", "required": ["status"], "properties": {"status": {"type": "string"}}},
            max_tokens=320,
            temperature=0,
        )
        result["checks"]["structured"] = {"passed": structured.get("status") == "ok"}
    except (ProviderRequestError, ValueError, json.JSONDecodeError) as exc:
        result["checks"]["structured"] = {"passed": False, "reason": getattr(exc, "reason", "invalid_json")}
    try:
        calls = provider.tool_calls(
            [{"role": "user", "content": "查询北京天气，必须调用工具。"}],
            [{"type": "function", "function": {
                "name": "get_weather", "description": "查询天气",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            }}],
            max_tokens=100,
            temperature=0,
        )
        result["checks"]["tool_calls"] = {"passed": bool(calls), "call_count": len(calls)}
    except ProviderRequestError as exc:
        result["checks"]["tool_calls"] = {"passed": False, "reason": exc.reason, "status_code": exc.status_code}
    try:
        def concurrent_chat(index: int) -> bool:
            completion = provider.complete(
                [{"role": "user", "content": f"只回答数字：{index}"}],
                max_tokens=160,
                temperature=0,
            )
            return bool(completion.content)

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"{name}-probe") as executor:
            concurrent_results = list(executor.map(concurrent_chat, (1, 2)))
        result["checks"]["concurrency"] = {
            "passed": all(concurrent_results),
            "request_count": len(concurrent_results),
        }
    except ProviderRequestError as exc:
        result["checks"]["concurrency"] = {"passed": False, "reason": exc.reason, "status_code": exc.status_code}
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
    result["checks"]["timeout_policy"] = {
        "passed": result["latency_ms"] < provider.timeout_seconds * 1000,
        "configured_seconds": provider.timeout_seconds,
    }
    result["status"] = "PASS" if all(item.get("passed") for item in result["checks"].values()) else "NOT_PASS"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", type=Path, action="append", default=[])
    parser.add_argument("--provider", choices=["all", *PROVIDERS], default="all")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in args.runtime_config:
        load_runtime_config(path.resolve())
    names = list(PROVIDERS) if args.provider == "all" else [args.provider]
    report = {"schema_version": "ai-provider-live-probe/v1", "providers": [_run(name) for name in names]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "statuses": {item["provider"]: item["status"] for item in report["providers"]},
    }, ensure_ascii=False))
    return 0 if all(item["status"] in {"PASS", "BLOCKED_MISSING_KEY"} for item in report["providers"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

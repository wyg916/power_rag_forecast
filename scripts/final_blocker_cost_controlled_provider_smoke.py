from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import requests
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ai_assistant.capability_registry import (  # noqa: E402
    LogicalModelAlias,
    PremiumConsentRequired,
    resolve_capability,
)
from backend.app.ai_assistant.llm_providers import (  # noqa: E402
    DeepSeekProvider,
    KimiProvider,
    MiMoProvider,
)
from backend.app.ai_assistant.llm_providers.openai_compatible import (  # noqa: E402
    CompletionResult,
    ProviderRequestError,
)
from backend.app.chatbi.planner import build_plan_messages, parse_analysis_plan  # noqa: E402
from backend.app.chatbi.validator import validate_analysis_plan  # noqa: E402


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


def _fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else ""


def _safe_diagnostics(result: CompletionResult) -> dict[str, Any]:
    request = dict((result.diagnostics or {}).get("request") or {})
    response = dict((result.diagnostics or {}).get("response") or {})
    usage = dict(response.get("usage") or {})
    return {
        "http_status": response.get("http_status"),
        "request_id": str(response.get("request_id") or ""),
        "endpoint": request.get("endpoint"),
        "request_mode": request.get("request_mode"),
        "stream": request.get("stream"),
        "requested_model": request.get("model"),
        "request_max_tokens": request.get("max_tokens"),
        "response_format": request.get("response_format"),
        "response_header_names": list(response.get("response_header_names") or []),
        "response_content_type": response.get("content_type_header"),
        "response_body_present": response.get("body_present"),
        "response_body_type": response.get("body_type"),
        "response_field_names": list(response.get("body_keys") or []),
        "choices_count": response.get("choice_count"),
        "message_present": response.get("message_present"),
        "message_field_names": list(response.get("message_keys") or []),
        "content_present": response.get("content_present"),
        "content_chars": response.get("content_chars"),
        "reasoning_content_present": response.get("reasoning_content_present"),
        "reasoning_chars": response.get("reasoning_chars"),
        "tool_calls_count": response.get("tool_calls_count"),
        "finish_reason": response.get("finish_reason") or result.finish_reason,
        "provider_error": response.get("provider_error"),
        "response_model": response.get("response_model") or result.model,
        "usage_capture": usage.get("capture_status") or "USAGE_NOT_RETURNED_BY_PROVIDER",
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "latency_ms": response.get("latency_ms") or result.latency_ms,
        "adapter_parse_result": response.get("adapter_parse_result"),
    }


def _safe_error_diagnostics(error: ProviderRequestError) -> dict[str, Any]:
    request = dict(error.diagnostics.get("request") or {})
    response = dict(error.diagnostics.get("response") or {})
    if not response:
        response = dict(error.diagnostics)
    usage = dict(response.get("usage") or {})
    return {
        "http_status": error.status_code or response.get("http_status"),
        "request_id": str(response.get("request_id") or error.diagnostics.get("request_id") or ""),
        "endpoint": request.get("endpoint"),
        "request_mode": request.get("request_mode"),
        "stream": request.get("stream"),
        "requested_model": request.get("model"),
        "request_max_tokens": request.get("max_tokens"),
        "response_format": request.get("response_format"),
        "response_header_names": list(response.get("response_header_names") or []),
        "response_content_type": response.get("content_type_header"),
        "response_body_present": response.get("body_present"),
        "response_body_type": response.get("body_type"),
        "response_field_names": list(response.get("body_keys") or []),
        "choices_count": response.get("choice_count"),
        "message_present": response.get("message_present"),
        "message_field_names": list(response.get("message_keys") or []),
        "content_present": response.get("content_present"),
        "content_chars": response.get("content_chars"),
        "reasoning_content_present": response.get("reasoning_content_present"),
        "reasoning_chars": response.get("reasoning_chars"),
        "tool_calls_count": response.get("tool_calls_count"),
        "finish_reason": response.get("finish_reason"),
        "provider_error": response.get("provider_error"),
        "response_model": response.get("response_model"),
        "usage_capture": usage.get("capture_status") or "USAGE_NOT_RETURNED_BY_PROVIDER",
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "latency_ms": response.get("latency_ms"),
        "adapter_parse_result": response.get("adapter_parse_result"),
    }


def _cost(provider: str, input_tokens: int, output_tokens: int) -> dict[str, Any]:
    prefix = f"AI_COST_{provider.upper()}"
    raw_input = os.environ.get(f"{prefix}_INPUT_PER_MILLION")
    raw_output = os.environ.get(f"{prefix}_OUTPUT_PER_MILLION")
    if raw_input is None or raw_output is None:
        return {"estimated_cost_cny": None, "cost_estimate_available": False}
    value = (input_tokens * float(raw_input) + output_tokens * float(raw_output)) / 1_000_000
    return {"estimated_cost_cny": round(value, 8), "cost_estimate_available": True}


def _completion_record(provider: str, purpose: str, result: CompletionResult) -> dict[str, Any]:
    return {
        "status": "PASS",
        "provider": provider,
        "model": result.model,
        "purpose": purpose,
        "call_count": 1,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_ms": result.latency_ms,
        **_cost(provider, result.input_tokens, result.output_tokens),
        "diagnostics": _safe_diagnostics(result),
    }


def _deepseek_analysis_plan(config_sources: list[str]) -> dict[str, Any]:
    provider = DeepSeekProvider()
    if not provider.available:
        raise ProviderRequestError("deepseek", "missing_api_key")
    capability = resolve_capability(LogicalModelAlias.DATA_PLANNER)
    if capability.provider != "deepseek" or not capability.supports_structured:
        raise RuntimeError("data_planner_capability_mismatch")
    result = provider.complete(
        build_plan_messages("查询最近一天的平均日前价格。", None),
        model=capability.model,
        temperature=0,
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    plan = parse_analysis_plan(result.content)
    validation = validate_analysis_plan(
        plan, permissions=("assistant:use", "data:read", "model:read")
    )
    plan_payload = plan.model_dump(mode="json")
    forbidden_sql = sorted(set(plan_payload).intersection({"sql", "query", "raw_sql", "statement"}))
    record = _completion_record("deepseek", "AnalysisPlan", result)
    record.update(
        status="PASS" if validation.valid and not forbidden_sql else "FAIL",
        schema_validation="PASS",
        semantic_validation="PASS" if validation.valid else "FAIL",
        validation_issues=[item.code for item in validation.issues],
        raw_sql_execution_by_llm=0,
        forbidden_sql_keys=forbidden_sql,
        selected_provider="deepseek",
        selected_model=capability.model,
        logical_alias=LogicalModelAlias.DATA_PLANNER.value,
        route_reason=capability.route_reason,
        key_source_files=config_sources,
    )
    return record


def _vision_data_url() -> str:
    stream = io.BytesIO()
    image = Image.new("RGB", (96, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 12, 42, 54), fill="red")
    draw.ellipse((54, 12, 88, 46), fill="blue")
    image.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _mimo_general() -> dict[str, Any]:
    result = MiMoProvider().complete(
        [{"role": "user", "content": "只回答：连接正常"}], temperature=0, max_tokens=500
    )
    record = _completion_record("mimo", "general", result)
    record["content_present"] = bool(result.content)
    record["status"] = "PASS" if result.content else "FAIL"
    return record


def _mimo_vision() -> dict[str, Any]:
    result = MiMoProvider().complete(
        [{"role": "user", "content": [
            {"type": "text", "text": "图中两种主要颜色是什么？只回答颜色。"},
            {"type": "image_url", "image_url": {"url": _vision_data_url()}},
        ]}],
        temperature=0,
        max_tokens=700,
    )
    normalized = result.content.lower()
    visible = ("红" in normalized or "red" in normalized) and ("蓝" in normalized or "blue" in normalized)
    record = _completion_record("mimo", "vision", result)
    record.update(status="PASS" if visible else "FAIL", visible_evidence_terms_present=visible)
    return record


def _kimi_premium() -> dict[str, Any]:
    denied = False
    try:
        resolve_capability(
            LogicalModelAlias.PREMIUM,
            requested_tier="premium",
            premium_confirmed=False,
        )
    except PremiumConsentRequired:
        denied = True
    result = KimiProvider().complete(
        [{"role": "user", "content": "只回答：Premium 已明确连接"}],
        temperature=0,
        max_tokens=700,
    )
    record = _completion_record("kimi", "explicit_premium", result)
    record.update(
        status="PASS" if denied and bool(result.content) else "FAIL",
        denied_without_confirmation=denied,
        explicit_confirmation=True,
    )
    return record


ATTACHMENT_FILE_NAME = "alpha-7281.txt"
ATTACHMENT_QUESTION = "这个文件中的 PROJECT_CODE 是什么？"
ATTACHMENT_EXPECTED_FACT = "ALPHA-7281"


def _redacted_answer_text(answer: str) -> str:
    normalized = " ".join(str(answer or "").split())
    normalized = re.sub(
        r"(?i)(bearer\s+|api[_-]?key\s*[:=]\s*|token\s*[:=]\s*)[^\s,;]+",
        r"\1<REDACTED>",
        normalized,
    )
    return normalized[:300]


def _evaluate_attachment_evidence(
    payload: dict[str, Any],
    uploaded_id: str,
    *,
    file_name: str = ATTACHMENT_FILE_NAME,
    question: str = ATTACHMENT_QUESTION,
    expected_fact: str = ATTACHMENT_EXPECTED_FACT,
) -> dict[str, Any]:
    """Evaluate grounding and citation independently and retain auditable fields."""
    answer = str(payload.get("answer") or "")
    grounding = dict(payload.get("attachment_grounding") or {})
    citations = [
        dict(item) for item in (payload.get("attachment_citations") or [])
        if isinstance(item, dict)
    ]
    retrieved_source_ids = [
        str(item) for item in (grounding.get("source_ids") or []) if str(item)
    ]
    retrieved_chunk_count = int(grounding.get("chunk_count") or 0)
    enterprise_kb_chunk_count = int(grounding.get("enterprise_kb_chunk_count") or 0)
    only_selected_mode = bool(grounding.get("only_selected_attachments_mode"))
    answer_contains_expected_fact = expected_fact in answer
    expected_source_prefix = f"attachment:{uploaded_id}:"
    retrieved_selected_attachment = bool(uploaded_id) and any(
        source_id.startswith(expected_source_prefix) for source_id in retrieved_source_ids
    )
    grounding_pass = bool(
        answer_contains_expected_fact
        and retrieved_chunk_count >= 1
        and retrieved_selected_attachment
        and enterprise_kb_chunk_count == 0
        and only_selected_mode
    )

    citation_attachment_ids = [str(item.get("attachment_id") or "") for item in citations]
    citation_file_names = [str(item.get("file_name") or "") for item in citations]
    citation_source_ids = [str(item.get("source_id") or "") for item in citations]

    def points_to_selected_attachment(item: dict[str, Any]) -> bool:
        citation_attachment_id = str(item.get("attachment_id") or "")
        citation_file_name = str(item.get("file_name") or "")
        citation_source_id = str(item.get("source_id") or "")
        if citation_attachment_id and citation_attachment_id != uploaded_id:
            return False
        if citation_source_id and not citation_source_id.startswith(expected_source_prefix):
            return False
        return bool(
            citation_attachment_id == uploaded_id
            or citation_file_name == file_name
            or citation_source_id in retrieved_source_ids
        )

    citation_pass = bool(citations) and any(points_to_selected_attachment(item) for item in citations)
    return {
        "ATTACHMENT_ID": uploaded_id,
        "FILE_NAME": file_name,
        "QUESTION": question,
        "EXPECTED_FACT": expected_fact,
        "ANSWER_TEXT_REDACTED": _redacted_answer_text(answer),
        "ANSWER_CONTAINS_EXPECTED_FACT": answer_contains_expected_fact,
        "RETRIEVED_ATTACHMENT_CHUNK_COUNT": retrieved_chunk_count,
        "RETRIEVED_ATTACHMENT_SOURCE_IDS": retrieved_source_ids,
        "ENTERPRISE_KB_CHUNK_COUNT": enterprise_kb_chunk_count,
        "ONLY_SELECTED_ATTACHMENTS_MODE": only_selected_mode,
        "GROUNDING_PASS": grounding_pass,
        "CITATION_COUNT": len(citations),
        "CITATION_ATTACHMENT_IDS": citation_attachment_ids,
        "CITATION_FILE_NAMES": citation_file_names,
        "CITATION_SOURCE_IDS": citation_source_ids,
        "CITATION_PASS": citation_pass,
    }


def _attachment_failure_layer(evidence: dict[str, Any]) -> str:
    if int(evidence["RETRIEVED_ATTACHMENT_CHUNK_COUNT"]) < 1:
        return "RETRIEVAL"
    if (
        int(evidence["ENTERPRISE_KB_CHUNK_COUNT"]) != 0
        or not evidence["ONLY_SELECTED_ATTACHMENTS_MODE"]
    ):
        return "GROUNDING"
    if not evidence["ANSWER_CONTAINS_EXPECTED_FACT"]:
        return "MODEL"
    if not evidence["CITATION_PASS"]:
        return "CITATION_MAPPING"
    return "EVALUATOR"


def _failed_attachment_record(
    failure_layer: str,
    *,
    uploaded_id: str = "",
    call_count: int = 0,
    http_status: int | None = None,
    reason: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = _evaluate_attachment_evidence(payload or {}, uploaded_id)
    return {
        "status": "FAIL",
        "provider": "mimo",
        "purpose": "attachment_grounded_qa",
        "call_count": call_count,
        "input_tokens": 0,
        "output_tokens": 0,
        **_cost("mimo", 0, 0),
        "http_status": http_status,
        "failure_layer": failure_layer,
        "reason": reason,
        **evidence,
    }


def _attachment_qa(base_url: str) -> dict[str, Any]:
    session_id = "sess_cost_" + uuid4().hex
    request_id = "req_cost_" + uuid4().hex
    headers = {"X-User": "cost-controlled-analyst", "X-Role": "analyst"}
    body = (
        "受控发布核验附件。\nPROJECT_CODE=ALPHA-7281\n"
        "该代码仅用于验证所选附件 grounding 与 citation。\n" + ("evidence-line\n" * 70)
    ).encode("utf-8")
    uploaded_id = ""
    result: dict[str, Any]
    cleanup_pass = True
    try:
        try:
            upload = requests.post(
                f"{base_url}/api/ai/attachments",
                headers=headers,
                files={"file": (ATTACHMENT_FILE_NAME, body, "text/plain")},
                data={"session_id": session_id},
                timeout=30,
            )
            upload.raise_for_status()
            upload_payload = upload.json()
            uploaded_id = str(upload_payload["attachment_id"])
        except (requests.RequestException, KeyError, TypeError, ValueError):
            result = _failed_attachment_record(
                "UPLOAD",
                http_status=locals().get("upload").status_code if "upload" in locals() else None,
                reason="attachment_upload_failed",
            )
            return result

        try:
            parsed = requests.get(
                f"{base_url}/api/ai/attachments/{uploaded_id}",
                headers=headers,
                params={"session_id": session_id},
                timeout=30,
            )
            parsed.raise_for_status()
            parsed_payload = parsed.json()
        except (requests.RequestException, TypeError, ValueError):
            result = _failed_attachment_record(
                "PARSE", uploaded_id=uploaded_id, reason="attachment_parse_status_unavailable"
            )
            return result
        if parsed_payload.get("status") != "ready":
            result = _failed_attachment_record(
                "PARSE", uploaded_id=uploaded_id, reason="attachment_not_ready"
            )
            return result

        started = time.perf_counter()
        try:
            response = requests.post(
                f"{base_url}/api/ai/chat",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "request_id": request_id,
                    "session_id": session_id,
                    "question": ATTACHMENT_QUESTION,
                    "mode": "file",
                    "stream": False,
                    "model_provider": "mimo",
                    "attachment_ids": [uploaded_id],
                    "knowledge_scope": "attachments",
                },
                timeout=180,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, TypeError, ValueError):
            result = _failed_attachment_record(
                "MODEL",
                uploaded_id=uploaded_id,
                call_count=1,
                http_status=locals().get("response").status_code if "response" in locals() else None,
                reason="attachment_model_request_failed",
            )
            return result

        usage = dict(payload.get("usage") or {})
        try:
            evidence = _evaluate_attachment_evidence(payload, uploaded_id)
        except (KeyError, TypeError, ValueError):
            result = _failed_attachment_record(
                "EVALUATOR", uploaded_id=uploaded_id, call_count=1,
                http_status=response.status_code, reason="attachment_evaluator_failed", payload=payload,
            )
            return result
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        passed = bool(evidence["GROUNDING_PASS"] and evidence["CITATION_PASS"])
        result = {
            "status": "PASS" if passed else "FAIL",
            "provider": "mimo",
            "model": (payload.get("route") or {}).get("selected_model"),
            "purpose": "attachment_grounded_qa",
            "call_count": 1,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": float(usage.get("latency_ms") or round((time.perf_counter() - started) * 1000, 3)),
            **_cost("mimo", input_tokens, output_tokens),
            "http_status": response.status_code,
            "request_id": payload.get("request_id"),
            "trace_id_present": bool(payload.get("trace_id")),
            "failure_layer": "" if passed else _attachment_failure_layer(evidence),
            "attachment_lifecycle": "PASS",
            "knowledge_scope": "attachments",
            "max_output_tokens": int(
                (payload.get("attachment_grounding") or {}).get("max_output_tokens") or 0
            ),
            **evidence,
        }
        return result
    finally:
        if uploaded_id:
            try:
                deleted = requests.delete(
                    f"{base_url}/api/ai/attachments/{uploaded_id}", headers=headers, timeout=30
                )
                deleted.raise_for_status()
            except requests.RequestException:
                cleanup_pass = False
        if "result" in locals() and not cleanup_pass:
            result.update(status="FAIL", failure_layer="EVALUATOR", attachment_lifecycle="FAIL")


def _run(name: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return operation()
    except ProviderRequestError as exc:
        diagnostics = _safe_error_diagnostics(exc)
        input_tokens = int(diagnostics.get("input_tokens") or 0)
        output_tokens = int(diagnostics.get("output_tokens") or 0)
        return {
            "status": "FAIL",
            "provider": exc.provider,
            "purpose": name,
            "call_count": 1,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            **_cost(exc.provider, input_tokens, output_tokens),
            "http_status": diagnostics.get("http_status"),
            "retryable": exc.retryable,
            "reason": exc.reason,
            "request_id": diagnostics.get("request_id"),
            "diagnostics": diagnostics,
            "non_empty_provider_response": bool(diagnostics.get("content_present")),
            "adapter_parse": diagnostics.get("adapter_parse_result") or "FAIL_BEFORE_PARSE",
            "schema_validation": "NOT_REACHED",
            "semantic_validation": "NOT_REACHED",
        }
    except Exception as exc:
        return {
            "status": "FAIL",
            "purpose": name,
            "call_count": 1,
            "reason": type(exc).__name__,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", action="append", type=Path, default=[])
    parser.add_argument("--base-url", default="http://127.0.0.1:18085")
    parser.add_argument("--check", choices=("targeted_deepseek", "targeted_attachment", "final"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in args.runtime_config:
        load_runtime_config(path.resolve())
    config_sources = [str(path.resolve()) for path in args.runtime_config]
    if args.check == "targeted_deepseek":
        checks = {"deepseek_analysis_plan": _run(
            "deepseek_analysis_plan", lambda: _deepseek_analysis_plan(config_sources)
        )}
    elif args.check == "targeted_attachment":
        checks = {"attachment_qa": _run("attachment_qa", lambda: _attachment_qa(args.base_url))}
    else:
        checks = {
            "mimo_general": _run("mimo_general", _mimo_general),
            "mimo_vision": _run("mimo_vision", _mimo_vision),
            "deepseek_analysis_plan": _run(
                "deepseek_analysis_plan", lambda: _deepseek_analysis_plan(config_sources)
            ),
            "kimi_premium": _run("kimi_premium", _kimi_premium),
            "attachment_qa": _run("attachment_qa", lambda: _attachment_qa(args.base_url)),
        }
    call_count = sum(int(item.get("call_count") or 0) for item in checks.values())
    cost_estimate_available = all(
        item.get("cost_estimate_available") is True
        for item in checks.values()
        if int(item.get("call_count") or 0) > 0
    )
    payload = {
        "schema_version": "project1-cost-controlled-provider-smoke/v1",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "check": args.check,
        "status": "PASS" if all(item["status"] == "PASS" for item in checks.values()) else "FAIL",
        "call_count": call_count,
        "input_tokens": sum(int(item.get("input_tokens") or 0) for item in checks.values()),
        "output_tokens": sum(int(item.get("output_tokens") or 0) for item in checks.values()),
        "estimated_cost_cny": (
            round(sum(float(item.get("estimated_cost_cny") or 0) for item in checks.values()), 8)
            if cost_estimate_available
            else None
        ),
        "cost_estimate_available": cost_estimate_available,
        "cost_capture": "CAPTURED" if cost_estimate_available else "PRICING_NOT_CONFIGURED",
        "redaction": "No API key, prompt body, response body, attachment body, or DSN is persisted.",
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("status", "check", "call_count", "input_tokens", "output_tokens", "estimated_cost_cny")}, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

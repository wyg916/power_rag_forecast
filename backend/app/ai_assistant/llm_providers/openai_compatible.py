from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Protocol

import requests


@dataclass(frozen=True)
class CompletionResult:
    content: str
    model: str
    finish_reason: str = ""
    reasoning_content: str = ""
    tool_calls: tuple[dict[str, Any], ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    default_model: str
    available: bool

    def chat(self, messages: list[dict[str, str]], **options: Any) -> str: ...
    def chat_stream(self, messages: list[dict[str, str]], **options: Any) -> Iterator[str]: ...
    def structured_completion(self, messages: list[dict[str, str]], schema: Mapping[str, Any], **options: Any) -> dict[str, Any]: ...
    def tool_calls(self, messages: list[dict[str, str]], tools: list[dict[str, Any]], **options: Any) -> list[dict[str, Any]]: ...
    def health(self) -> dict[str, Any]: ...
    def capabilities(self) -> dict[str, Any]: ...


class ProviderRequestError(RuntimeError):
    def __init__(
        self,
        provider: str,
        reason: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        self.reason = reason
        self.status_code = status_code
        self.retryable = retryable
        self.diagnostics = dict(diagnostics or {})
        super().__init__(f"{provider}:{reason}")


def _json_object(content: str) -> dict[str, Any]:
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("structured_response_missing_json")
    payload = json.loads(value[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("structured_response_not_object")
    return payload


def _content_text(value: Any) -> tuple[str, list[str]]:
    """Normalize OpenAI-compatible string or multipart response content."""
    if isinstance(value, str):
        return value.strip(), ["text"]
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return "", [type(value).__name__]
    texts: list[str] = []
    part_types: list[str] = []
    for part in value:
        if isinstance(part, str):
            part_types.append("text")
            texts.append(part)
            continue
        if not isinstance(part, dict):
            part_types.append(type(part).__name__)
            continue
        part_types.append(str(part.get("type") or "object"))
        text_value = part.get("text")
        if isinstance(text_value, dict):
            text_value = text_value.get("value") or text_value.get("content")
        if text_value is None:
            text_value = part.get("content") or part.get("value")
        if isinstance(text_value, str):
            texts.append(text_value)
    return "\n".join(item for item in texts if item).strip(), part_types


def _request_shape(payload: Mapping[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    content_types: list[str] = []
    image_mimes: list[str] = []
    image_url_kinds: list[str] = []
    image_count = 0
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        parts = content if isinstance(content, list) else [content]
        for part in parts:
            if isinstance(part, str):
                content_types.append("text")
                continue
            if not isinstance(part, dict):
                content_types.append(type(part).__name__)
                continue
            part_type = str(part.get("type") or "object")
            content_types.append(part_type)
            if part_type == "image_url":
                image_count += 1
                image_value = part.get("image_url") or {}
                url = image_value.get("url") if isinstance(image_value, dict) else image_value
                url = str(url or "")
                image_url_kinds.append("data" if url.startswith("data:") else "remote")
                match = re.match(r"^data:([^;,]+)", url)
                image_mimes.append(match.group(1).lower() if match else "")
    response_format = payload.get("response_format")
    return {
        "endpoint": "chat/completions",
        "request_mode": "stream" if bool(payload.get("stream")) else "non_stream",
        "stream": bool(payload.get("stream")),
        "model": str(payload.get("model") or ""),
        "message_count": len(messages),
        "content_types": content_types,
        "image_count": image_count,
        "image_mimes": image_mimes,
        "image_url_kinds": image_url_kinds,
        "max_tokens": int(payload.get("max_tokens") or 0),
        "response_format": response_format.get("type") if isinstance(response_format, dict) else None,
    }


def _provider_error_shape(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {"body_type": "non_json", "body_chars": len(getattr(response, "text", "") or "")}
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return {"body_type": type(body).__name__, "body_keys": sorted(body) if isinstance(body, dict) else []}
    message = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", str(error.get("message") or ""))
    return {
        "body_type": "object",
        "provider_error": {
            "type": str(error.get("type") or "")[:80],
            "code": str(error.get("code") or "")[:80],
            "message": message[:300],
        },
    }


def _request_id(response: requests.Response, fallback: str = "") -> str:
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get("x-request-id") or headers.get("request-id") or fallback)


def _schema_issues(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    issues: list[str] = []
    expected = schema.get("type")
    type_checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    expected_types = expected if isinstance(expected, list) else [expected]
    expected_types = [item for item in expected_types if item]
    if expected_types and not any(type_checks.get(item, lambda _value: True)(value) for item in expected_types):
        return [f"{path}:type"]
    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        issues.append(f"{path}:enum")
    if isinstance(value, dict):
        required = [str(item) for item in schema.get("required", [])]
        issues.extend(f"{path}.{key}:required" for key in required if key not in value)
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        if schema.get("additionalProperties") is False:
            issues.extend(f"{path}.{key}:extra" for key in value if key not in properties)
        for key, item in value.items():
            if key in properties:
                issues.extend(_schema_issues(item, properties[key], f"{path}.{key}"))
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            issues.extend(_schema_issues(item, schema["items"], f"{path}[{index}]"))
    return issues


class OpenAICompatibleProvider:
    name = "openai_compatible"
    display_name = "OpenAI Compatible"

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout_seconds: int = 120) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.default_model = model.strip()
        self.timeout_seconds = max(1, min(int(timeout_seconds), 300))

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.base_url and self.default_model)

    def capabilities(self) -> dict[str, Any]:
        return {
            "chat": True,
            "chat_stream": True,
            "structured_completion": True,
            "tool_calls": True,
            "openai_compatible": True,
        }

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderRequestError(self.name, "missing_api_key")
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def _url(self, resource: str) -> str:
        return f"{self.base_url}/{resource.lstrip('/')}"

    def _request(self, method: str, resource: str, **kwargs: Any) -> requests.Response:
        try:
            response = requests.request(
                method,
                self._url(resource),
                headers=self._headers(),
                timeout=kwargs.pop("timeout", self.timeout_seconds),
                **kwargs,
            )
        except requests.Timeout as exc:
            raise ProviderRequestError(self.name, "timeout", retryable=True) from exc
        except requests.RequestException as exc:
            raise ProviderRequestError(self.name, "network_unavailable") from exc
        if response.status_code >= 400:
            retryable = response.status_code == 429 or response.status_code >= 500
            raise ProviderRequestError(
                self.name,
                f"http_{response.status_code}",
                status_code=response.status_code,
                retryable=retryable,
                diagnostics={
                    "http_status": response.status_code,
                    "request_id": _request_id(response),
                    **_provider_error_shape(response),
                },
            )
        return response

    def complete(self, messages: list[dict[str, Any]], **options: Any) -> CompletionResult:
        started = time.perf_counter()
        model = str(options.pop("model", "") or self.default_model)
        max_tokens = options.pop("max_tokens", None)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": float(options.pop("temperature", 0.35)),
            "stream": False,
            **options,
        }
        if max_tokens is not None and int(max_tokens) > 0:
            payload["max_tokens"] = int(max_tokens)
        try:
            response = self._request("POST", "chat/completions", json=payload)
            body = response.json()
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            raise ProviderRequestError(self.name, "invalid_response") from exc
        content, part_types = _content_text(message.get("content"))
        reasoning_content, reasoning_part_types = _content_text(message.get("reasoning_content"))
        tool_calls = tuple(message.get("tool_calls") or ())
        response_headers = getattr(response, "headers", {}) or {}
        usage_payload = body.get("usage") if isinstance(body.get("usage"), dict) else None
        provider_error = body.get("error") if isinstance(body.get("error"), dict) else None
        if content:
            adapter_parse_result = "PASS_CONTENT"
        elif tool_calls:
            adapter_parse_result = "PASS_TOOL_CALLS"
        elif reasoning_content:
            adapter_parse_result = "FAIL_REASONING_ONLY"
        elif not (body.get("choices") or []):
            adapter_parse_result = "FAIL_CHOICES_MISSING"
        elif not isinstance(choice.get("message"), dict):
            adapter_parse_result = "FAIL_MESSAGE_MISSING"
        else:
            adapter_parse_result = "FAIL_CONTENT_EMPTY"
        diagnostics = {
            "request": _request_shape(payload),
            "response": {
                "http_status": response.status_code,
                "request_id": _request_id(response, str(body.get("id") or "")),
                "response_header_names": sorted(str(key).lower() for key in response_headers),
                "content_type_header": str(response_headers.get("content-type") or "")[:120],
                "body_present": True,
                "body_type": type(body).__name__,
                "body_keys": sorted(body) if isinstance(body, dict) else [],
                "choice_count": len(body.get("choices") or []),
                "message_present": isinstance(choice.get("message"), dict),
                "message_keys": sorted(message) if isinstance(message, dict) else [],
                "content_type": type(message.get("content")).__name__,
                "content_part_types": part_types,
                "reasoning_part_types": reasoning_part_types,
                "content_present": bool(content),
                "reasoning_content_present": bool(reasoning_content),
                "content_chars": len(content),
                "reasoning_chars": len(reasoning_content),
                "tool_calls_count": len(tool_calls),
                "finish_reason": str(choice.get("finish_reason") or ""),
                "response_model": str(body.get("model") or ""),
                "provider_error": {
                    "type": str(provider_error.get("type") or "")[:80],
                    "code": str(provider_error.get("code") or "")[:80],
                    "message": re.sub(
                        r"sk-[A-Za-z0-9_\-]{8,}",
                        "sk-***",
                        str(provider_error.get("message") or ""),
                    )[:300],
                } if provider_error else None,
                "adapter_parse_result": adapter_parse_result,
                "usage": {
                    "capture_status": "CAPTURED" if usage_payload is not None else "USAGE_NOT_RETURNED_BY_PROVIDER",
                    "prompt_tokens": int((usage_payload or {}).get("prompt_tokens") or 0),
                    "completion_tokens": int((usage_payload or {}).get("completion_tokens") or 0),
                    "total_tokens": int((usage_payload or {}).get("total_tokens") or 0),
                },
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        }
        if not content and not tool_calls:
            raise ProviderRequestError(self.name, "empty_response", diagnostics=diagnostics)
        return CompletionResult(
            content=content,
            model=str(body.get("model") or model),
            finish_reason=str(choice.get("finish_reason") or ""),
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            input_tokens=int((body.get("usage") or {}).get("prompt_tokens") or 0),
            output_tokens=int((body.get("usage") or {}).get("completion_tokens") or 0),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            diagnostics=diagnostics,
        )

    def chat(self, messages: list[dict[str, Any]], **options: Any) -> str:
        result = self.complete(messages, **options)
        if not result.content:
            raise ProviderRequestError(self.name, "empty_content")
        return result.content

    def chat_stream(self, messages: list[dict[str, Any]], **options: Any) -> Iterator[str]:
        max_tokens = options.pop("max_tokens", None)
        payload = {
            "model": str(options.pop("model", "") or self.default_model),
            "messages": messages,
            "temperature": float(options.pop("temperature", 0.35)),
            "stream": True,
            **options,
        }
        if max_tokens is not None and int(max_tokens) > 0:
            payload["max_tokens"] = int(max_tokens)
        response = self._request("POST", "chat/completions", json=payload, stream=True)
        try:
            for raw in response.iter_lines(decode_unicode=True):
                line = str(raw or "").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = ((json.loads(data).get("choices") or [{}])[0].get("delta") or {})
                except (json.JSONDecodeError, TypeError, IndexError):
                    continue
                if content := str(delta.get("content") or ""):
                    yield content
        finally:
            response.close()

    def structured_completion(self, messages: list[dict[str, str]], schema: Mapping[str, Any], **options: Any) -> dict[str, Any]:
        result = self.complete(
            messages,
            response_format={"type": "json_object"},
            **options,
        )
        try:
            payload = _json_object(result.content)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderRequestError(
                self.name, "structured_response_invalid_json", diagnostics=result.diagnostics
            ) from exc
        issues = _schema_issues(payload, schema)
        if issues:
            diagnostics = {
                **result.diagnostics,
                "structured_output": {
                    "payload_keys": sorted(payload),
                    "value_types": {key: type(value).__name__ for key, value in payload.items()},
                    "schema_issues": issues[:30],
                },
            }
            raise ProviderRequestError(self.name, "structured_response_schema_mismatch", diagnostics=diagnostics)
        return payload

    def tool_calls(self, messages: list[dict[str, str]], tools: list[dict[str, Any]], **options: Any) -> list[dict[str, Any]]:
        result = self.complete(messages, tools=tools, tool_choice="auto", **options)
        return list(result.tool_calls)

    def health(self) -> dict[str, Any]:
        base = {
            "available": False,
            "configured": self.available,
            "provider": self.name,
            "display_name": self.display_name,
            "base_url": self.base_url,
            "model": self.default_model,
            "capabilities": self.capabilities(),
        }
        if not self.available:
            return {**base, "reason": "missing_api_key"}
        try:
            models = self._request("GET", "models", timeout=min(self.timeout_seconds, 20)).json().get("data") or []
            names = [str(item.get("id") or item.get("model") or "") for item in models if isinstance(item, dict)]
            return {**base, "available": True, "models": [name for name in names if name]}
        except ProviderRequestError as exc:
            return {**base, "reason": exc.reason, "status_code": exc.status_code}

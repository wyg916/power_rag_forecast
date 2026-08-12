from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Protocol

import requests


@dataclass(frozen=True)
class CompletionResult:
    content: str
    model: str
    finish_reason: str = ""
    reasoning_content: str = ""
    tool_calls: tuple[dict[str, Any], ...] = ()


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
    def __init__(self, provider: str, reason: str, *, status_code: int | None = None, retryable: bool = False) -> None:
        self.provider = provider
        self.reason = reason
        self.status_code = status_code
        self.retryable = retryable
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
            )
        return response

    def complete(self, messages: list[dict[str, str]], **options: Any) -> CompletionResult:
        model = str(options.pop("model", "") or self.default_model)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": float(options.pop("temperature", 0.35)),
            "max_tokens": int(options.pop("max_tokens", 1400)),
            "stream": False,
            **options,
        }
        try:
            body = self._request("POST", "chat/completions", json=payload).json()
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            raise ProviderRequestError(self.name, "invalid_response") from exc
        content = str(message.get("content") or "").strip()
        tool_calls = tuple(message.get("tool_calls") or ())
        if not content and not tool_calls:
            raise ProviderRequestError(self.name, "empty_response")
        return CompletionResult(
            content=content,
            model=str(body.get("model") or model),
            finish_reason=str(choice.get("finish_reason") or ""),
            reasoning_content=str(message.get("reasoning_content") or ""),
            tool_calls=tool_calls,
        )

    def chat(self, messages: list[dict[str, str]], **options: Any) -> str:
        result = self.complete(messages, **options)
        if not result.content:
            raise ProviderRequestError(self.name, "empty_content")
        return result.content

    def chat_stream(self, messages: list[dict[str, str]], **options: Any) -> Iterator[str]:
        payload = {
            "model": str(options.pop("model", "") or self.default_model),
            "messages": messages,
            "temperature": float(options.pop("temperature", 0.35)),
            "max_tokens": int(options.pop("max_tokens", 1400)),
            "stream": True,
            **options,
        }
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
        payload = _json_object(result.content)
        required = [str(item) for item in schema.get("required", [])]
        if any(key not in payload for key in required):
            raise ProviderRequestError(self.name, "structured_response_schema_mismatch")
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

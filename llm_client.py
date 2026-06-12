from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

import requests

from automation_common import env_or_default

try:
    from jsonschema import validate as validate_json_schema
except Exception:  # pragma: no cover - optional dependency during partial installs
    validate_json_schema = None


class LLMClient:
    def __init__(self, config: dict[str, Any]):
        llm_cfg = config["llm"]
        self.provider = llm_cfg["provider"]
        self.api_mode = llm_cfg.get("api_mode", "openai_compat")
        self.base_url = env_or_default("LLM_BASE_URL", llm_cfg["base_url"]).rstrip("/")
        self.api_key = env_or_default("LLM_API_KEY", llm_cfg["api_key"])
        self.model = env_or_default("LLM_MODEL", llm_cfg["model"])
        self.temperature = float(llm_cfg["temperature"])
        self.max_tokens = int(llm_cfg["max_tokens"])
        self.timeout_seconds = int(env_or_default("LLM_TIMEOUT", llm_cfg["timeout_seconds"]))
        self.auto_pull = str(os.environ.get("LLM_AUTO_PULL", str(llm_cfg.get("auto_pull", False)))).lower() in {"1", "true", "yes"}
        self.structured_json = bool(llm_cfg.get("structured_json", True))
        self.retry_count = int(env_or_default("LLM_RETRY_COUNT", llm_cfg.get("retry_count", 3)))
        self.last_raw_response = ""
        self.last_parse_error = ""
        self.last_schema_error = ""
        self.last_retry_count = 0

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def ensure_model(self) -> None:
        if self.provider != "ollama":
            return

        list_result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
            timeout=10,
        )
        if self.model in (list_result.stdout or ""):
            return
        if not self.auto_pull:
            raise RuntimeError(f"Ollama 未安装目标模型：{self.model}")
        subprocess.run(["ollama", "pull", self.model], check=True, timeout=int(os.environ.get("LLM_PULL_TIMEOUT", "300")))

    def healthcheck(self) -> dict[str, Any]:
        endpoint = "/api/tags" if self.provider == "ollama" and self.api_mode == "native" else "/models"
        response = requests.get(f"{self.base_url}{endpoint}", headers=self._headers(), timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_model()
        self.last_raw_response = ""
        self.last_parse_error = ""
        self.last_schema_error = ""
        self.last_retry_count = 0

        errors: list[str] = []
        attempts = max(1, self.retry_count)
        for attempt in range(1, attempts + 1):
            self.last_retry_count = attempt - 1
            try:
                if self.provider == "ollama" and self.api_mode == "native":
                    content = self._generate_content_ollama_native(system_prompt, user_prompt, schema)
                else:
                    content = self._generate_content_openai_compat(system_prompt, user_prompt)
                self.last_raw_response = content
                return self._parse_json_response(content, schema)
            except Exception as exc:
                error_text = f"第 {attempt} 次 LLM JSON 生成/解析失败：{exc}"
                errors.append(error_text)
                self.last_parse_error = str(exc)
                if attempt >= attempts:
                    raise RuntimeError("; ".join(errors)) from exc
                time.sleep(min(2 ** (attempt - 1), 8))

        raise RuntimeError("LLM JSON 生成失败。")

    @staticmethod
    def extract_json_object(text: str) -> str:
        start = (text or "").find("{")
        end = (text or "").rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM 输出中未发现 JSON 对象。")
        return text[start : end + 1]

    def _parse_json_response(self, content: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            payload = json.loads(content or "{}")
        except json.JSONDecodeError:
            payload = json.loads(self.extract_json_object(content or ""))

        if not isinstance(payload, dict):
            raise ValueError("LLM JSON 根节点不是对象。")

        if schema:
            if validate_json_schema is not None:
                try:
                    validate_json_schema(payload, schema)
                except Exception as exc:
                    self.last_schema_error = str(exc)
                    raise
            else:
                missing = set(schema.get("required", [])) - set(payload.keys())
                if missing:
                    self.last_schema_error = f"缺少必填字段：{sorted(missing)}"
                    raise ValueError(self.last_schema_error)
        return payload

    def _generate_content_openai_compat(self, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "think": False,
        }
        if self.structured_json:
            payload["response_format"] = {"type": "json_object"}

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"] or ""

    def _generate_content_ollama_native(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "format": schema or "json",
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        result = response.json()
        return result["message"]["content"] or ""

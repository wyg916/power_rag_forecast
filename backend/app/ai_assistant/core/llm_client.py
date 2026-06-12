from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from ....model_gateway.config import load_model_gateway_config


_OLLAMA_READY_UNTIL = 0.0


def _ollama_root_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/v1"):
        return value[:-3]
    return value


def _openai_base_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    return value if value.endswith("/v1") else f"{value}/v1"


def _ollama_exe() -> str | None:
    path = shutil.which("ollama")
    if path:
        return path
    fallback = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
    return str(fallback) if fallback.exists() else None


def _start_ollama_if_needed(root_url: str, timeout_seconds: int = 20) -> None:
    global _OLLAMA_READY_UNTIL
    if time.time() < _OLLAMA_READY_UNTIL:
        return
    try:
        requests.get(f"{root_url}/api/tags", timeout=2).raise_for_status()
        _OLLAMA_READY_UNTIL = time.time() + 60
        return
    except Exception:
        pass

    exe = _ollama_exe()
    if not exe:
        raise RuntimeError("未找到 Ollama 可执行文件")

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    subprocess.Popen(
        [exe, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            requests.get(f"{root_url}/api/tags", timeout=2).raise_for_status()
            _OLLAMA_READY_UNTIL = time.time() + 60
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    raise RuntimeError(f"Ollama 启动后仍不可用：{last_error}")


def get_local_llm_status() -> dict[str, Any]:
    cfg = load_model_gateway_config()
    root_url = _ollama_root_url(cfg.base_url)
    _start_ollama_if_needed(root_url)
    response = requests.get(f"{root_url}/api/tags", timeout=5)
    response.raise_for_status()
    models = response.json().get("models") or []
    names = [str(item.get("name") or item.get("model") or "") for item in models if item.get("name") or item.get("model")]
    configured = cfg.model
    selected = configured if configured in names else ""
    if not selected:
        selected = next((name for name in names if "qwen3" in name.lower()), "")
    if not selected:
        selected = next((name for name in names if "qwen" in name.lower()), "")
    if not selected:
        selected = names[0] if names else ""
    if not selected:
        raise RuntimeError("Ollama 已启动，但未发现可用本地模型")
    return {
        "available": True,
        "base_url": cfg.base_url,
        "root_url": root_url,
        "configured_model": configured,
        "selected_model": selected,
        "models": names,
    }


def _compact_json(value: Any, limit: int = 9000) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "...(已截断)"


def _clean_answer(text: str) -> str:
    value = text
    if "</think>" in value.lower():
        value = re.split(r"</think>", value, flags=re.I)[-1]
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.S | re.I).strip()
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value


def summarize_with_local_llm(
    *,
    question: str,
    intent: str,
    draft_answer: str,
    evidence: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    answer_style: str = "analysis",
) -> tuple[str, dict[str, Any]]:
    cfg = load_model_gateway_config()
    status = get_local_llm_status()
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    system_prompt = (
        "你是售电交易 AI 辅助决策平台的本地大模型助手。"
        "必须基于工具证据回答，不得编造数据库没有给出的具体数值。"
        "回答用中文，结构保持为：结论、数据依据、业务解释、建议。"
        "如果用户问天气、日期或通用问题，要直接回答用户真实问题，不要强行转成电力分析。"
        "不得给出保证收益、必须买入、必须卖出等绝对交易指令。"
        "直接输出最终答案，不要输出思考过程。"
    )
    user_payload = {
        "question": question,
        "intent": intent,
        "answer_style": answer_style,
        "draft_answer": draft_answer,
        "evidence": evidence,
        "tools": tools,
    }
    root_url = status["root_url"]
    response = requests.post(
        f"{root_url}/api/chat",
        headers={"Content-Type": "application/json"},
        json={
            "model": status["selected_model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _compact_json(user_payload)},
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 700,
            },
        },
        timeout=cfg.timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    content = str(payload.get("message", {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("本地模型返回空内容")
    return _clean_answer(content), status

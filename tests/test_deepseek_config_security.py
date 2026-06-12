from __future__ import annotations

from pathlib import Path


def test_deepseek_example_config_does_not_contain_real_key():
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" in text
    assert "sk-" not in text


def test_deepseek_key_not_hardcoded_in_new_backend_files():
    paths = [
        Path("backend/app/ai_assistant/llm_router.py"),
        Path("backend/app/ai_assistant/llm_providers/deepseek_provider.py"),
        Path("backend/app/ai_assistant/prompts.py"),
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "sk-" not in text

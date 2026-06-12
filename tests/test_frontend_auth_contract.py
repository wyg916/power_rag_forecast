from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_has_login_context_and_bearer_injection():
    api_text = (ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    app_text = (ROOT / "frontend/src/app/App.tsx").read_text(encoding="utf-8")
    provider_text = (ROOT / "frontend/src/app/providers.tsx").read_text(encoding="utf-8")
    assistant_text = (ROOT / "frontend/src/pages/assistant/AssistantPage.tsx").read_text(encoding="utf-8")

    assert "Authorization" in api_text
    assert "Bearer ${token}" in api_text
    assert "auth:unauthorized" in api_text
    assert "LoginPage" in app_text
    assert "AuthProvider" in provider_text
    assert "canUseDeveloperMode" in assistant_text


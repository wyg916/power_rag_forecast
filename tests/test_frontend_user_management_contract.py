from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_user_management_contract():
    user_api = (ROOT / "frontend/src/services/userApi.ts").read_text(encoding="utf-8")
    page = (ROOT / "frontend/src/pages/settings/UserManagementPage.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "frontend/src/pages/settings/SettingsPage.tsx").read_text(encoding="utf-8")
    header = (ROOT / "frontend/src/layout/HeaderBar.tsx").read_text(encoding="utf-8")
    auth_context = (ROOT / "frontend/src/context/AuthContext.tsx").read_text(encoding="utf-8")

    assert "password_hash" not in user_api
    assert "Input.Password" in page
    assert "user:write" in page
    assert "user:read" in settings
    assert "UserManagementPage" in settings
    assert "Dropdown" in header and "登录正式账号" in header
    assert "VITE_AUTH_REQUIRED ?? '1'" in auth_context


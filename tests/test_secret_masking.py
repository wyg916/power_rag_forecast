from __future__ import annotations

from backend.app.core.redaction import mask_api_key, mask_authorization, mask_db_url, mask_secret_fields


def test_secret_masking_helpers():
    assert mask_api_key("sk-1234567890abcdef").startswith("sk-")
    assert "7890abcdef" not in mask_api_key("sk-1234567890abcdef")
    assert mask_authorization("Bearer abcdefghijklmn") == "Bearer ******"
    assert mask_db_url("postgresql+psycopg2://postgres:secret@127.0.0.1:5432/postgres") == (
        "postgresql+psycopg2://postgres:******@127.0.0.1:5432/postgres"
    )


def test_mask_secret_fields_nested():
    payload = {
        "DEEPSEEK_API_KEY": "sk-1234567890abcdef",
        "headers": {"Authorization": "Bearer abcdefghijklmn"},
        "database_url": "postgresql://user:password@localhost/db",
        "nested": [{"token": "abc123"}],
        "safe": "ok",
    }
    masked = mask_secret_fields(payload)
    assert masked["DEEPSEEK_API_KEY"] == "******"
    assert masked["headers"]["Authorization"] == "Bearer ******"
    assert "password" not in masked["database_url"]
    assert masked["nested"][0]["token"] == "******"
    assert masked["safe"] == "ok"

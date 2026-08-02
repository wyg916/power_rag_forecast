from __future__ import annotations

from pathlib import Path

from backend.app.services.qdrant_security_contract import (
    qdrant_control_plane_issues,
    qdrant_security_status,
)


def _security_env(tmp_path: Path, *, role: str, access_mode: str) -> dict[str, str]:
    ca_path = tmp_path / "ca-cert.pem"
    ca_path.write_text("test-only-ca", encoding="utf-8")
    return {
        "RAG_QDRANT_URL": "https://qdrant:6333",
        "RAG_PROCESS_ROLE": role,
        "RAG_QDRANT_ACCESS_MODE": access_mode,
        "RAG_QDRANT_API_KEY": f"{role}-" + "k" * 40,
        "RAG_QDRANT_TLS_ENABLED": "1",
        "RAG_QDRANT_STRICT_MODE": "1",
        "RAG_QDRANT_TLS_CA_PATH": str(ca_path),
        "RAG_QDRANT_IMAGE_VERSION": "1.18.2",
        "RAG_QDRANT_IMAGE_DIGEST": "sha256:" + "d" * 64,
    }


def test_reader_and_publisher_runtime_profiles_are_separated(tmp_path: Path):
    reader = qdrant_security_status(
        _security_env(tmp_path, role="api", access_mode="read_only")
    )
    publisher = qdrant_security_status(
        _security_env(tmp_path, role="publisher", access_mode="admin")
    )
    wrong_reader = qdrant_security_status(
        _security_env(tmp_path, role="api", access_mode="admin")
    )
    wrong_publisher = qdrant_security_status(
        _security_env(tmp_path, role="publisher", access_mode="read_only")
    )

    assert reader.available is True
    assert publisher.available is True
    assert wrong_reader.issues == ("qdrant_access_mode_invalid",)
    assert wrong_publisher.issues == ("qdrant_access_mode_invalid",)
    assert "kkkk" not in repr(reader)
    assert "kkkk" not in repr(publisher)


def test_runtime_profile_rejects_insecure_or_unpinned_values(tmp_path: Path):
    base = _security_env(tmp_path, role="api", access_mode="read_only")
    changes = {
        "RAG_QDRANT_URL": ("http://qdrant:6333", "qdrant_https_endpoint_required"),
        "RAG_PROCESS_ROLE": ("unknown", "qdrant_process_role_invalid"),
        "RAG_QDRANT_TLS_ENABLED": ("maybe", "qdrant_tls_required"),
        "RAG_QDRANT_STRICT_MODE": ("0", "qdrant_strict_mode_required"),
        "RAG_QDRANT_API_KEY": ("replace_me", "qdrant_api_key_unavailable"),
        "RAG_QDRANT_IMAGE_VERSION": ("latest", "qdrant_image_version_invalid"),
        "RAG_QDRANT_IMAGE_DIGEST": ("sha256:unset", "qdrant_image_digest_invalid"),
    }

    for key, (value, issue) in changes.items():
        status = qdrant_security_status({**base, key: value})
        assert status.available is False
        assert issue in status.issues


def test_control_plane_requires_distinct_non_placeholder_keys_and_digest():
    valid = {
        "QDRANT_ADMIN_API_KEY": "admin-" + "a" * 40,
        "QDRANT_READ_ONLY_API_KEY": "readonly-" + "b" * 40,
        "QDRANT_IMAGE_DIGEST": "sha256:" + "c" * 64,
    }
    assert qdrant_control_plane_issues(valid) == ()
    assert "qdrant_keys_must_be_distinct" in qdrant_control_plane_issues(
        {**valid, "QDRANT_READ_ONLY_API_KEY": valid["QDRANT_ADMIN_API_KEY"]}
    )
    placeholder_issues = qdrant_control_plane_issues(
        {
            "QDRANT_ADMIN_API_KEY": "replace_with_admin_key",
            "QDRANT_READ_ONLY_API_KEY": "replace_with_read_key",
            "QDRANT_IMAGE_DIGEST": "sha256:replace_with_digest",
        }
    )
    assert set(placeholder_issues) == {
        "qdrant_admin_key_unavailable",
        "qdrant_read_only_key_unavailable",
        "qdrant_image_digest_invalid",
    }

from __future__ import annotations

import os
from pathlib import Path

from scripts import web_platform_launcher as launcher
from scripts import final_functional_isolated_launcher as acceptance_launcher


ROOT = Path(__file__).resolve().parents[1]


def test_web_batch_is_read_only_on_startup() -> None:
    source = (ROOT / "run_web_platform.bat").read_text(encoding="utf-8")

    assert "--skip-sync" in source
    assert "--restart" not in source
    assert "set \"PYTHON_EXE=python\"" not in source
    assert "rev-parse --git-common-dir" in source
    assert "mklink /J" in source
    assert "RAG_READER_CONFIG is validated by web_platform_launcher.py" in source

    for legacy_name in ("run_web_backend.bat", "run_web_frontend.bat"):
        legacy_source = (ROOT / legacy_name).read_text(encoding="utf-8")
        assert "--restart" not in legacy_source


def test_project_batch_defaults_to_unified_rc_and_has_health_gates() -> None:
    source = (ROOT / "run_project.bat").read_text(encoding="utf-8")

    assert 'if /I "%~1"=="menu" goto menu' in source
    assert "goto rcstart" in source
    assert "--preflight-only" in source
    assert source.count('phase4_precheck_runtime.py" --runtime-config') == 5
    assert 'redis start' in source
    assert 'celery start' in source
    assert '--worker-role forecast celery start' in source
    assert '--worker-role forecast celery status' in source
    assert 'combined health' in source
    assert "mklink /J" in source
    assert "automatic network install is disabled" in source
    assert source.count('runtime-config "%RAG_PREPRODUCTION_CONFIG%"') == 8
    assert source.count('day5_memory_worker_runtime.py" --runtime-config') == 2
    assert 'day5_memory_worker_runtime.py" --runtime-config "%RAG_PREPRODUCTION_CONFIG%" --runtime-config "%LOCAL_DATABASE_CONFIG%" --runtime-config "%LOCAL_RUNTIME_CONFIG%" start' in source
    assert 'day5_memory_worker_runtime.py" --runtime-config "%RAG_PREPRODUCTION_CONFIG%" --runtime-config "%LOCAL_DATABASE_CONFIG%" --runtime-config "%LOCAL_RUNTIME_CONFIG%" status' in source
    assert "deploy\\rag-r1\\preproduction-profile.env" in source
    assert "rag_r1_qdrant_runtime_probe.py\" --mode health" in source
    assert 'if not defined QDRANT_STARTUP_MAX_ATTEMPTS set "QDRANT_STARTUP_MAX_ATTEMPTS=48"' in source
    assert "GEQ %QDRANT_STARTUP_MAX_ATTEMPTS%" in source
    assert '--rag-qdrant-config "%QDRANT_RUNTIME_CONFIG%"' not in source
    assert '--rag-model-config "%RAG_MODEL_CONFIG%"' not in source
    assert "rag_r1_runtime_profile_check.py" in source

    web_source = (ROOT / "run_web_platform.bat").read_text(encoding="utf-8")
    assert 'runtime-config "%RAG_PREPRODUCTION_CONFIG%"' in web_source
    assert "deploy\\rag-r1\\preproduction-profile.env" in web_source
    assert '--rag-qdrant-config "%QDRANT_RUNTIME_CONFIG%"' not in web_source
    assert '--rag-model-config "%RAG_MODEL_CONFIG%"' not in web_source
    assert "RAG_READER_CONFIG is validated by web_platform_launcher.py" in web_source


def test_rag_preproduction_profile_is_secret_free_and_frozen() -> None:
    profile = (
        ROOT / "deploy" / "rag-r1" / "preproduction-profile.env"
    ).read_text(encoding="utf-8")
    values = "\n".join(
        line for line in profile.splitlines() if not line.lstrip().startswith("#")
    )

    assert "RAG_PROFILE=enterprise" in profile
    assert "RAG_RERANK_BATCH_SIZE=8" in profile
    assert "RAG_RERANK_MAX_LENGTH=32" in profile
    assert "RAG_RERANK_CANDIDATE_LIMIT=3" in profile
    assert "RAG_TOP_K=5" in profile
    assert "FORECAST_CELERY_QUEUE=forecast_final_rc" in profile
    assert "OMP_NUM_THREADS=6" in profile
    assert "MKL_NUM_THREADS=6" in profile
    assert not any(
        marker in values.upper() for marker in ("PASSWORD", "SECRET", "API_KEY")
    )


def test_isolated_acceptance_loads_frozen_preproduction_contract(
    monkeypatch, tmp_path
) -> None:
    profile = tmp_path / "preproduction.env"
    profile.write_text(
        "\n".join(
            (
                "RAG_PROFILE=enterprise",
                "RAG_RUNTIME_TARGET_MODE=preproduction_candidate",
                "RAG_RELEASE_ID=RAG-R1",
                "RAG_QDRANT_COLLECTION=rag_chunks_RAG-R1",
                "RAG_QDRANT_ALIAS=",
                "TOKENIZERS_PARALLELISM=false",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RAG_RUNTIME_TARGET_MODE", "production_alias")
    monkeypatch.setenv("RAG_QDRANT_API_KEY", "reader-key-must-be-preserved")

    acceptance_launcher.load_frozen_rag_profile(profile)

    assert os.environ["RAG_PROFILE"] == "enterprise"
    assert os.environ["RAG_RUNTIME_TARGET_MODE"] == "preproduction_candidate"
    assert os.environ["RAG_QDRANT_ALIAS"] == ""
    assert os.environ["RAG_QDRANT_API_KEY"] == "reader-key-must-be-preserved"


def test_database_target_accepts_only_approved_local_target(
    monkeypatch, capsys
) -> None:
    accepted = (
        "postgresql+psycopg://beta10d_app_login:do-not-print@127.0.0.1:5432/postgres"
    )
    security = (
        "postgresql+psycopg://beta10d_security_login:also-secret@localhost:5432/postgres"
    )
    monkeypatch.setenv("DATABASE_URL", accepted)
    monkeypatch.setenv("SECURITY_DATABASE_URL", security)

    assert launcher.validate_database_target() is True
    output = capsys.readouterr().out
    assert "beta10d_app_login + beta10d_security_login" in output
    assert "do-not-print" not in output
    assert "also-secret" not in output

    rejected = [
        "postgresql+psycopg://beta10d_app_login:x@db.example:5432/postgres",
        "postgresql+psycopg://beta10d_app_login:x@localhost:5433/postgres",
        "postgresql+psycopg://beta10d_app_login:x@localhost:5432/other",
        "postgresql+psycopg://postgres:x@localhost:5432/postgres",
    ]
    for value in rejected:
        monkeypatch.setenv("DATABASE_URL", value)
        assert launcher.validate_database_target() is False


def test_missing_frontend_dependencies_fail_without_install(
    monkeypatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(launcher, "FRONTEND_DIR", tmp_path)

    assert launcher.ensure_frontend_deps() is False
    output = capsys.readouterr().out
    assert "automatic network installation is disabled" in output


def test_web_ports_are_configurable_without_changing_defaults() -> None:
    source = (ROOT / "scripts" / "web_platform_launcher.py").read_text(
        encoding="utf-8"
    )
    project_batch = (ROOT / "run_project.bat").read_text(encoding="utf-8")

    assert '_configured_port("WEB_BACKEND_PORT", 8000)' in source
    assert '_configured_port("WEB_FRONTEND_PORT", 5173)' in source
    assert 'f"http://127.0.0.1:{BACKEND_PORT}"' in source
    assert 'if not defined WEB_BACKEND_PORT set "WEB_BACKEND_PORT=8000"' in project_batch
    assert 'if not defined WEB_FRONTEND_PORT set "WEB_FRONTEND_PORT=5173"' in project_batch
    assert "timeout=60" in source
    assert 'WEB_BACKEND_STARTUP_TIMEOUT", "720"' in source
    assert 'WEB_FRONTEND_STARTUP_TIMEOUT", "180"' in source
    assert "def backend_http_ok" in source
    assert 'warmup.get("status") == "ready"' in source
    assert "wait_backend_ready(BACKEND_STARTUP_TIMEOUT)" in source


def test_rag_reader_config_is_discovered_once_and_fail_closed() -> None:
    source = (ROOT / "scripts" / "web_platform_launcher.py").read_text(
        encoding="utf-8"
    )
    project_batch = (ROOT / "run_project.bat").read_text(encoding="utf-8")

    assert "resolve_rag_reader_config(args.rag_reader_config)" in source
    assert 'shared_root.parent.glob(f"{shared_root.name}_*")' in source
    assert "discovery must resolve exactly one file" in source
    assert '--rag-reader-config "%RAG_READER_CONFIG%"' not in project_batch


def test_runtime_config_layers_keep_least_privilege_identity_first(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECURITY_DATABASE_URL", raising=False)
    identity = tmp_path / "identity.env"
    runtime = tmp_path / "runtime.env"
    identity.write_text(
        "DATABASE_URL=postgresql+psycopg://beta10d_app_login:x@localhost:5432/postgres\n"
        "SECURITY_DATABASE_URL=postgresql+psycopg://beta10d_security_login:y@localhost:5432/postgres\n",
        encoding="utf-8",
    )
    runtime.write_text(
        "DATABASE_URL=postgresql+psycopg://postgres:z@localhost:5432/postgres\n",
        encoding="utf-8",
    )

    launcher.load_dotenv([identity, runtime])

    assert "beta10d_app_login" in launcher.os.environ["DATABASE_URL"]
    assert "beta10d_security_login" in launcher.os.environ["SECURITY_DATABASE_URL"]


def test_enterprise_rag_profile_overrides_stale_local_values_without_admin_key(
    monkeypatch, tmp_path
) -> None:
    embedding = tmp_path / "bge-large-zh-v1.5"
    reranker = tmp_path / "bge-reranker-v2-m3"
    embedding.mkdir()
    reranker.mkdir()
    ca = tmp_path / "ca.pem"
    ca.write_text("test-only", encoding="utf-8")
    qdrant = tmp_path / "qdrant.env"
    qdrant.write_text(
        "\n".join(
            (
                "QDRANT_READ_ONLY_API_KEY=readonly-" + "r" * 40,
                "QDRANT_ADMIN_API_KEY=admin-" + "a" * 40,
                "QDRANT_IMAGE_DIGEST=sha256:" + "d" * 64,
                f"RAG_R1_QDRANT_ROOT={tmp_path.as_posix()}",
            )
        ),
        encoding="utf-8",
    )
    model = tmp_path / "model.env"
    model.write_text(
        "\n".join(
            (
                "RAG_ENABLED=1",
                "RAG_PROFILE=enterprise",
                "RAG_FILE_FALLBACK_ENABLED=0",
                "RAG_EMBEDDING_PROVIDER=sentence_transformers",
                "RAG_EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5",
                "RAG_EMBEDDING_MODEL_NAME=BAAI/bge-large-zh-v1.5",
                f"RAG_EMBEDDING_MODEL_PATH={embedding.as_posix()}",
                "RAG_EMBEDDING_DIM=1024",
                "RAG_EMBEDDING_EXPECTED_DIM=1024",
                "RAG_EMBEDDING_VERSION=v1",
                "RAG_EMBEDDING_EXPECTED_VERSION=v1",
                "RAG_EMBEDDING_ALLOW_FALLBACK=0",
                "RAG_EMBEDDING_FALLBACK_PROVIDER=disabled",
                "RAG_RERANK_ENABLED=1",
                "RAG_RERANK_PROVIDER=bge",
                "RAG_RERANK_MODEL=bge-reranker-v2-m3",
                "RAG_RERANK_MODEL_NAME=bge-reranker-v2-m3",
                f"RAG_RERANK_MODEL_PATH={reranker.as_posix()}",
                "RAG_RERANK_VERSION=v1",
                "RAG_RERANK_EXPECTED_VERSION=v1",
                "RAG_RERANK_FALLBACK_PROVIDER=disabled",
                "RAG_RELEASE_ID=RAG-R1",
                "RAG_QDRANT_COLLECTION=rag_chunks_RAG-R1",
                "RAG_QDRANT_ALIAS=rag_chunks_current",
                "RAG_PROCESS_ROLE=api",
                "RAG_QDRANT_ACCESS_MODE=read_only",
                "RAG_QDRANT_TLS_ENABLED=1",
                "RAG_QDRANT_STRICT_MODE=1",
                "RAG_QDRANT_URL=https://127.0.0.1:6333",
                f"RAG_QDRANT_TLS_CA_PATH={ca.as_posix()}",
                "RAG_QDRANT_IMAGE_VERSION=1.18.2",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "256")
    monkeypatch.setenv("QDRANT_ADMIN_API_KEY", "must-not-survive")

    launcher.load_enterprise_rag_runtime(qdrant, model)

    assert launcher.os.environ["RAG_EMBEDDING_DIM"] == "1024"
    assert launcher.os.environ["RAG_QDRANT_API_KEY"].startswith("readonly-")
    assert "QDRANT_ADMIN_API_KEY" not in launcher.os.environ

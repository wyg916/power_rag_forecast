from __future__ import annotations

from pathlib import Path

from scripts import web_platform_launcher as launcher


ROOT = Path(__file__).resolve().parents[1]


def test_web_batch_is_read_only_on_startup() -> None:
    source = (ROOT / "run_web_platform.bat").read_text(encoding="utf-8")

    assert "--skip-sync" in source
    assert "--restart" not in source
    assert "set \"PYTHON_EXE=python\"" not in source
    assert "rev-parse --git-common-dir" in source
    assert "mklink /J" in source

    for legacy_name in ("run_web_backend.bat", "run_web_frontend.bat"):
        legacy_source = (ROOT / legacy_name).read_text(encoding="utf-8")
        assert "--restart" not in legacy_source


def test_project_batch_defaults_to_unified_rc_and_has_health_gates() -> None:
    source = (ROOT / "run_project.bat").read_text(encoding="utf-8")

    assert 'if /I "%~1"=="menu" goto menu' in source
    assert "goto rcstart" in source
    assert "--preflight-only" in source
    assert source.count('phase4_precheck_runtime.py" --runtime-config') == 3
    assert 'redis start' in source
    assert 'celery start' in source
    assert 'combined health' in source
    assert "mklink /J" in source
    assert "automatic network install is disabled" in source
    assert source.count('runtime-config "%RAG_PREPRODUCTION_CONFIG%"') == 4
    assert "deploy\\rag-r1\\preproduction-profile.env" in source

    web_source = (ROOT / "run_web_platform.bat").read_text(encoding="utf-8")
    assert 'runtime-config "%RAG_PREPRODUCTION_CONFIG%"' in web_source
    assert "deploy\\rag-r1\\preproduction-profile.env" in web_source


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
    assert "OMP_NUM_THREADS=6" in profile
    assert "MKL_NUM_THREADS=6" in profile
    assert not any(
        marker in values.upper() for marker in ("PASSWORD", "SECRET", "API_KEY")
    )


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

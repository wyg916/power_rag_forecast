from __future__ import annotations

import json
import logging
import subprocess
import sys

import pytest

from backend.app.core.redaction import redact_text, safe_exception_summary
from scripts.day6a_database_fingerprint import build_fingerprint, write_json, write_markdown


SENTINEL = "_".join(("SENTINEL", "SECRET", "MUST", "NOT", "LEAK"))
DATABASE_URL = (
    f"postgresql+psycopg://day6a:{SENTINEL}@localhost:5432/postgres"
    f"?token={SENTINEL}&api_key={SENTINEL}"
)


def assert_secret_absent(value: object) -> None:
    assert SENTINEL not in str(value)


@pytest.mark.parametrize(
    "value",
    [
        DATABASE_URL,
        f"password={SENTINEL}",
        f'{{"token": "{SENTINEL}"}}',
        f"api_key={SENTINEL}",
        f"secret={SENTINEL}",
        f"Authorization: Bearer {SENTINEL}",
    ],
    ids=("database_url", "password", "token", "api_key", "secret", "authorization"),
)
def test_redact_text_covers_supported_secret_shapes(value: str) -> None:
    redacted = redact_text(value, extra_secrets=(SENTINEL,))
    assert_secret_absent(redacted)
    assert "[REDACTED]" in redacted or "******" in redacted


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (f"JWT_SECRET_KEY={SENTINEL}", "JWT_SECRET_KEY=[REDACTED]"),
        (f"JWT_SECRET_KEY = {SENTINEL}", "JWT_SECRET_KEY = [REDACTED]"),
        (f'JWT_SECRET_KEY="{SENTINEL}"', 'JWT_SECRET_KEY="[REDACTED]"'),
        (f"JWT_SECRET_KEY='{SENTINEL}'", "JWT_SECRET_KEY='[REDACTED]'"),
        (f"jwt_secret_key={SENTINEL}", "jwt_secret_key=[REDACTED]"),
        (f'"JWT_SECRET_KEY": "{SENTINEL}"', '"JWT_SECRET_KEY": "[REDACTED]"'),
        (f"JWT_SECRET_KEY: {SENTINEL}", "JWT_SECRET_KEY: [REDACTED]"),
        (f"jwt-secret-key={SENTINEL}", "jwt-secret-key=[REDACTED]"),
    ],
    ids=(
        "environment",
        "spaces",
        "double_quoted_value",
        "single_quoted_value",
        "lowercase",
        "json",
        "plain_text_colon",
        "hyphenated_key",
    ),
)
def test_redact_text_covers_jwt_secret_key_assignments(value: str, expected: str) -> None:
    redacted = redact_text(value)
    assert redacted == expected
    assert_secret_absent(redacted)


@pytest.mark.parametrize(
    "value",
    [
        f"password={SENTINEL}",
        f"token={SENTINEL}",
        f"api_key={SENTINEL}",
        f"secret={SENTINEL}",
        f"Authorization: Bearer {SENTINEL}",
        DATABASE_URL,
    ],
    ids=("password", "token", "api_key", "secret", "authorization", "database_url"),
)
def test_redact_text_legacy_shapes_without_extra_secrets(value: str) -> None:
    assert_secret_absent(redact_text(value))


def test_jwt_secret_key_redaction_is_idempotent() -> None:
    once = redact_text(f'"JWT_SECRET_KEY": "{SENTINEL}"')
    assert once == '"JWT_SECRET_KEY": "[REDACTED]"'
    assert redact_text(once) == once
    assert redact_text("JWT_SECRET_KEY=[REDACTED]") == "JWT_SECRET_KEY=[REDACTED]"


def test_jwt_secret_key_stdout_stderr_and_logs_do_not_leak(capsys, caplog) -> None:
    redacted = redact_text(f"JWT_SECRET_KEY={SENTINEL}")
    with caplog.at_level(logging.ERROR):
        logging.getLogger("t004-hotfix-test").error("%s", redacted)
    print(redacted)
    print(redacted, file=sys.stderr)
    captured = capsys.readouterr()
    assert_secret_absent(captured.out)
    assert_secret_absent(captured.err)
    assert_secret_absent(caplog.text)


def test_jwt_secret_key_exception_chain_is_redacted() -> None:
    try:
        try:
            raise RuntimeError(f"JWT_SECRET_KEY={SENTINEL}")
        except RuntimeError as exc:
            raise ValueError(f'configuration failed: "JWT_SECRET_KEY": "{SENTINEL}"') from exc
    except ValueError as exc:
        report = safe_exception_summary(exc)
    serialized = json.dumps(report, ensure_ascii=False)
    assert_secret_absent(serialized)
    assert len(report["chain"]) == 2
    assert "[REDACTED]" in serialized


def test_jwt_secret_key_json_markdown_and_txt_evidence_are_redacted(tmp_path) -> None:
    report = {
        "status": "failed",
        "error": {"message": f"JWT_SECRET_KEY={SENTINEL}"},
    }
    json_path = tmp_path / "t004_hotfix.json"
    markdown_path = tmp_path / "t004_hotfix.md"
    txt_path = tmp_path / "t004_hotfix.txt"
    write_json(report, json_path)
    write_markdown(report, markdown_path)
    txt_path.write_text(redact_text(f"JWT_SECRET_KEY={SENTINEL}"), encoding="utf-8")
    for path in (json_path, markdown_path, txt_path):
        content = path.read_text(encoding="utf-8")
        assert_secret_absent(content)
        assert "[REDACTED]" in content


def test_sqlalchemy_dsn_parse_failure_is_safe() -> None:
    malformed = f"postgresql+psycopg://day6a:{SENTINEL}@localhost:not-a-port/postgres"
    report = build_fingerprint(malformed)
    assert report["status"] == "failed"
    assert report["stage"] == "parse_database_url"
    assert_secret_absent(json.dumps(report))


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ("psycopg_connection", "connection failed password={secret}"),
        ("dns_host", "host lookup failed for postgresql://user:{secret}@invalid/db"),
        ("authentication", "authentication failed password={secret}"),
        ("wrong_port", "port failure token={secret}"),
        ("database_missing", "database missing api_key={secret}"),
        ("environment_config", "DATABASE_URL=postgresql://user:{secret}@host/db"),
        ("fingerprint_exception", "fingerprint failed secret={secret}"),
    ],
)
def test_database_failure_scenarios_never_leak(scenario: str, message: str) -> None:
    def failing_connect(**kwargs):
        assert scenario
        raise RuntimeError(message.format(secret=kwargs["password"]))

    report = build_fingerprint(DATABASE_URL, connect_factory=failing_connect)
    assert report["status"] == "failed"
    assert report["stage"] == "database_fingerprint"
    serialized = json.dumps(report, ensure_ascii=False)
    assert_secret_absent(serialized)
    assert "RuntimeError" in serialized


def test_exception_chain_is_redacted_but_diagnostic() -> None:
    try:
        try:
            raise RuntimeError(f"password={SENTINEL}")
        except RuntimeError as exc:
            raise ValueError(f"failed URL {DATABASE_URL}") from exc
    except ValueError as exc:
        report = safe_exception_summary(exc, extra_secrets=(SENTINEL,))
    assert report["error_type"] == "ValueError"
    assert len(report["chain"]) == 2
    assert_secret_absent(json.dumps(report))


def test_json_and_markdown_evidence_are_redacted(tmp_path) -> None:
    report = {
        "status": "failed",
        "connection": {"host": "localhost", "port": 5432, "user": "day6a", "password": SENTINEL},
        "error": {"error_type": "RuntimeError", "message": f"password={SENTINEL}; {DATABASE_URL}"},
        "token": SENTINEL,
    }
    json_path = tmp_path / "fingerprint.json"
    markdown_path = tmp_path / "fingerprint.md"
    write_json(report, json_path)
    write_markdown(report, markdown_path)
    assert_secret_absent(json_path.read_text(encoding="utf-8"))
    assert_secret_absent(markdown_path.read_text(encoding="utf-8"))
    assert "RuntimeError" in markdown_path.read_text(encoding="utf-8")


def test_stdout_stderr_and_logs_do_not_leak(capsys, caplog) -> None:
    summary = safe_exception_summary(RuntimeError(f"Authorization: Bearer {SENTINEL}"), extra_secrets=(SENTINEL,))
    with caplog.at_level(logging.ERROR):
        logging.getLogger("day6a-test").error("%s", summary)
    print(json.dumps(summary))
    captured = capsys.readouterr()
    assert_secret_absent(captured.out)
    assert_secret_absent(captured.err)
    assert_secret_absent(caplog.text)


def test_current_git_diff_does_not_contain_runtime_sentinel() -> None:
    completed = subprocess.run(
        ["git", "diff", "--no-ext-diff", "HEAD", "--"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert_secret_absent(completed.stdout)

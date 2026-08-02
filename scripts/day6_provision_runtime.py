from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from psycopg import sql
from sqlalchemy import create_engine, text


GROUP_ROLE = "beta10d_forecast_runtime"
LOGIN_ROLE = "beta10d_forecast_login"
READ_TABLES = ("raw_market", "raw_load", "raw_weather")
MODEL_TABLES = ("model_registry",)
KNOWLEDGE_READ_TABLES = (
    "kb_documents",
    "kb_chunks",
    "kb_document_versions",
    "kb_releases",
    "kb_release_items",
)
KNOWLEDGE_COLUMN_READS = {
    "kb_rag_audit_events": (
        "tenant_id",
        "release_id",
        "event_type",
        "details_json",
        "created_at",
    ),
}
WRITE_TABLES = {
    "forecast_input_batches": ("SELECT", "INSERT", "UPDATE"),
    "forecast_input_snapshots": ("SELECT", "INSERT"),
    "forecast_runs": ("SELECT", "INSERT", "UPDATE"),
    "forecast_results": ("SELECT", "INSERT"),
    "report_runs": ("SELECT", "INSERT"),
    "report_reviews": ("SELECT", "INSERT"),
    "strategy_advice": ("SELECT", "INSERT", "UPDATE"),
    "strategy_reviews": ("SELECT", "INSERT"),
    "audit_logs": ("INSERT",),
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate_admin(url: str) -> None:
    parsed = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise RuntimeError("database_host_not_allowed")
    if (parsed.port or 5432) != 5432 or parsed.path.lstrip("/") != "postgres":
        raise RuntimeError("database_target_not_allowed")
    if parsed.username != "postgres":
        raise RuntimeError("administrator_identity_required")


def runtime_url(password: str) -> str:
    return f"postgresql+psycopg://{LOGIN_ROLE}:{quote(password, safe='')}@localhost:5432/postgres"


def existing_password(config: Path) -> str:
    url = read_env(config).get("DATABASE_URL", "")
    if not url:
        return ""
    parsed = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.username != LOGIN_ROLE:
        raise RuntimeError("runtime_config_identity_mismatch")
    return unquote(parsed.password or "")


def write_runtime_config(path: Path, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        (
            f"DATABASE_URL={runtime_url(password)}",
            "DAY6_ENVIRONMENT=development_demo",
            "MARKET_TIMEZONE=America/New_York",
            "PJM_PNODE_ID=34964545",
            "PJM_PNODE_NAME=DOM",
            "PJM_LOAD_AREA=DOMINION",
            "",
        )
    )
    path.write_text(content, encoding="utf-8")


def harden_acl(path: Path) -> dict[str, object]:
    if os.name != "nt":
        os.chmod(path, 0o600)
        return {"platform": os.name, "hardened": True}
    user = getpass.getuser()
    commands = (
        ["icacls", str(path), "/inheritance:r"],
        ["icacls", str(path), "/grant:r", f"{user}:(F)", "*S-1-5-18:(F)", "*S-1-5-32-544:(F)"],
        ["icacls", str(path), "/remove:g", "*S-1-5-11", "*S-1-5-32-545"],
    )
    return_codes = []
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        return_codes.append(result.returncode)
    return {"platform": "windows", "hardened": all(code == 0 for code in return_codes), "return_codes": return_codes}


def provision(admin_url: str, password: str) -> dict[str, object]:
    engine = create_engine(admin_url, pool_pre_ping=True, future=True)
    with engine.begin() as conn:
        conn.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{GROUP_ROLE}') THEN CREATE ROLE {GROUP_ROLE} NOLOGIN; END IF; END $$"))
        conn.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{LOGIN_ROLE}') THEN CREATE ROLE {LOGIN_ROLE} LOGIN; END IF; END $$"))
        conn.execute(text(f"ALTER ROLE {GROUP_ROLE} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOLOGIN"))
        with conn.connection.driver_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS LOGIN INHERIT PASSWORD {}"
                ).format(sql.Identifier(LOGIN_ROLE), sql.Literal(password))
            )
        conn.execute(text(f"GRANT {GROUP_ROLE} TO {LOGIN_ROLE}"))
        conn.execute(text(f"GRANT CONNECT ON DATABASE postgres TO {LOGIN_ROLE}"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {GROUP_ROLE}"))
        conn.execute(text(f"REVOKE CREATE ON SCHEMA public FROM {GROUP_ROLE}, {LOGIN_ROLE}"))
        existing = {
            row[0]
            for row in conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        }
        for table in READ_TABLES:
            if table in existing:
                conn.execute(text(f"GRANT SELECT ON TABLE public.{table} TO {GROUP_ROLE}"))
        for table in KNOWLEDGE_READ_TABLES:
            if table in existing:
                conn.execute(text(f"GRANT SELECT ON TABLE public.{table} TO {GROUP_ROLE}"))
        for table, columns in KNOWLEDGE_COLUMN_READS.items():
            if table in existing:
                conn.execute(
                    text(
                        f"GRANT SELECT ({','.join(columns)}) "
                        f"ON TABLE public.{table} TO {GROUP_ROLE}"
                    )
                )
        for table in MODEL_TABLES:
            if table in existing:
                conn.execute(text(f"GRANT SELECT, INSERT ON TABLE public.{table} TO {GROUP_ROLE}"))
        for table, privileges in WRITE_TABLES.items():
            if table in existing:
                conn.execute(text(f"GRANT {','.join(privileges)} ON TABLE public.{table} TO {GROUP_ROLE}"))
                has_id = bool(
                    conn.execute(
                        text(
                            "SELECT 1 FROM information_schema.columns "
                            "WHERE table_schema='public' AND table_name=:table AND column_name='id'"
                        ),
                        {"table": table},
                    ).first()
                )
                if has_id:
                    sequence = conn.execute(
                        text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                        {"table_name": f"public.{table}"},
                    ).scalar_one_or_none()
                    if sequence:
                        conn.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {GROUP_ROLE}"))
    runtime_engine = create_engine(runtime_url(password), pool_pre_ping=True, future=True)
    with runtime_engine.connect() as conn:
        identity = dict(
            conn.execute(
                text(
                    "SELECT current_user,session_user,current_database(),inet_server_port(),"
                    "r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolreplication,r.rolbypassrls "
                    "FROM pg_roles r WHERE r.rolname=current_user"
                )
            ).mappings().one()
        )
        privileges = {}
        for table in (*READ_TABLES, *MODEL_TABLES, *KNOWLEDGE_READ_TABLES, *WRITE_TABLES):
            privileges[table] = {
                privilege: bool(conn.execute(text("SELECT has_table_privilege(current_user,:table,:privilege)"), {"table": f"public.{table}", "privilege": privilege}).scalar_one())
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
            }
        for table, columns in KNOWLEDGE_COLUMN_READS.items():
            privileges[table] = {
                column: bool(
                    conn.execute(
                        text(
                            "SELECT has_column_privilege(current_user,:table,:column,'SELECT')"
                        ),
                        {"table": f"public.{table}", "column": column},
                    ).scalar_one()
                )
                for column in columns
            }
    dangerous = any(identity[name] for name in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls"))
    if identity["current_user"] != LOGIN_ROLE or dangerous:
        raise RuntimeError("runtime_identity_gate_failed")
    return {"identity": identity, "privileges": privileges, "dangerous_attributes": dangerous}


def rollback(admin_url: str) -> dict[str, object]:
    engine = create_engine(admin_url, pool_pre_ping=True, future=True)
    with engine.begin() as conn:
        conn.execute(text(f"REVOKE {GROUP_ROLE} FROM {LOGIN_ROLE}"))
        conn.execute(text(f"DROP ROLE IF EXISTS {LOGIN_ROLE}"))
        conn.execute(text(f"DROP ROLE IF EXISTS {GROUP_ROLE}"))
    return {"roles_removed": [LOGIN_ROLE, GROUP_ROLE], "runtime_config_retained": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-config", type=Path, required=True)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    admin_url = read_env(args.admin_config).get("DATABASE_URL", "")
    validate_admin(admin_url)
    if args.rollback:
        result = rollback(admin_url)
    else:
        password = existing_password(args.runtime_config) or secrets.token_urlsafe(36)
        result = provision(admin_url, password)
        write_runtime_config(args.runtime_config, password)
        result["acl"] = harden_acl(args.runtime_config)
        result["runtime_config_path"] = str(args.runtime_config)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    safe = {
        "operation": "rollback" if args.rollback else "provision",
        "roles": [GROUP_ROLE, LOGIN_ROLE],
        "identity": result.get("identity"),
        "dangerous_attributes": result.get("dangerous_attributes"),
        "acl": result.get("acl"),
        "runtime_config_path": result.get("runtime_config_path"),
    }
    print(json.dumps(safe, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

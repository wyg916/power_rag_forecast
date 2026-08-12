from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )
    try:
        with engine.connect() as connection:
            identity = dict(
                connection.execute(
                    text(
                        """
                        SELECT current_database() AS database_name,
                               current_user AS current_user,
                               current_setting('transaction_read_only') AS transaction_read_only
                        """
                    )
                ).mappings().one()
            )
            releases = [
                dict(row)
                for row in connection.execute(
                    text(
                        """
                        SELECT release_id, collection_name, status, is_current,
                               embedding_dimension, embedding_provider, reranker_model
                        FROM kb_releases
                        WHERE tenant_id = 'default'
                        ORDER BY created_at DESC
                        """
                    )
                ).mappings()
            ]
            counts = dict(
                connection.execute(
                    text(
                        """
                        SELECT
                          (SELECT COUNT(*) FROM kb_documents) AS documents,
                          (SELECT COUNT(*) FROM kb_chunks) AS chunks,
                          (SELECT COUNT(*) FROM ai_chat_sessions) AS chat_sessions,
                          (SELECT COUNT(*) FROM ai_chat_messages) AS chat_messages
                        """
                    )
                ).mappings().one()
            )
    finally:
        engine.dispose()
    payload = {
        "status": "PASS" if identity["transaction_read_only"] == "on" else "FAIL",
        "identity": identity,
        "releases": releases,
        "counts": counts,
        "database_write_count": 0,
        "secret_values_emitted": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.rag_runtime_contract import runtime_contract_status


class RuntimeProfileCheckError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeProfileCheckError("runtime_profile_file_missing")
    return {key: str(value or "") for key, value in dotenv_values(path).items()}


def merge_runtime_values(
    qdrant_values: dict[str, str], model_values: dict[str, str]
) -> dict[str, str]:
    values = dict(model_values)
    required = (
        "QDRANT_READ_ONLY_API_KEY",
        "QDRANT_IMAGE_DIGEST",
        "RAG_R1_QDRANT_ROOT",
    )
    if any(not qdrant_values.get(key) for key in required):
        raise RuntimeProfileCheckError("runtime_qdrant_profile_incomplete")
    values.update(
        {
            "RAG_QDRANT_API_KEY": qdrant_values["QDRANT_READ_ONLY_API_KEY"],
            "RAG_QDRANT_IMAGE_DIGEST": qdrant_values["QDRANT_IMAGE_DIGEST"],
        }
    )
    if "QDRANT_ADMIN_API_KEY" in values:
        raise RuntimeProfileCheckError("runtime_admin_key_leak")
    return values


def check_profile(qdrant_env: Path, model_env: Path) -> dict:
    values = merge_runtime_values(_read(qdrant_env), _read(model_env))
    status = runtime_contract_status(values)
    if not status.available:
        raise RuntimeProfileCheckError("runtime_contract_unavailable:" + ",".join(status.issues))
    return {
        "status": "PASS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "enterprise": status.enterprise,
        "issues": list(status.issues),
        "embedding": {
            "provider": status.embedding.provider,
            "model": status.embedding.model,
            "version": status.embedding.version,
            "dimension": status.embedding.dimensions,
            "fallback_enabled": status.embedding.fallback_enabled,
        },
        "reranker": {
            "provider": status.reranker.provider,
            "model": status.reranker.model,
            "version": status.reranker.version,
            "enabled": status.reranker.enabled,
            "fallback_enabled": status.reranker.fallback_enabled,
        },
        "release": {
            "release_id": status.release.release_id,
            "collection": status.release.collection,
            "alias": status.release.alias,
        },
        "qdrant": {
            "endpoint": status.qdrant.endpoint,
            "access_mode": status.qdrant.access_mode,
            "tls_enabled": status.qdrant.tls_enabled,
            "strict_mode": status.qdrant.strict_mode,
            "api_key_configured": status.qdrant.api_key_configured,
            "image_version": status.qdrant.image_version,
            "image_digest_configured": status.qdrant.image_digest_configured,
        },
        "admin_key_available_to_runtime": False,
        "secret_values_emitted": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate merged RAG-R1 runtime profile")
    parser.add_argument("--qdrant-env", type=Path, required=True)
    parser.add_argument("--model-env", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = check_profile(args.qdrant_env.resolve(), args.model_env.resolve())
    except Exception as exc:
        print(f"RAG-R1 runtime profile FAILED: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

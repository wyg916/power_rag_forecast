from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROBE_RE = re.compile(r"^rag_r1_security_probe_[0-9]{8}_[0-9]{6}_[0-9]+$")


class QdrantProbeError(RuntimeError):
    pass


def _load(env_file: Path) -> dict[str, str]:
    values = {key: str(value or "") for key, value in dotenv_values(env_file).items()}
    required = (
        "RAG_R1_QDRANT_ROOT",
        "QDRANT_ADMIN_API_KEY",
        "QDRANT_READ_ONLY_API_KEY",
        "QDRANT_IMAGE_DIGEST",
    )
    if any(not values.get(key) for key in required):
        raise QdrantProbeError("qdrant_probe_configuration_incomplete")
    if values["QDRANT_ADMIN_API_KEY"] == values["QDRANT_READ_ONLY_API_KEY"]:
        raise QdrantProbeError("qdrant_probe_keys_not_distinct")
    return values


def _probe_name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"rag_r1_security_probe_{stamp}_{os.getpid()}"


def _request(
    endpoint: str,
    context: ssl.SSLContext,
    path: str,
    *,
    key: str = "",
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"accept": "application/json"}
    if key:
        headers["api-key"] = key
    data = None
    if payload is not None:
        headers["content-type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode()
    request = Request(endpoint + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, context=context, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"error_type": "non_json_error"}
        return exc.code, parsed


def run_probe(env_file: Path) -> dict[str, Any]:
    values = _load(env_file)
    root = Path(values["RAG_R1_QDRANT_ROOT"]).resolve()
    ca_path = root / "tls" / "ca-cert.pem"
    if not ca_path.is_file():
        raise QdrantProbeError("qdrant_probe_ca_missing")
    endpoint = "https://127.0.0.1:6333"
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or parsed.hostname != "127.0.0.1" or parsed.port != 6333:
        raise QdrantProbeError("qdrant_probe_endpoint_invalid")
    context = ssl.create_default_context(cafile=str(ca_path))
    admin = values["QDRANT_ADMIN_API_KEY"]
    reader = values["QDRANT_READ_ONLY_API_KEY"]
    collection = _probe_name()
    created = False
    deleted = False
    checks: dict[str, Any] = {}
    try:
        status, root_payload = _request(endpoint, context, "/", key=reader)
        checks["tls_version_read"] = status == 200 and root_payload.get("version") == "1.18.2"
        status, _ = _request(endpoint, context, "/collections")
        checks["no_key_read_denied"] = status in {401, 403}
        status, _ = _request(endpoint, context, "/collections", key=reader)
        checks["read_only_key_read_allowed"] = status == 200
        create_payload = {
            "vectors": {"size": 1024, "distance": "Cosine"},
            "strict_mode_config": {"enabled": True},
        }
        status, _ = _request(
            endpoint,
            context,
            f"/collections/{collection}",
            key=reader,
            method="PUT",
            payload=create_payload,
        )
        checks["read_only_key_create_denied"] = status in {401, 403}
        status, _ = _request(
            endpoint,
            context,
            f"/collections/{collection}",
            key=admin,
            method="PUT",
            payload=create_payload,
        )
        if status != 200:
            raise QdrantProbeError(f"qdrant_admin_create_failed:{status}")
        created = True
        status, inspection = _request(
            endpoint, context, f"/collections/{collection}", key=admin
        )
        result = inspection.get("result", {})
        vectors = result.get("config", {}).get("params", {}).get("vectors", {})
        strict = result.get("strict_mode_config") or result.get("config", {}).get(
            "strict_mode_config", {}
        )
        checks["admin_create_and_inspect"] = status == 200
        checks["vector_dimension_1024"] = vectors.get("size") == 1024
        checks["strict_mode_enabled"] = strict.get("enabled") is True
        point_payload = {
            "points": [
                {
                    "id": 1,
                    "vector": [0.0] * 1024,
                    "payload": {"tenant_id": "default", "status": "probe"},
                }
            ]
        }
        status, _ = _request(
            endpoint,
            context,
            f"/collections/{collection}/points?wait=true",
            key=reader,
            method="PUT",
            payload=point_payload,
        )
        checks["read_only_key_write_denied"] = status in {401, 403}
    finally:
        if created:
            status, _ = _request(
                endpoint,
                context,
                f"/collections/{collection}",
                key=admin,
                method="DELETE",
            )
            deleted = status == 200
    checks["probe_collection_deleted"] = deleted
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise QdrantProbeError(f"qdrant_runtime_probe_failed:{failed}")
    return {
        "status": "PASS",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "image_version": "1.18.2",
        "image_digest": values["QDRANT_IMAGE_DIGEST"],
        "checks": checks,
        "probe_collection": collection,
        "probe_collection_deleted": deleted,
        "secret_values_emitted": False,
        "persistent_candidate_mutations": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe RAG-R1 Qdrant TLS and key roles")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_probe(args.env_file.resolve())
    except Exception as exc:
        print(f"Qdrant runtime probe FAILED: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.qdrant_security_contract import qdrant_control_plane_issues


EXPECTED_VERSION = "1.18.2"
TLS_FILES = ("ca-cert.pem", "server-cert.pem", "server-key.pem")


class QdrantPreflightError(RuntimeError):
    pass


def _values(env_file: Path) -> dict[str, str]:
    if not env_file.is_file():
        raise QdrantPreflightError("qdrant_env_file_missing")
    return {key: str(value or "") for key, value in dotenv_values(env_file).items()}


def _runtime_root(values: Mapping[str, str]) -> Path:
    raw = str(values.get("RAG_R1_QDRANT_ROOT", "")).strip()
    if not raw:
        raise QdrantPreflightError("qdrant_runtime_root_missing")
    root = Path(raw).resolve()
    if root.drive.upper() != "E:":
        raise QdrantPreflightError("qdrant_runtime_root_must_be_e_drive")
    try:
        root.relative_to(PROJECT_ROOT)
    except ValueError:
        pass
    else:
        raise QdrantPreflightError("qdrant_runtime_root_must_be_outside_repository")
    return root


def _pem_ok(path: Path, marker: str) -> bool:
    try:
        content = path.read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return False
    return f"-----BEGIN {marker}-----" in content and f"-----END {marker}-----" in content


def inspect_preflight(
    values: Mapping[str, str], *, require_assets: bool, require_runtime: bool
) -> dict[str, Any]:
    root = _runtime_root(values)
    issues = list(qdrant_control_plane_issues(values))
    if str(values.get("RAG_QDRANT_IMAGE_VERSION", EXPECTED_VERSION)) != EXPECTED_VERSION:
        issues.append("qdrant_image_version_invalid")
    try:
        port = int(str(values.get("QDRANT_PORT", "6333")))
    except ValueError:
        port = 0
    if not 1024 <= port <= 65535:
        issues.append("qdrant_port_invalid")

    tls_root = root / "tls"
    asset_status = {
        "storage": (root / "storage").is_dir(),
        "snapshots": (root / "snapshots").is_dir(),
        "ca_cert": _pem_ok(tls_root / TLS_FILES[0], "CERTIFICATE"),
        "server_cert": _pem_ok(tls_root / TLS_FILES[1], "CERTIFICATE"),
        "server_key": _pem_ok(tls_root / TLS_FILES[2], "PRIVATE KEY"),
    }
    if require_assets:
        issues.extend(
            f"qdrant_asset_unavailable:{name}"
            for name, available in asset_status.items()
            if not available
        )

    docker = shutil.which("docker")
    if require_runtime and not docker:
        issues.append("qdrant_container_runtime_unavailable")
    result = {
        "available": not issues,
        "issues": tuple(dict.fromkeys(issues)),
        "image": f"qdrant/qdrant:v{EXPECTED_VERSION}",
        "digest_configured": not any("digest" in issue for issue in issues),
        "keys_configured": not any("key" in issue for issue in issues),
        "keys_distinct": "qdrant_keys_must_be_distinct" not in issues,
        "bind": f"127.0.0.1:{port}" if port else "invalid",
        "runtime_root": str(root),
        "runtime_root_drive": root.drive.upper(),
        "assets": asset_status,
        "container_runtime": "docker" if docker else "unavailable",
        "secret_values_emitted": False,
    }
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG-R1 Qdrant safe local preflight")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--require-assets", action="store_true")
    parser.add_argument("--require-runtime", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect_preflight(
            _values(args.env_file.resolve()),
            require_assets=args.require_assets,
            require_runtime=args.require_runtime,
        )
    except Exception as exc:
        print(f"Qdrant preflight FAILED: {exc}")
        return 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

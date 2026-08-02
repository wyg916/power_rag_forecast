from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE = "qdrant/qdrant:v1.18.2"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RUNTIME_DIRS = ("storage", "snapshots", "tls", "secrets")


class QdrantBootstrapError(RuntimeError):
    pass


def validate_root(root: Path) -> Path:
    resolved = root.resolve()
    if resolved.drive.upper() != "E:":
        raise QdrantBootstrapError("qdrant_runtime_root_must_be_e_drive")
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        pass
    else:
        raise QdrantBootstrapError("qdrant_runtime_root_must_be_outside_repository")
    if resolved.exists():
        raise QdrantBootstrapError("qdrant_runtime_root_already_exists")
    return resolved


def validate_digest(value: str) -> str:
    digest = value.strip().lower()
    if not DIGEST_RE.fullmatch(digest):
        raise QdrantBootstrapError("qdrant_image_digest_invalid")
    return digest


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command), check=False, capture_output=True, text=True
    )
    if completed.returncode:
        raise QdrantBootstrapError(
            f"command_failed:{command[0]}:{completed.returncode}:"
            f"{completed.stderr[-500:]}"
        )
    return completed


def _verify_local_image(digest: str) -> dict[str, str]:
    completed = _run(
        [
            "docker",
            "image",
            "inspect",
            IMAGE,
            "--format",
            "{{json .RepoDigests}}|{{.Id}}|{{.Os}}/{{.Architecture}}",
        ]
    )
    output = completed.stdout.strip()
    if f"qdrant/qdrant@{digest}" not in output:
        raise QdrantBootstrapError("qdrant_local_image_digest_mismatch")
    parts = output.rsplit("|", 2)
    return {"image_id": parts[-2], "platform": parts[-1], "digest": digest}


def _write_exclusive(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    os.chmod(path, 0o600)


def _generate_tls(root: Path, digest: str) -> None:
    extensions = """basicConstraints=CA:FALSE
subjectAltName=DNS:qdrant,DNS:localhost,IP:127.0.0.1
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
"""
    _write_exclusive(root / "secrets" / "server-ext.cnf", extensions)
    image = f"{IMAGE}@{digest}"
    command = " && ".join(
        (
            "openssl genrsa -out /secrets/ca-key.pem 3072",
            "openssl req -x509 -new -sha256 -days 825 -key /secrets/ca-key.pem "
            "-subj '/CN=RAG-R1 Local CA' -out /tls/ca-cert.pem",
            "openssl genrsa -out /tls/server-key.pem 3072",
            "openssl req -new -sha256 -key /tls/server-key.pem "
            "-subj '/CN=qdrant' -out /secrets/server.csr",
            "openssl x509 -req -sha256 -days 825 -in /secrets/server.csr "
            "-CA /tls/ca-cert.pem -CAkey /secrets/ca-key.pem -CAcreateserial "
            "-extfile /secrets/server-ext.cnf -out /tls/server-cert.pem",
            "chmod 600 /secrets/ca-key.pem /tls/server-key.pem",
            "chmod 644 /tls/ca-cert.pem /tls/server-cert.pem",
        )
    )
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "sh",
            "-v",
            f"{root / 'tls'}:/tls",
            "-v",
            f"{root / 'secrets'}:/secrets",
            image,
            "-ec",
            command,
        ]
    )


def _apply_windows_acl(root: Path) -> str:
    completed = _run(["whoami", "/user", "/fo", "csv", "/nh"])
    row = next(csv.reader([completed.stdout.strip()]))
    if len(row) < 2 or not row[1].startswith("S-1-"):
        raise QdrantBootstrapError("current_user_sid_unavailable")
    account, sid = row[0], row[1]
    directories = (root, *sorted(path for path in root.rglob("*") if path.is_dir()))
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in directories:
        _run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{account}:(OI)(CI)F",
                "/grant:r",
                "SYSTEM:(OI)(CI)F",
            ]
        )
    for path in files:
        _run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{account}:F",
                "/grant:r",
                "SYSTEM:F",
            ]
        )
    return hashlib.sha256(sid.encode()).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _report(root: Path, image: dict[str, str], sid_hash: str) -> dict[str, Any]:
    return {
        "status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "image": image,
        "bind": "127.0.0.1:6333",
        "keys_distinct": True,
        "key_values_emitted": False,
        "acl_applied": True,
        "principal_sid_sha256": sid_hash,
        "certificates": {
            name: _sha256(root / "tls" / name)
            for name in ("ca-cert.pem", "server-cert.pem")
        },
        "private_files": (
            "secrets/runtime.env",
            "secrets/ca-key.pem",
            "tls/server-key.pem",
        ),
    }


def bootstrap(root: Path, digest: str) -> dict[str, Any]:
    root = validate_root(root)
    digest = validate_digest(digest)
    image = _verify_local_image(digest)
    root.mkdir(parents=True, exist_ok=False)
    for name in RUNTIME_DIRS:
        (root / name).mkdir(exist_ok=False)
    try:
        _generate_tls(root, digest)
        admin_key = secrets.token_urlsafe(48)
        reader_key = secrets.token_urlsafe(48)
        if admin_key == reader_key:
            raise QdrantBootstrapError("qdrant_generated_keys_not_distinct")
        runtime_env = "\n".join(
            (
                f"RAG_R1_QDRANT_ROOT={root.as_posix()}",
                "QDRANT_PORT=6333",
                f"QDRANT_IMAGE_DIGEST={digest}",
                f"QDRANT_ADMIN_API_KEY={admin_key}",
                f"QDRANT_READ_ONLY_API_KEY={reader_key}",
                "RAG_QDRANT_IMAGE_VERSION=1.18.2",
                "RAG_ENABLED=0",
                "RAG_RELEASE_ID=RAG-R1",
                "RAG_QDRANT_COLLECTION=rag_chunks_RAG-R1",
                "",
            )
        )
        env_path = root / "secrets" / "runtime.env"
        _write_exclusive(env_path, runtime_env)
        sid_hash = _apply_windows_acl(root)
        report = _report(root, image, sid_hash)
        _write_exclusive(
            root / "bootstrap-report.json",
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        )
        return report
    except Exception:
        # Fail closed without deleting potentially useful forensic material.
        raise


def resume_bootstrap(root: Path, digest: str) -> dict[str, Any]:
    root = root.resolve()
    if root.drive.upper() != "E:" or not root.is_dir():
        raise QdrantBootstrapError("qdrant_resume_root_invalid")
    try:
        root.relative_to(PROJECT_ROOT)
    except ValueError:
        pass
    else:
        raise QdrantBootstrapError("qdrant_runtime_root_must_be_outside_repository")
    digest = validate_digest(digest)
    image = _verify_local_image(digest)
    required = (
        root / "secrets" / "runtime.env",
        root / "secrets" / "ca-key.pem",
        root / "tls" / "ca-cert.pem",
        root / "tls" / "server-cert.pem",
        root / "tls" / "server-key.pem",
    )
    if not all(path.is_file() for path in required):
        raise QdrantBootstrapError("qdrant_resume_assets_incomplete")
    report_path = root / "bootstrap-report.json"
    if report_path.exists():
        raise QdrantBootstrapError("qdrant_bootstrap_report_already_exists")
    sid_hash = _apply_windows_acl(root)
    values = {}
    for line in (root / "secrets" / "runtime.env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    if (
        values.get("QDRANT_IMAGE_DIGEST") != digest
        or len(values.get("QDRANT_ADMIN_API_KEY", "")) < 32
        or len(values.get("QDRANT_READ_ONLY_API_KEY", "")) < 32
        or values.get("QDRANT_ADMIN_API_KEY") == values.get("QDRANT_READ_ONLY_API_KEY")
    ):
        raise QdrantBootstrapError("qdrant_resume_runtime_env_invalid")
    report = _report(root, image, sid_hash)
    _write_exclusive(
        report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap isolated RAG-R1 Qdrant assets")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        action = resume_bootstrap if args.resume else bootstrap
        result = action(args.root, args.image_digest)
    except Exception as exc:
        print(f"Qdrant bootstrap FAILED: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

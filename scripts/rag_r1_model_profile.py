from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_OUTPUT = Path(
    "E:/智能运营分析项目_运行资产/rag-r1/qdrant/secrets/model-profile.env"
).resolve()
EMBEDDING_ROOT = Path("E:/智能运营分析项目/bge-large-zh-v1.5").resolve()
RERANKER_ROOT = Path("E:/智能运营分析项目/bge-reranker-v2-m3").resolve()


class ModelProfileError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelProfileError("model_profile_evidence_invalid") from exc
    if not isinstance(value, dict) or value.get("status") != "PASS":
        raise ModelProfileError("model_profile_evidence_not_pass")
    return value


def render_profile(
    admission: Mapping[str, Any], smoke: Mapping[str, Any]
) -> tuple[str, dict[str, str]]:
    versions = {
        role: str(admission["models"][role]["version"])
        for role in ("embedding", "reranker")
    }
    for role, version in versions.items():
        runtime = smoke.get("models", {}).get(role, {})
        if runtime.get("status") != "PASS" or runtime.get("version") != version:
            raise ModelProfileError(f"model_profile_runtime_mismatch:{role}")
        if runtime.get("fallback_used") is not False or runtime.get("network_calls") != 0:
            raise ModelProfileError(f"model_profile_runtime_unsafe:{role}")
    values = {
        "APP_ENV": "test",
        "RAG_ENABLED": "1",
        "RAG_PROFILE": "enterprise",
        "RAG_FILE_FALLBACK_ENABLED": "0",
        "RAG_EMBEDDING_PROVIDER": "sentence_transformers",
        "RAG_EMBEDDING_MODEL": "bge-large-zh-v1.5",
        "RAG_EMBEDDING_MODEL_NAME": "bge-large-zh-v1.5",
        "RAG_EMBEDDING_MODEL_PATH": EMBEDDING_ROOT.as_posix(),
        "RAG_EMBEDDING_DIM": "1024",
        "RAG_EMBEDDING_EXPECTED_DIM": "1024",
        "RAG_EMBEDDING_VERSION": versions["embedding"],
        "RAG_EMBEDDING_EXPECTED_VERSION": versions["embedding"],
        "RAG_EMBEDDING_ALLOW_FALLBACK": "0",
        "RAG_EMBEDDING_FALLBACK_PROVIDER": "disabled",
        "RAG_RERANK_ENABLED": "1",
        "RAG_RERANK_PROVIDER": "bge",
        "RAG_RERANK_MODEL": "bge-reranker-v2-m3",
        "RAG_RERANK_MODEL_NAME": "bge-reranker-v2-m3",
        "RAG_RERANK_MODEL_PATH": RERANKER_ROOT.as_posix(),
        "RAG_RERANK_VERSION": versions["reranker"],
        "RAG_RERANK_EXPECTED_VERSION": versions["reranker"],
        "RAG_RERANK_FALLBACK_PROVIDER": "disabled",
        "RAG_RELEASE_ID": "RAG-R1",
        "RAG_QDRANT_COLLECTION": "rag_chunks_RAG-R1",
        "RAG_QDRANT_ALIAS": "rag_chunks_current",
        "RAG_PROCESS_ROLE": "api",
        "RAG_QDRANT_ACCESS_MODE": "read_only",
        "RAG_QDRANT_TLS_ENABLED": "1",
        "RAG_QDRANT_STRICT_MODE": "1",
        "RAG_QDRANT_URL": "https://127.0.0.1:6333",
        "RAG_QDRANT_TLS_CA_PATH": (
            EXPECTED_OUTPUT.parent.parent / "tls" / "ca-cert.pem"
        ).as_posix(),
        "RAG_QDRANT_IMAGE_VERSION": "1.18.2",
    }
    return "\n".join(f"{key}={value}" for key, value in values.items()) + "\n", versions


def _acl(path: Path) -> str:
    identity = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
    )
    row = next(csv.reader([identity.stdout.strip()]))
    account, sid = row[0], row[1]
    completed = subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{account}:F",
            "/grant:r",
            "SYSTEM:F",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise ModelProfileError("model_profile_acl_failed")
    return hashlib.sha256(sid.encode()).hexdigest()


def create_profile(admission: Path, smoke: Path, output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output != EXPECTED_OUTPUT or output.exists() or not output.parent.is_dir():
        raise ModelProfileError("model_profile_output_rejected")
    content, versions = render_profile(_load(admission), _load(smoke))
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    sid_hash = _acl(output)
    return {
        "status": "PASS",
        "output": str(output),
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "versions": versions,
        "acl_applied": True,
        "principal_sid_sha256": sid_hash,
        "secret_values_written": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create admitted RAG-R1 model profile")
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=EXPECTED_OUTPUT)
    args = parser.parse_args(argv)
    try:
        result = create_profile(args.admission, args.smoke, args.output)
    except Exception as exc:
        print(f"RAG-R1 model profile FAILED: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

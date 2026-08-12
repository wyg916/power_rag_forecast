from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.day3_test_database_guard import main as isolation_main
from scripts.web_platform_launcher import load_enterprise_rag_runtime, load_env_file


def load_frozen_rag_profile(path: Path) -> None:
    """Overlay the Git-controlled, secret-free preproduction RAG contract."""

    if not path.is_file():
        raise RuntimeError(f"Frozen RAG runtime profile does not exist: {path}")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        upper_key = key.upper()
        if upper_key in {"PASSWORD", "SECRET", "API_KEY", "TOKEN"} or upper_key.endswith(
            ("_PASSWORD", "_SECRET", "_API_KEY", "_TOKEN")
        ):
            raise RuntimeError("Frozen RAG runtime profile must remain secret-free")
        if key.startswith("RAG_") or key in {
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "TOKENIZERS_PARALLELISM",
        }:
            os.environ[key] = value.strip().strip('"').strip("'")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--local-runtime-config", type=Path)
    parser.add_argument("--rag-qdrant-config", type=Path)
    parser.add_argument("--rag-model-config", type=Path)
    parser.add_argument(
        "--rag-runtime-profile",
        type=Path,
        default=ROOT / "deploy" / "rag-r1" / "preproduction-profile.env",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    load_env_file(args.env_file.resolve(), required=True)
    if args.local_runtime_config:
        load_env_file(args.local_runtime_config.resolve(), required=True)
    if bool(args.rag_qdrant_config) != bool(args.rag_model_config):
        raise RuntimeError(
            "--rag-qdrant-config and --rag-model-config must be provided together"
        )
    if args.rag_qdrant_config and args.rag_model_config:
        load_enterprise_rag_runtime(
            args.rag_qdrant_config.resolve(),
            args.rag_model_config.resolve(),
        )
    load_frozen_rag_profile(args.rag_runtime_profile.resolve())
    # Browser acceptance writes only to the disposable PostgreSQL schema. The
    # formal Qdrant collection remains under its independent read-only probe.
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    return isolation_main(command)


if __name__ == "__main__":
    raise SystemExit(main())

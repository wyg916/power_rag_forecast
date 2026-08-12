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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--local-runtime-config", type=Path)
    parser.add_argument("--rag-qdrant-config", type=Path)
    parser.add_argument("--rag-model-config", type=Path)
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
    # Browser acceptance writes only to the disposable PostgreSQL schema. The
    # formal Qdrant collection remains under its independent read-only probe.
    os.environ["RAG_PROFILE"] = "balanced"
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    return isolation_main(command)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .ledger import build_source_ledger, write_source_ledger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a deterministic RAG-R1 source admission ledger.")
    parser.add_argument("--input", type=Path, required=True, help="Read-only corpus directory.")
    parser.add_argument("--staging-root", type=Path, required=True, help="Runtime staging root on the project disk.")
    parser.add_argument("--run-id", required=True, help="Explicit auditable run identifier.")
    parser.add_argument("--expected-count", type=int, default=83)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.run_id):
        raise ValueError("invalid_run_id")
    input_root = args.input.resolve()
    staging_root = args.staging_root.resolve()
    if input_root.drive.casefold() != staging_root.drive.casefold():
        raise ValueError("staging_root_must_share_corpus_drive")
    if staging_root == input_root or staging_root.is_relative_to(input_root):
        raise ValueError("staging_root_must_not_be_inside_corpus")
    entries = build_source_ledger(input_root, expected_count=args.expected_count)
    output_path = staging_root / args.run_id / "source_ledger.jsonl"
    result = write_source_ledger(entries, output_path)
    if result["entry_count"] != args.expected_count:
        raise RuntimeError("ledger_count_mismatch_after_write")
    return result


def main(argv: list[str] | None = None) -> int:
    result = run(build_parser().parse_args(argv))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

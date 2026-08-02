from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_pipeline.enterprise.acceptance_preflight import run_preflight


DEFAULT_RELEASE_ROOT = Path(
    "E:/智能运营分析项目/.runtime/rag/releases/RAG-R1"
).resolve()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight RAG-R1 acceptance evidence")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_RELEASE_ROOT / "candidate_corpus.json")
    parser.add_argument("--collection", type=Path, default=DEFAULT_RELEASE_ROOT / "candidate_collection_report.json")
    parser.add_argument("--ocr-gold", type=Path, default=PROJECT_ROOT / "tests/evaluation/rag_r1_ocr_gold.json")
    parser.add_argument("--retrieval-gold", type=Path, default=PROJECT_ROOT / "tests/evaluation/rag_r1_retrieval_gold.json")
    parser.add_argument("--ai-gold", type=Path, default=PROJECT_ROOT / "tests/evaluation/rag_r1_ai_gold.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_preflight(
            candidate_path=args.candidate.resolve(),
            collection_path=args.collection.resolve(),
            ocr_gold_path=args.ocr_gold.resolve(),
            retrieval_gold_path=args.retrieval_gold.resolve(),
            ai_gold_path=args.ai_gold.resolve(),
        )
    except Exception as exc:
        print(f"RAG-R1 acceptance preflight FAILED: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())


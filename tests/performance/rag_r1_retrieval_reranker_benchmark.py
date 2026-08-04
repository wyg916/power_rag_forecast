from __future__ import annotations

import argparse, json, math, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


from scripts import rag_r1_candidate_acceptance as acceptance

def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values); return round(ordered[max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))], 3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark the formal RAG-R1 reranker")
    for name in ("model-path", "corpus", "questions", "output"): parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--pairs", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument(
        "--runtime", choices=("torch_fp32",), default="torch_fp32"
    )
    parser.add_argument(
        "--runtime-profile",
        choices=(acceptance.R3_DEVELOPMENT_PROFILE,),
        required=True,
    )
    args = parser.parse_args(argv)
    acceptance._validate_r3_assets(
        questions_path=args.questions,
        corpus_path=args.corpus,
    )
    if args.model_path.resolve(strict=True) != acceptance.EXPECTED_RERANKER_ROOT:
        raise ValueError("benchmark_model_path_forbidden")
    if args.model_version != acceptance.EXPECTED_RERANKER_VERSION:
        raise ValueError("benchmark_model_version_invalid")
    if args.output.exists():
        raise ValueError("benchmark_output_exists")
    if (
        args.batch_size not in {4, 8}
        or args.max_length not in {64, 96, 128}
        or args.iterations < 20
    ):
        raise ValueError("benchmark_profile_invalid")

    os.environ["RAG_PROFILE"] = "enterprise"
    for key in ("TRANSFORMERS_OFFLINE", "HF_HUB_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"): os.environ[key] = "1"
    import torch
    from backend.app.services.rerank_service import BGETransformersReranker

    if args.threads not in {1, 2, 4, 6, 8} or not 1 <= args.pairs <= 16:
        raise ValueError("benchmark_profile_invalid")
    torch.set_num_threads(args.threads); torch.set_num_interop_threads(1)
    corpus = json.loads(args.corpus.read_text(encoding="utf-8")); questions = json.loads(args.questions.read_text(encoding="utf-8")).get("items", [])
    chunks = corpus.get("candidate_manifest", {}).get("chunks", []); contents = sorted((str(row.get("content") or "") for row in chunks if row.get("content")), key=len)
    if not questions or len(contents) < args.pairs: raise ValueError("benchmark_input_invalid")
    start, span = len(contents) // 2, len(contents) - 1 - len(contents) // 2
    divisor = max(1, args.pairs - 1)
    texts = [
        contents[start + span * index // divisor][:1800]
        for index in range(args.pairs)
    ]
    query = str(questions[0]["question"])
    reranker = BGETransformersReranker(
        str(args.model_path), "bge-reranker-v2-m3",
        batch_size=args.batch_size, max_length=args.max_length, runtime=args.runtime,
    )

    started = time.perf_counter(); reranker._load_model(); load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter(); reranker._score_pairs(query, texts); cold_ms = (time.perf_counter() - started) * 1000
    reranker._score_pairs(query, texts)
    def timed(): started = time.perf_counter(); reranker._score_pairs(query, texts); return (time.perf_counter() - started) * 1000
    warm = [timed() for _ in range(args.iterations)]

    report = {"schema_version": "rag-r1-reranker-benchmark/v1", "model": "bge-reranker-v2-m3",
        "model_version": args.model_version, "device": "cpu",
        "runtime_profile": args.runtime_profile,
        "runtime": reranker.runtime, "batch_size": reranker.batch_size,
        "max_length": reranker.max_length, "pairs": len(texts),
        "iterations": args.iterations, "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "load_ms": round(load_ms, 3), "cold_forward_ms": round(cold_ms, 3), "warm_max_ms": round(max(warm), 3)}
    report.update({f"warm_p{p}_ms": _percentile(warm, p / 100) for p in (50, 90, 95, 99)})
    args.output.parent.mkdir(parents=True, exist_ok=True); rendered = json.dumps(report, ensure_ascii=False, indent=2)
    args.output.write_text(rendered + "\n", encoding="utf-8"); print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

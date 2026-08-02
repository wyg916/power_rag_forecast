from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_PREFIX = "RAG_R1_MODEL_RESULT="
EXPECTED_MODELS = {
    "embedding": "BAAI/bge-large-zh-v1.5",
    "reranker": "BAAI/bge-reranker-v2-m3",
}


class ModelRuntimeSmokeError(RuntimeError):
    pass


def _offline_env() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "CUDA_VISIBLE_DEVICES": "",
        }
    )
    return environment


def _embedding_child(root: Path) -> dict[str, Any]:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    started = time.monotonic()
    model = SentenceTransformer(
        str(root), device="cpu", local_files_only=True, trust_remote_code=False
    )
    texts = (
        "电力现货市场峰谷价差如何计算",
        "计算高峰电价与低谷电价之差",
        "春天的花园适合散步",
    )
    vectors = model.encode(
        texts,
        batch_size=3,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    if vectors.shape != (3, 1024) or not np.isfinite(vectors).all():
        raise ModelRuntimeSmokeError("embedding_shape_or_finite_failed")
    norms = np.linalg.norm(vectors, axis=1)
    relevant = float(vectors[0] @ vectors[1])
    irrelevant = float(vectors[0] @ vectors[2])
    if not np.allclose(norms, 1.0, atol=1e-4):
        raise ModelRuntimeSmokeError("embedding_normalization_failed")
    if relevant <= irrelevant:
        raise ModelRuntimeSmokeError("embedding_semantic_order_failed")
    return {
        "role": "embedding",
        "status": "PASS",
        "shape": list(vectors.shape),
        "norms": [round(float(value), 6) for value in norms],
        "relevant_similarity": round(relevant, 6),
        "irrelevant_similarity": round(irrelevant, 6),
        "semantic_margin": round(relevant - irrelevant, 6),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "device": "cpu",
        "fallback_used": False,
        "network_calls": 0,
    }


def _reranker_child(root: Path) -> dict[str, Any]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(
        str(root), local_files_only=True, trust_remote_code=False
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        str(root),
        local_files_only=True,
        trust_remote_code=False,
        use_safetensors=True,
    )
    model.to("cpu")
    model.eval()
    pairs = (
        ("如何计算峰谷电价差", "峰谷价差等于高峰时段电价减去低谷时段电价。"),
        ("如何计算峰谷电价差", "春天的花园里鲜花盛开，适合户外散步。"),
    )
    encoded = tokenizer(
        list(pairs),
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt",
    )
    with torch.inference_mode():
        logits = model(**encoded, return_dict=True).logits.view(-1)
        scores = torch.sigmoid(logits).cpu().tolist()
    if len(scores) != 2 or not all(math.isfinite(float(value)) for value in scores):
        raise ModelRuntimeSmokeError("reranker_scores_invalid")
    if float(scores[0]) <= float(scores[1]):
        raise ModelRuntimeSmokeError("reranker_semantic_order_failed")
    return {
        "role": "reranker",
        "status": "PASS",
        "scores": [round(float(value), 6) for value in scores],
        "semantic_margin": round(float(scores[0] - scores[1]), 6),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "device": "cpu",
        "max_length_smoke": 512,
        "configured_max_length": 8192,
        "fallback_used": False,
        "network_calls": 0,
        "safe_weight_format": True,
    }


def _child(role: str, root: Path) -> int:
    if role not in EXPECTED_MODELS or root.name not in EXPECTED_MODELS[role]:
        raise ModelRuntimeSmokeError("model_child_root_rejected")
    result = _embedding_child(root) if role == "embedding" else _reranker_child(root)
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


def _parse_child(stdout: str, role: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1:
        raise ModelRuntimeSmokeError(f"model_child_result_missing:{role}")
    try:
        result = json.loads(lines[0][len(RESULT_PREFIX) :])
    except json.JSONDecodeError as exc:
        raise ModelRuntimeSmokeError(f"model_child_result_invalid:{role}") from exc
    if result.get("role") != role or result.get("status") != "PASS":
        raise ModelRuntimeSmokeError(f"model_child_contract_invalid:{role}")
    return result


def _admission_versions(path: Path) -> dict[str, str]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("weight_deserializations") != 0:
        raise ModelRuntimeSmokeError("model_admission_not_static_pass")
    return {
        role: str(report["models"][role]["version"])
        for role in ("embedding", "reranker")
    }


def run_smoke(
    embedding_root: Path,
    reranker_root: Path,
    admission: Path,
) -> dict[str, Any]:
    versions = _admission_versions(admission)
    results: dict[str, Any] = {}
    for role, root in (("embedding", embedding_root), ("reranker", reranker_root)):
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--child-role",
                role,
                "--child-root",
                str(root.resolve()),
            ],
            cwd=PROJECT_ROOT,
            env=_offline_env(),
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if completed.returncode:
            raise ModelRuntimeSmokeError(
                f"model_child_failed:{role}:{completed.returncode}:"
                f"{completed.stderr[-1200:]}"
            )
        results[role] = _parse_child(completed.stdout, role)
        results[role]["version"] = versions[role]
    return {
        "status": "PASS",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "models": results,
        "execution": "sequential_isolated_processes",
        "weight_deserializations": 2,
        "fallbacks_used": False,
        "network_calls": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline RAG-R1 model runtime smoke")
    parser.add_argument("--embedding-root", type=Path)
    parser.add_argument("--reranker-root", type=Path)
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child-role", choices=tuple(EXPECTED_MODELS))
    parser.add_argument("--child-root", type=Path)
    args = parser.parse_args(argv)
    if args.child_role:
        if args.child_root is None:
            raise SystemExit("child root required")
        return _child(args.child_role, args.child_root.resolve())
    if not all((args.embedding_root, args.reranker_root, args.admission, args.output)):
        raise SystemExit("embedding, reranker, admission and output are required")
    try:
        result = run_smoke(args.embedding_root, args.reranker_root, args.admission)
    except Exception as exc:
        print(f"RAG-R1 model runtime smoke FAILED: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

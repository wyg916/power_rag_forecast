from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPECTED_ROOT = Path("E:/智能运营分析项目").resolve()
LICENSE_RE = re.compile(r"^license:\s*([^\s]+)\s*$", re.IGNORECASE | re.MULTILINE)
MODEL_SPECS: dict[str, dict[str, Any]] = {
    "embedding": {
        "directory": "bge-large-zh-v1.5",
        "model": "BAAI/bge-large-zh-v1.5",
        "architecture": "BertModel",
        "model_type": "bert",
        "hidden_size": 1024,
        "layers": 24,
        "heads": 16,
        "max_length": 512,
        "license": "mit",
        "weight": "pytorch_model.bin",
        "required": {
            "config.json",
            "modules.json",
            "1_Pooling/config.json",
            "sentence_bert_config.json",
            "tokenizer.json",
            "vocab.txt",
            "README.md",
            "pytorch_model.bin",
        },
    },
    "reranker": {
        "directory": "bge-reranker-v2-m3",
        "model": "BAAI/bge-reranker-v2-m3",
        "architecture": "XLMRobertaForSequenceClassification",
        "model_type": "xlm-roberta",
        "hidden_size": 1024,
        "layers": 24,
        "heads": 16,
        "max_length": 8192,
        "license": "apache-2.0",
        "weight": "model.safetensors",
        "required": {
            "config.json",
            "tokenizer.json",
            "sentencepiece.bpe.model",
            "README.md",
            "model.safetensors",
        },
    },
}


class ModelAdmissionError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelAdmissionError(f"model_json_invalid:{path.name}") from exc
    if not isinstance(value, dict):
        raise ModelAdmissionError(f"model_json_not_object:{path.name}")
    return value


def _validate_root(root: Path, spec: Mapping[str, Any]) -> Path:
    resolved = root.resolve()
    if resolved.parent != EXPECTED_ROOT or resolved.name != spec["directory"]:
        raise ModelAdmissionError("model_root_rejected")
    if not resolved.is_dir():
        raise ModelAdmissionError("model_root_unavailable")
    return resolved


def _manifest(root: Path) -> tuple[list[dict[str, Any]], str]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ModelAdmissionError("model_files_missing")
    manifest = []
    for path in files:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ModelAdmissionError("model_file_escaped_root") from exc
        size = path.stat().st_size
        if size < 1:
            raise ModelAdmissionError(f"model_zero_byte_file:{relative}")
        with path.open("rb") as handle:
            prefix = handle.read(128)
        if prefix.startswith(b"version https://git-lfs.github.com/spec"):
            raise ModelAdmissionError(f"model_lfs_pointer_rejected:{relative}")
        manifest.append({"path": relative, "bytes": size, "sha256": _sha256(path)})
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return manifest, manifest_hash


def admit_model(role: str, root: Path) -> dict[str, Any]:
    if role not in MODEL_SPECS:
        raise ModelAdmissionError("model_role_invalid")
    spec = MODEL_SPECS[role]
    root = _validate_root(root, spec)
    actual_files = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    missing = sorted(spec["required"] - actual_files)
    if missing:
        raise ModelAdmissionError(f"model_required_files_missing:{missing}")

    config = _json(root / "config.json")
    architecture = tuple(config.get("architectures") or ())
    if architecture != (spec["architecture"],):
        raise ModelAdmissionError("model_architecture_mismatch")
    checks = {
        "model_type": config.get("model_type") == spec["model_type"],
        "hidden_size": config.get("hidden_size") == spec["hidden_size"],
        "layers": config.get("num_hidden_layers") == spec["layers"],
        "heads": config.get("num_attention_heads") == spec["heads"],
        "float32_declared": config.get("torch_dtype") == "float32",
    }
    if role == "embedding":
        sequence = _json(root / "sentence_bert_config.json")
        pooling = _json(root / "1_Pooling" / "config.json")
        modules = json.loads((root / "modules.json").read_text(encoding="utf-8"))
        checks.update(
            {
                "max_length": sequence.get("max_seq_length") == spec["max_length"],
                "pooling_dimension": pooling.get("word_embedding_dimension") == 1024,
                "cls_pooling": pooling.get("pooling_mode_cls_token") is True,
                "normalized_output": any(
                    item.get("type") == "sentence_transformers.models.Normalize"
                    for item in modules
                    if isinstance(item, dict)
                ),
            }
        )
    else:
        tokenizer = _json(root / "tokenizer_config.json")
        checks.update(
            {
                "max_length": tokenizer.get("model_max_length") == spec["max_length"],
                "classification_head": spec["architecture"].endswith(
                    "ForSequenceClassification"
                ),
                "safe_weight_format": str(spec["weight"]).endswith(".safetensors"),
            }
        )
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ModelAdmissionError(f"model_profile_failed:{failed}")

    readme = (root / "README.md").read_text(encoding="utf-8")
    license_match = LICENSE_RE.search(readme[:2048])
    license_id = license_match.group(1).lower() if license_match else ""
    if license_id != spec["license"]:
        raise ModelAdmissionError("model_license_mismatch")
    manifest, manifest_hash = _manifest(root)
    weight = next(item for item in manifest if item["path"] == spec["weight"])
    return {
        "status": "PASS",
        "role": role,
        "model": spec["model"],
        "directory_name": root.name,
        "license": license_id,
        "license_evidence": "README.md front matter",
        "license_evidence_sha256": _sha256(root / "README.md"),
        "architecture": spec["architecture"],
        "hidden_size": spec["hidden_size"],
        "embedding_dimension": 1024 if role == "embedding" else None,
        "max_length": spec["max_length"],
        "checks": checks,
        "weight": weight,
        "file_count": len(manifest),
        "total_bytes": sum(item["bytes"] for item in manifest),
        "manifest_sha256": manifest_hash,
        "version": f"sha256:{manifest_hash}",
        "files": manifest,
        "network_calls": 0,
        "weight_deserializations": 0,
    }


def create_report(embedding_root: Path, reranker_root: Path) -> dict[str, Any]:
    models = {
        "embedding": admit_model("embedding", embedding_root),
        "reranker": admit_model("reranker", reranker_root),
    }
    return {
        "status": "PASS",
        "admitted_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
        "embedding_dimension": 1024,
        "fallbacks_enabled": False,
        "network_calls": 0,
        "weight_deserializations": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static admission for RAG-R1 local models")
    parser.add_argument("--embedding-root", type=Path, required=True)
    parser.add_argument("--reranker-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = create_report(args.embedding_root, args.reranker_root)
    except Exception as exc:
        print(f"RAG-R1 model admission FAILED: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = {
        "status": report["status"],
        "embedding_version": report["models"]["embedding"]["version"],
        "reranker_version": report["models"]["reranker"]["version"],
        "weight_deserializations": 0,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

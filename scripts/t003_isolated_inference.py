from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

import joblib
import lightgbm
import numpy as np
import pandas as pd
import scipy
import sklearn
import threadpoolctl

from model_ops.result_hash import RESULT_VALUE_COLUMNS, result_data_hash
from model_ops.safe_model_contract import (
    build_artifact_manifest,
    build_feature_contract,
    candidate_identity,
    frame_hash,
    isolated_load_guards,
    load_verified_candidate,
    predict_candidate_components,
    prepare_frozen_24_input,
    sha256_file,
    validate_feature_batch,
)


THREAD_KEYS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "PYTHONHASHSEED",
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-timezone", default="America/New_York")
    return parser.parse_args()


def _load_input(
    path: Path,
    contract: dict,
    source_timezone: str,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    if path.suffix.lower() == ".csv":
        raw = pd.read_csv(path, encoding="utf-8-sig")
        names = [item["name"] for item in contract["features"]]
        if list(raw.columns) != ["timestamp", *names]:
            raise RuntimeError("FROZEN_INPUT_COLUMNS_MISMATCH")
        frame = raw[names]
        timestamps = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True)).tz_convert(contract["timezone"])
        return frame, timestamps
    extra_site = os.environ.get("T003_OPENPYXL_SITE_PACKAGES", "").strip()
    if extra_site:
        resolved = Path(extra_site).resolve(strict=True)
        if resolved.name != "site-packages" or ".venv" not in resolved.parts:
            raise RuntimeError("OPENPYXL_PATH_UNAUTHORIZED")
        sys.path.append(str(resolved))
    return prepare_frozen_24_input(
        path,
        path,
        contract,
        source_timezone=source_timezone,
    )


def _environment_hash() -> str:
    payload = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
        "lightgbm": lightgbm.__version__,
        "threadpoolctl": threadpoolctl.__version__,
        "threads": {name: os.environ.get(name) for name in THREAD_KEYS},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    args = _args()
    artifact = Path(args.artifact).resolve(strict=True)
    input_path = Path(args.input).resolve(strict=True)
    output = Path(args.output).resolve(strict=True)
    before = build_artifact_manifest(artifact)
    contract = build_feature_contract(artifact)
    contract["artifact_id"] = before["artifact_id"]
    frame, timestamps = _load_input(input_path, contract, args.source_timezone)
    identity = {
        "artifact_id": before["artifact_id"],
        "feature_version": before["feature_version"],
        "schema_hash": before["schema_hash"],
    }
    validate_feature_batch(frame, timestamps, contract, identity)
    with isolated_load_guards(output) as runtime_events:
        candidate = load_verified_candidate(
            artifact,
            before,
            authorized_dir=artifact,
            output_dir=output,
        )
        predictions = predict_candidate_components(
            candidate,
            frame,
            timestamps,
            candidate_identity(candidate),
        )
    values = predictions[list(RESULT_VALUE_COLUMNS)]
    data_hash = result_data_hash(timestamps, values)
    predictions.to_csv(output / "prediction_batch.csv", index=False, encoding="utf-8-sig")
    np.save(
        output / "prediction_values.npy",
        np.ascontiguousarray(values.to_numpy(dtype="float64"), dtype="<f8"),
        allow_pickle=False,
    )
    (output / "prediction_timestamps.json").write_text(
        json.dumps([item.isoformat() for item in timestamps], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    after = build_artifact_manifest(artifact)
    if before["artifact_hash"] != after["artifact_hash"]:
        raise RuntimeError("ARTIFACT_HASH_CHANGED")
    report = {
        "status": "PASS",
        "artifact_id": before["artifact_id"],
        "model_version": before["model_version"],
        "artifact_hash": before["artifact_hash"],
        "feature_version": before["feature_version"],
        "schema_hash": before["schema_hash"],
        "input_path": str(input_path),
        "input_file_hash": sha256_file(input_path),
        "input_data_hash": frame_hash(frame),
        "input_rows": len(frame),
        "input_features": len(frame.columns),
        "input_start_at": timestamps[0].isoformat(),
        "input_end_at": timestamps[-1].isoformat(),
        "forecast_start_at": timestamps[0].isoformat(),
        "forecast_end_at": timestamps[-1].isoformat(),
        "environment_hash": _environment_hash(),
        "result_data_hash": data_hash,
        "binary_values_hash": sha256_file(output / "prediction_values.npy"),
        "timestamps_hash": sha256_file(output / "prediction_timestamps.json"),
        "record_count": len(predictions),
        "artifact_hash_equal": True,
        "network_events": runtime_events["network"],
        "subprocess_events": runtime_events["subprocess"],
        "outside_write_events": runtime_events["writes"],
        "database_access": False,
        "formal_prediction": False,
        "active_promotion": False,
    }
    (output / "prediction_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

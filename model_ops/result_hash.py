from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

import numpy as np
import pandas as pd


RESULT_VALUE_COLUMNS = (
    "base_prediction",
    "peak_prediction",
    "classifier_prediction",
    "spike_probability",
    "p90_prediction",
    "blend_weight",
    "predicted_price",
)
MANIFEST_HASH_FIELDS = (
    "artifact_id",
    "model_version",
    "feature_version",
    "schema_hash",
    "input_hash",
    "environment_hash",
    "result_data_hash",
)


def canonical_float64_bytes(values: Any) -> bytes:
    array = np.asarray(values)
    if array.ndim == 0:
        array = array.reshape(1)
    numeric = np.asarray(array, dtype="float64")
    if not np.isfinite(numeric).all():
        raise ValueError("RESULT_NONFINITE")
    numeric = np.where(numeric == 0.0, 0.0, numeric)
    little_endian = np.ascontiguousarray(numeric, dtype="<f8")
    return little_endian.tobytes(order="C")


def canonical_array_hash(values: Any) -> str:
    array = np.asarray(values)
    header = json.dumps(
        {"shape": list(array.shape), "canonical_dtype": "<f8"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(header + b"\n" + canonical_float64_bytes(array)).hexdigest()


def canonical_timestamps(timestamps: Any) -> list[str]:
    index = pd.DatetimeIndex(timestamps)
    if index.tz is None:
        raise ValueError("RESULT_TIMEZONE_MISSING")
    utc = index.tz_convert("UTC")
    return [item.strftime("%Y-%m-%dT%H:%M:%S.%fZ") for item in utc]


def result_data_hash(
    timestamps: Any,
    values: pd.DataFrame,
    *,
    columns: Sequence[str] = RESULT_VALUE_COLUMNS,
) -> str:
    ordered = list(columns)
    missing = [name for name in ordered if name not in values.columns]
    if missing:
        raise ValueError(f"RESULT_COLUMNS_MISSING:{missing}")
    if len(values) != len(pd.DatetimeIndex(timestamps)):
        raise ValueError("RESULT_ROW_COUNT_MISMATCH")
    matrix = values[ordered].to_numpy(dtype="float64", copy=True)
    time_values = canonical_timestamps(timestamps)
    header = json.dumps(
        {
            "protocol": "t002.result-data.v1",
            "rows": int(matrix.shape[0]),
            "columns": ordered,
            "timestamps_utc": time_values,
            "numeric_dtype": "<f8",
            "order": "C",
            "negative_zero": "normalized_to_positive_zero",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(header + b"\n" + canonical_float64_bytes(matrix)).hexdigest()


def result_manifest_hash(payload: dict[str, Any]) -> str:
    missing = [name for name in MANIFEST_HASH_FIELDS if name not in payload]
    if missing:
        raise ValueError(f"RESULT_MANIFEST_FIELDS_MISSING:{missing}")
    stable = {name: payload[name] for name in MANIFEST_HASH_FIELDS}
    encoded = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compare_arrays(left: Any, right: Any) -> dict[str, Any]:
    a_raw = np.asarray(left)
    b_raw = np.asarray(right)
    result: dict[str, Any] = {
        "left_shape": list(a_raw.shape),
        "right_shape": list(b_raw.shape),
        "left_dtype": str(a_raw.dtype),
        "right_dtype": str(b_raw.dtype),
    }
    if a_raw.shape != b_raw.shape:
        return {**result, "shape_equal": False, "equal": False}
    a = np.asarray(a_raw, dtype="float64")
    b = np.asarray(b_raw, dtype="float64")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("RESULT_NONFINITE")
    delta = np.abs(a - b)
    scale = np.maximum(np.maximum(np.abs(a), np.abs(b)), np.finfo("float64").tiny)
    relative = delta / scale
    numeric_mask = a != b
    a_bits = np.where(a == 0.0, 0.0, a).astype("<f8", copy=False).view("<u8")
    b_bits = np.where(b == 0.0, 0.0, b).astype("<f8", copy=False).view("<u8")
    bitwise_mask = a_bits != b_bits
    first = np.flatnonzero(bitwise_mask.reshape(-1))
    return {
        **result,
        "shape_equal": True,
        "equal": not bool(bitwise_mask.any()),
        "left_min": float(a.min()),
        "left_max": float(a.max()),
        "left_mean": float(a.mean()),
        "right_min": float(b.min()),
        "right_max": float(b.max()),
        "right_mean": float(b.mean()),
        "left_array_sha256": canonical_array_hash(a),
        "right_array_sha256": canonical_array_hash(b),
        "max_absolute_difference": float(delta.max(initial=0.0)),
        "max_relative_difference": float(relative.max(initial=0.0)),
        "numeric_mismatch_count": int(numeric_mask.sum()),
        "bitwise_mismatch_count": int(bitwise_mask.sum()),
        "first_mismatch_flat_index": int(first[0]) if first.size else None,
    }

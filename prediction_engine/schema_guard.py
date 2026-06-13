from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def load_feature_schema(path_or_dir: str | Path) -> dict[str, Any]:
    path = Path(path_or_dir)
    if path.is_dir():
        path = path / "feature_schema.json"
    if not path.exists():
        raise FileNotFoundError(f"feature schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def feature_names_from_schema(feature_schema: dict[str, Any]) -> list[str]:
    return [str(item["name"]) for item in feature_schema.get("features", [])]


def _dtype_compatible(expected_dtype: str, actual_dtype: str) -> bool:
    expected = expected_dtype.lower()
    actual = actual_dtype.lower()
    if any(token in expected for token in ["float", "int", "number"]):
        return any(token in actual for token in ["float", "int"])
    if "bool" in expected:
        return "bool" in actual or "int" in actual
    return True


def validate_feature_frame_schema(
    frame: pd.DataFrame,
    feature_schema: dict[str, Any],
    *,
    require_order: bool = False,
    allow_extra: bool = True,
) -> dict[str, Any]:
    expected_features = feature_names_from_schema(feature_schema)
    expected_set = set(expected_features)
    frame_columns = list(frame.columns)
    frame_set = set(frame_columns)
    missing = [column for column in expected_features if column not in frame_set]
    extra = [column for column in frame_columns if column not in expected_set]
    present_order = [column for column in frame_columns if column in expected_set]
    order_ok = present_order == expected_features if require_order else True

    dtype_mismatches = []
    feature_meta = {str(item["name"]): item for item in feature_schema.get("features", [])}
    for column in expected_features:
        if column not in frame.columns:
            continue
        expected_dtype = str(feature_meta.get(column, {}).get("dtype", ""))
        actual_dtype = str(frame[column].dtype)
        if expected_dtype and not _dtype_compatible(expected_dtype, actual_dtype):
            dtype_mismatches.append({"name": column, "expected_dtype": expected_dtype, "actual_dtype": actual_dtype})

    ok = not missing and not dtype_mismatches and order_ok and (allow_extra or not extra)
    return {
        "ok": ok,
        "expected_feature_count": len(expected_features),
        "actual_column_count": len(frame_columns),
        "missing_features": missing,
        "extra_columns": extra,
        "order_ok": order_ok,
        "dtype_mismatches": dtype_mismatches,
        "ordered_feature_columns": expected_features,
    }


def select_schema_features(frame: pd.DataFrame, feature_schema: dict[str, Any], *, require_order: bool = False) -> pd.DataFrame:
    check = validate_feature_frame_schema(frame, feature_schema, require_order=require_order, allow_extra=True)
    if not check["ok"]:
        raise ValueError(f"feature frame does not match feature_schema.json: {check}")
    return frame[check["ordered_feature_columns"]].copy()

from __future__ import annotations

import builtins
import copy
import hashlib
import importlib.metadata
import io
import json
import os
import re
import socket
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np
import pandas as pd


MODEL_FILES = (
    "base_model.joblib",
    "peak_model.joblib",
    "spike_classifier.joblib",
    "p90_model.joblib",
)
TEXT_FILES = (
    "feature_cols.json",
    "input_schema.json",
    "manifest.json",
    "metrics.json",
    "model_card.md",
    "thresholds.json",
    "training_config.json",
)
REQUIRED_FILES = MODEL_FILES[:3] + TEXT_FILES
ALLOWED_EXTENSIONS = {".joblib", ".json", ".md"}
PLACEHOLDER_FEATURES = (
    "hour_bias_mean",
    "scenario_mae",
    "historical_under_predict_rate",
)
PEAK_HOURS = frozenset({6, 7, 8, 9, 10, 11, 18, 19, 20, 21})
TARGET_COLUMNS = {"da_price"}
FUTURE_RESULT_COLUMNS = {
    "predicted_price",
    "prediction",
    "forecast_result",
    "raw_predicted_price",
    "corrected_predicted_price",
    "spike_risk_prob",
}
EXPECTED_MODEL_TYPES = {
    "base_model.joblib": {("sklearn.pipeline", "Pipeline")},
    "peak_model.joblib": {("sklearn.ensemble._hist_gradient_boosting.gradient_boosting", "HistGradientBoostingRegressor")},
    "spike_classifier.joblib": {("sklearn.ensemble._forest", "RandomForestClassifier")},
    "p90_model.joblib": {("lightgbm.sklearn", "LGBMRegressor")},
}


class ModelContractError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class LoadedCandidate:
    artifact_dir: Path
    manifest: dict[str, Any]
    feature_contract: dict[str, Any]
    models: dict[str, Any]
    metadata: dict[str, Any]
    guard_events: dict[str, list[str]]


def _fail(code: str, message: str) -> None:
    raise ModelContractError(code, message)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _fail("MANIFEST_INVALID", f"无法读取 JSON {path.name}: {exc}")


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _embedded_sklearn_versions(artifact_dir: Path) -> dict[str, Any]:
    detected: dict[str, str] = {}
    unknown: list[str] = []
    pattern = re.compile(rb"_sklearn_version.{0,16}?([0-9]+\.[0-9]+\.[0-9]+)", re.DOTALL)
    for name in MODEL_FILES:
        path = artifact_dir / name
        if not path.exists():
            continue
        match = pattern.search(path.read_bytes())
        if match is None:
            unknown.append(name)
        else:
            detected[name] = match.group(1).decode("ascii")
    return {"detected": detected, "unknown": unknown, "source": "embedded _sklearn_version metadata"}


def resolve_authorized_artifact_dir(path: str | Path, authorized_dir: str | Path | None = None) -> Path:
    candidate = Path(path).resolve(strict=True)
    if not candidate.is_dir():
        _fail("ARTIFACT_PATH_INVALID", "artifact 路径不是目录")
    if authorized_dir is not None and candidate != Path(authorized_dir).resolve(strict=True):
        _fail("ARTIFACT_PATH_UNAUTHORIZED", "artifact 路径不等于本次授权目录")
    return candidate


def _validate_artifact_layout(artifact_dir: Path) -> list[Path]:
    files = sorted((item for item in artifact_dir.iterdir() if item.is_file()), key=lambda item: item.name)
    if any(item.is_symlink() for item in files):
        _fail("ARTIFACT_SYMLINK", "artifact 不允许符号链接")
    names = {item.name for item in files}
    missing = [name for name in REQUIRED_FILES if name not in names]
    if missing:
        _fail("ARTIFACT_FILE_MISSING", f"缺失文件：{missing}")
    unknown_extensions = [item.name for item in files if item.suffix.lower() not in ALLOWED_EXTENSIONS]
    if unknown_extensions:
        _fail("ARTIFACT_EXTENSION_DENIED", f"不允许的扩展名：{unknown_extensions}")
    source_manifest = _read_json(artifact_dir / "manifest.json")
    declared = {str(name) for name in source_manifest.get("files") or []}
    if declared | {"manifest.json"} != names:
        _fail("ARTIFACT_FILE_SET_MISMATCH", "manifest 文件清单与目录实际文件不一致")
    return files


def build_feature_contract(artifact_dir: str | Path, *, timezone: str = "America/New_York") -> dict[str, Any]:
    path = resolve_authorized_artifact_dir(artifact_dir)
    feature_cols = _read_json(path / "feature_cols.json")
    source_schema = _read_json(path / "input_schema.json")
    training = _read_json(path / "training_config.json")
    metrics = _read_json(path / "metrics.json")
    source_manifest = _read_json(path / "manifest.json")
    if not isinstance(feature_cols, list) or len(feature_cols) != 170 or len(set(feature_cols)) != 170:
        _fail("FEATURE_COUNT_MISMATCH", "feature_cols 必须包含 170 个唯一特征")
    schema_features = [str(item.get("name")) for item in source_schema.get("features") or []]
    if schema_features != feature_cols:
        _fail("SOURCE_SCHEMA_ORDER_MISMATCH", "input_schema 与 feature_cols 名称或顺序不一致")
    model_versions = {
        str(source_manifest.get("model_version") or ""),
        str(training.get("model_version") or ""),
        str(metrics.get("model_version") or ""),
        path.name,
    }
    if len(model_versions) != 1:
        _fail("MODEL_VERSION_MISMATCH", f"model_version 不一致：{sorted(model_versions)}")
    feature_version = str(training.get("feature_version") or source_schema.get("feature_version") or "")
    if not feature_version or feature_version != str(source_schema.get("feature_version") or ""):
        _fail("FEATURE_VERSION_MISMATCH", "training_config 与 input_schema 的 feature_version 不一致")
    target_name = str(training.get("target_col") or source_schema.get("target_col") or "")
    if target_name != "da_price":
        _fail("TARGET_MISMATCH", f"不支持的 target：{target_name}")
    features: list[dict[str, Any]] = []
    for name in feature_cols:
        item: dict[str, Any] = {
            "name": name,
            "dtype": "float64",
            "nullable": False,
            "default_allowed": False,
        }
        if name in PLACEHOLDER_FEATURES:
            item.update(
                {
                    "behavior": "deterministic_placeholder",
                    "allowed_values": [0.0],
                    "business_meaning": "v4_fix1 训练与推理 schema 对齐的确定性零占位；不代表动态历史误差",
                }
            )
        features.append(item)
    contract: dict[str, Any] = {
        "contract_version": "t002.strict.v1",
        "model_version": path.name,
        "feature_version": feature_version,
        "domain": "price",
        "target_name": target_name,
        "feature_count": len(features),
        "timestamp_transport": "separate_datetime_index",
        "timezone": timezone,
        "required_rows": 24,
        "horizon_hours": 24,
        "allow_negative_prediction": True,
        "features": features,
        "schema_hash_method": "sha256(canonical-json-without-schema_hash; UTF-8; sorted keys; compact separators)",
    }
    contract["schema_hash"] = _canonical_hash(contract)
    return contract


def build_artifact_manifest(artifact_dir: str | Path, *, timezone: str = "America/New_York") -> dict[str, Any]:
    path = resolve_authorized_artifact_dir(artifact_dir)
    files = _validate_artifact_layout(path)
    contract = build_feature_contract(path, timezone=timezone)
    hashes = {item.name: sha256_file(item) for item in files}
    artifact_hash = _canonical_hash([{"name": name, "sha256": hashes[name]} for name in sorted(hashes)])
    training = _read_json(path / "training_config.json")
    metrics = _read_json(path / "metrics.json")
    source_manifest = _read_json(path / "manifest.json")
    return {
        "manifest_version": "t002.artifact.v1",
        "artifact_id": f"artifact_{artifact_hash[:24]}",
        "artifact_hash": artifact_hash,
        "artifact_path": str(path),
        "model_version": contract["model_version"],
        "feature_version": contract["feature_version"],
        "domain": contract["domain"],
        "target_name": contract["target_name"],
        "feature_count": contract["feature_count"],
        "schema_hash": contract["schema_hash"],
        "created_at": source_manifest.get("created_at"),
        "source_type": "trained_artifact",
        "status": "candidate",
        "artifact_files": [
            {"name": item.name, "size_bytes": item.stat().st_size, "sha256": hashes[item.name]}
            for item in files
        ],
        "runtime": {
            "python": sys.version.split()[0],
            "pandas": _package_version("pandas"),
            "scikit_learn": _package_version("scikit-learn"),
            "joblib": _package_version("joblib"),
            "numpy": _package_version("numpy"),
            "scipy": _package_version("scipy"),
            "training_runtime_versions": _embedded_sklearn_versions(path),
        },
        "model_components": {
            "base": training.get("base_model_name") or metrics.get("base_model_name"),
            "peak": training.get("peak_model_name") or metrics.get("peak_model_name"),
            "classifier": training.get("classifier_name") or metrics.get("classifier_name"),
            "p90": "lightgbm.sklearn.LGBMRegressor" if (path / "p90_model.joblib").exists() else None,
        },
        "input_schema_file": "input_schema.json",
        "metrics_file": "metrics.json",
    }


def verify_artifact_manifest(
    artifact_dir: str | Path,
    expected: dict[str, Any],
    *,
    authorized_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_authorized_artifact_dir(artifact_dir, authorized_dir)
    actual = build_artifact_manifest(path)
    for key, code in (
        ("artifact_id", "ARTIFACT_ID_MISMATCH"),
        ("artifact_hash", "ARTIFACT_HASH_MISMATCH"),
        ("model_version", "MODEL_VERSION_MISMATCH"),
        ("feature_version", "FEATURE_VERSION_MISMATCH"),
        ("schema_hash", "SCHEMA_HASH_MISMATCH"),
    ):
        if expected.get(key) != actual.get(key):
            _fail(code, f"{key} 与已冻结 manifest 不一致")
    expected_files = {item["name"]: item["sha256"] for item in expected.get("artifact_files") or []}
    actual_files = {item["name"]: item["sha256"] for item in actual.get("artifact_files") or []}
    if expected_files != actual_files:
        _fail("ARTIFACT_FILE_HASH_MISMATCH", "artifact 文件 hash 清单不一致")
    return actual


def _ensure_authorized_input(path: str | Path, authorized_input: str | Path) -> Path:
    resolved = Path(path).resolve(strict=True)
    if resolved != Path(authorized_input).resolve(strict=True):
        _fail("INPUT_PATH_UNAUTHORIZED", "输入路径不等于冻结授权文件")
    return resolved


def prepare_frozen_24_input(
    source_path: str | Path,
    authorized_input: str | Path,
    feature_contract: dict[str, Any],
    *,
    source_timezone: str,
) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    path = _ensure_authorized_input(source_path, authorized_input)
    frame = pd.read_excel(path, engine="openpyxl")
    expected = [item["name"] for item in feature_contract["features"]]
    if list(frame.columns) != ["datetime", *expected]:
        _fail("SOURCE_INPUT_COLUMNS", "冻结源文件必须严格为 datetime + 170 特征顺序")
    if len(frame) != feature_contract["required_rows"]:
        _fail("ROW_COUNT_MISMATCH", "冻结源文件必须恰好 24 行")
    if not all(pd.api.types.is_numeric_dtype(frame[name].dtype) for name in expected):
        _fail("SOURCE_DTYPE_MISMATCH", "冻结源特征必须全部已是数值 dtype")
    timestamps = pd.DatetimeIndex(frame["datetime"])
    if timestamps.tz is not None:
        _fail("SOURCE_TIMEZONE_UNEXPECTED", "旧冻结源预期为 naive；禁止重复时区转换")
    try:
        timestamps = timestamps.tz_localize(source_timezone, ambiguous="raise", nonexistent="raise")
    except Exception as exc:
        _fail("TIMEZONE_LOCALIZE_FAILED", str(exc))
    features = frame[expected].astype("float64", copy=True)
    return features, timestamps


def validate_feature_batch(
    frame: pd.DataFrame,
    timestamps: pd.DatetimeIndex | pd.Series,
    feature_contract: dict[str, Any],
    identity: dict[str, Any],
) -> None:
    for key, code in (
        ("artifact_id", "ARTIFACT_ID_MISMATCH"),
        ("feature_version", "FEATURE_VERSION_MISMATCH"),
        ("schema_hash", "SCHEMA_HASH_MISMATCH"),
    ):
        expected_value = feature_contract.get(key)
        actual_value = identity.get(key)
        if expected_value != actual_value:
            _fail(code, f"{key} 不一致")
    required_rows = int(feature_contract["required_rows"])
    if len(frame) != required_rows:
        _fail("ROW_COUNT_MISMATCH", f"要求 {required_rows} 行，实际 {len(frame)} 行")
    expected = [item["name"] for item in feature_contract["features"]]
    columns = [str(name) for name in frame.columns]
    lowered = {name.lower() for name in columns}
    if lowered & TARGET_COLUMNS:
        _fail("TARGET_COLUMN_FORBIDDEN", "目标字段不得进入模型输入")
    if lowered & FUTURE_RESULT_COLUMNS:
        _fail("FUTURE_RESULT_COLUMN_FORBIDDEN", "预测结果/未来结果字段不得进入模型输入")
    missing = [name for name in expected if name not in columns]
    extra = [name for name in columns if name not in set(expected)]
    if missing:
        _fail("MISSING_FEATURE", f"缺失特征：{missing[:10]}")
    if extra:
        _fail("EXTRA_FEATURE", f"额外特征：{extra[:10]}")
    if columns != expected:
        _fail("FEATURE_ORDER_MISMATCH", "特征顺序与 schema 不一致")
    if len({name.lower() for name in columns}) != len(columns):
        _fail("FEATURE_ALIAS_COLLISION", "存在大小写或别名冲突")
    for name in expected:
        series = frame[name]
        if pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype):
            parsed = pd.to_numeric(series, errors="coerce")
            if bool(parsed.isna().any() & series.notna().any()):
                _fail("ILLEGAL_STRING", f"{name} 包含非法字符串")
        if str(series.dtype) != "float64":
            _fail("DTYPE_MISMATCH", f"{name} 要求 float64，实际 {series.dtype}")
    values = frame.to_numpy(dtype="float64", copy=False)
    if np.isnan(values).any():
        _fail("NAN_FORBIDDEN", "必填特征包含 NaN")
    if not np.isfinite(values).all():
        _fail("INF_FORBIDDEN", "特征包含 Inf 或 -Inf")
    for name in PLACEHOLDER_FEATURES:
        if not np.equal(frame[name].to_numpy(), 0.0).all():
            _fail("PLACEHOLDER_VALUE_MISMATCH", f"{name} 必须为已声明的确定性 0 占位")
    if isinstance(timestamps, pd.Series):
        if not pd.api.types.is_datetime64_any_dtype(timestamps.dtype):
            _fail("TIMESTAMP_DTYPE_MISMATCH", "时间字段必须为 datetime dtype")
        index = pd.DatetimeIndex(timestamps)
    elif isinstance(timestamps, pd.DatetimeIndex):
        index = timestamps
    else:
        _fail("TIMESTAMP_DTYPE_MISMATCH", "时间字段必须为 DatetimeIndex 或 datetime Series")
    if len(index) != required_rows:
        _fail("TIMESTAMP_ROW_MISMATCH", "时间数量与 24 行特征不一致")
    if index.tz is None:
        _fail("TIMEZONE_MISSING", "时间字段缺少显式时区")
    if str(index.tz) != str(feature_contract["timezone"]):
        _fail("TIMEZONE_MISMATCH", f"要求 {feature_contract['timezone']}，实际 {index.tz}")
    if index.has_duplicates:
        _fail("DUPLICATE_HOUR", "时间字段存在重复小时")
    diffs = index.to_series(index=range(len(index))).diff().dropna()
    if not bool((diffs == pd.Timedelta(hours=1)).all()):
        _fail("NON_CONTIGUOUS_HOURS", "时间必须按一小时连续递增")


@contextmanager
def isolated_load_guards(output_dir: str | Path | None = None) -> Iterator[dict[str, list[str]]]:
    output = Path(output_dir).resolve() if output_dir is not None else None
    events: dict[str, list[str]] = {"network": [], "subprocess": [], "writes": [], "imports": []}
    original_import = builtins.__import__
    original_open = builtins.open
    original_io_open = io.open
    original_socket = socket.socket
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    subprocess_names = ("Popen", "run", "call", "check_call", "check_output")
    original_subprocess = {name: getattr(subprocess, name) for name in subprocess_names}
    original_system = os.system
    original_popen = os.popen
    original_startfile = getattr(os, "startfile", None)

    allowed_roots = set(sys.stdlib_module_names) | {
        "numpy",
        "scipy",
        "sklearn",
        "joblib",
        "threadpoolctl",
        "packaging",
        "pandas",
        "lightgbm",
    }

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = str(name).split(".", 1)[0]
        if level == 0 and root and root not in allowed_roots and root not in sys.modules:
            events["imports"].append(str(name))
            _fail("UNKNOWN_IMPORT_BLOCKED", f"反序列化尝试导入未知模块：{name}")
        return original_import(name, globals, locals, fromlist, level)

    def blocked_network(*args, **kwargs):
        events["network"].append("blocked")
        _fail("NETWORK_ACCESS_BLOCKED", "安全加载期间禁止网络访问")

    def blocked_subprocess(*args, **kwargs):
        events["subprocess"].append("blocked")
        _fail("SUBPROCESS_BLOCKED", "安全加载期间禁止外部命令")

    def guarded_open(file, mode="r", *args, **kwargs):
        write_mode = any(flag in str(mode) for flag in ("w", "a", "x", "+"))
        if write_mode and not isinstance(file, int):
            target = Path(file).resolve()
            if output is None or (target != output and output not in target.parents):
                events["writes"].append(str(target))
                _fail("FILE_WRITE_BLOCKED", f"安全加载期间禁止写入：{target}")
            events["writes"].append(str(target))
        return original_open(file, mode, *args, **kwargs)

    def guarded_io_open(file, mode="r", *args, **kwargs):
        write_mode = any(flag in str(mode) for flag in ("w", "a", "x", "+"))
        if write_mode and not isinstance(file, int):
            target = Path(file).resolve()
            if output is None or (target != output and output not in target.parents):
                events["writes"].append(str(target))
                _fail("FILE_WRITE_BLOCKED", f"安全加载期间禁止写入：{target}")
            events["writes"].append(str(target))
        return original_io_open(file, mode, *args, **kwargs)

    try:
        builtins.__import__ = guarded_import
        builtins.open = guarded_open
        io.open = guarded_io_open
        socket.socket = blocked_network  # type: ignore[assignment]
        socket.create_connection = blocked_network
        socket.getaddrinfo = blocked_network
        for name in subprocess_names:
            setattr(subprocess, name, blocked_subprocess)
        os.system = blocked_subprocess  # type: ignore[assignment]
        os.popen = blocked_subprocess  # type: ignore[assignment]
        if original_startfile is not None:
            os.startfile = blocked_subprocess  # type: ignore[attr-defined]
        yield events
    finally:
        builtins.__import__ = original_import
        builtins.open = original_open
        io.open = original_io_open
        socket.socket = original_socket
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo
        for name, value in original_subprocess.items():
            setattr(subprocess, name, value)
        os.system = original_system
        os.popen = original_popen
        if original_startfile is not None:
            os.startfile = original_startfile  # type: ignore[attr-defined]


def load_verified_candidate(
    artifact_dir: str | Path,
    expected_manifest: dict[str, Any],
    *,
    authorized_dir: str | Path,
    output_dir: str | Path | None = None,
) -> LoadedCandidate:
    path = resolve_authorized_artifact_dir(artifact_dir, authorized_dir)
    before = verify_artifact_manifest(path, expected_manifest, authorized_dir=authorized_dir)
    detected_versions = set(
        before.get("runtime", {}).get("training_runtime_versions", {}).get("detected", {}).values()
    )
    runtime_sklearn = before.get("runtime", {}).get("scikit_learn")
    if detected_versions and detected_versions != {runtime_sklearn}:
        _fail(
            "SKLEARN_VERSION_INCOMPATIBLE",
            f"artifact sklearn={sorted(detected_versions)}, runtime sklearn={runtime_sklearn}",
        )
    contract = build_feature_contract(path)
    contract["artifact_id"] = before["artifact_id"]
    training = _read_json(path / "training_config.json")
    metrics = _read_json(path / "metrics.json")
    thresholds = _read_json(path / "thresholds.json")
    # Bootstrap the trusted loader and its installed runtime dependencies before
    # enforcing the deserialization-time import allowlist. Artifact-triggered
    # imports remain guarded below.
    import joblib
    from lightgbm import LGBMRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestClassifier
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline

    _trusted_model_types = (Pipeline, Ridge, HistGradientBoostingRegressor, RandomForestClassifier, LGBMRegressor)

    with isolated_load_guards(output_dir) as guard_events:
        models = {name: joblib.load(path / name) for name in MODEL_FILES if (path / name).exists()}
    feature_names = [item["name"] for item in contract["features"]]
    interfaces: dict[str, Any] = {}
    for filename, model in models.items():
        actual_type = (model.__class__.__module__, model.__class__.__name__)
        if actual_type not in EXPECTED_MODEL_TYPES[filename]:
            _fail("MODEL_TYPE_UNEXPECTED", f"{filename} 类型异常：{actual_type}")
        if not callable(getattr(model, "predict", None)):
            _fail("MODEL_INTERFACE_MISSING", f"{filename} 缺少 predict")
        if filename == "spike_classifier.joblib" and not callable(getattr(model, "predict_proba", None)):
            _fail("MODEL_INTERFACE_MISSING", "spike_classifier 缺少 predict_proba")
        n_features = int(getattr(model, "n_features_in_", -1))
        if n_features != len(feature_names):
            _fail("MODEL_INPUT_DIMENSION_MISMATCH", f"{filename} n_features_in_={n_features}")
        names_in = getattr(model, "feature_names_in_", None)
        if names_in is not None and list(map(str, names_in)) != feature_names:
            _fail("MODEL_FEATURE_NAMES_MISMATCH", f"{filename} feature_names_in_ 不一致")
        interfaces[filename] = {
            "module": actual_type[0],
            "class": actual_type[1],
            "n_features_in": n_features,
            "predict": True,
            "predict_proba": callable(getattr(model, "predict_proba", None)),
            "feature_names_in_present": names_in is not None,
        }
        if filename == "spike_classifier.joblib":
            interfaces[filename]["artifact_n_jobs"] = getattr(model, "n_jobs", None)
            interfaces[filename]["validated_prediction_n_jobs"] = 1
    after = verify_artifact_manifest(path, before, authorized_dir=authorized_dir)
    if before["artifact_hash"] != after["artifact_hash"]:
        _fail("ARTIFACT_HASH_CHANGED_DURING_LOAD", "加载前后 artifact hash 变化")
    return LoadedCandidate(
        artifact_dir=path,
        manifest=after,
        feature_contract=contract,
        models=models,
        metadata={"training_config": training, "metrics": metrics, "thresholds": thresholds, "interfaces": interfaces},
        guard_events=guard_events,
    )


def candidate_identity(candidate: LoadedCandidate) -> dict[str, Any]:
    return {
        "artifact_id": candidate.manifest["artifact_id"],
        "feature_version": candidate.manifest["feature_version"],
        "schema_hash": candidate.manifest["schema_hash"],
    }


def _blend_predictions(
    base_prediction: np.ndarray,
    peak_prediction: np.ndarray,
    risk_probability: np.ndarray,
    peak_hour_flag: np.ndarray,
    *,
    alpha: float,
    peak_floor: float,
    load_high_flag: np.ndarray,
    error_high_flag: np.ndarray,
    spike_threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    risk = np.clip(np.asarray(risk_probability, dtype="float64"), 0.0, 1.0)
    peak_hour = np.asarray(peak_hour_flag, dtype="float64")
    load_high = np.asarray(load_high_flag, dtype="float64")
    error_high = np.asarray(error_high_flag, dtype="float64")
    dynamic_alpha = (
        float(alpha)
        + 0.12 * peak_hour
        + 0.18 * (risk >= float(spike_threshold)).astype("float64")
        + 0.10 * load_high
        + 0.08 * error_high
    )
    dynamic_alpha = np.maximum(dynamic_alpha, float(peak_floor) * peak_hour)
    dynamic_alpha = np.clip(dynamic_alpha, 0.0, 0.65)
    predicted = (
        np.asarray(base_prediction, dtype="float64") * (1.0 - dynamic_alpha)
        + np.asarray(peak_prediction, dtype="float64") * dynamic_alpha
    )
    return predicted, dynamic_alpha


def predict_candidate_components(
    candidate: LoadedCandidate,
    frame: pd.DataFrame,
    timestamps: pd.DatetimeIndex | pd.Series,
    identity: dict[str, Any],
) -> pd.DataFrame:
    validate_feature_batch(frame, timestamps, candidate.feature_contract, identity)
    base = np.asarray(candidate.models["base_model.joblib"].predict(frame), dtype="float64")
    peak = np.asarray(candidate.models["peak_model.joblib"].predict(frame), dtype="float64")
    # RandomForest reductions with n_jobs != 1 can change a few probability
    # values by one ULP between calls. Predict through a shallow execution-only
    # copy so the artifact remains untouched and component output is bitwise stable.
    classifier = copy.copy(candidate.models["spike_classifier.joblib"])
    classifier.n_jobs = 1
    classification = np.asarray(classifier.predict(frame), dtype="float64")
    probability = np.asarray(classifier.predict_proba(frame), dtype="float64")[:, 1]
    p90 = np.asarray(
        candidate.models["p90_model.joblib"].predict(frame, num_threads=1),
        dtype="float64",
    )
    peak_flags = frame["hour"].isin(PEAK_HOURS).astype(int).to_numpy()
    load_high_flag = frame["forecast_load"] >= frame["forecast_load"].quantile(0.75)
    error_high_flag = frame["scenario_mae"] >= frame["scenario_mae"].quantile(0.75)
    thresholds = candidate.metadata["thresholds"]
    metrics = candidate.metadata["metrics"]
    training = candidate.metadata["training_config"]
    predicted, blend_weight = _blend_predictions(
        base,
        peak,
        probability,
        peak_flags,
        alpha=thresholds.get("best_alpha", metrics.get("best_alpha", 0.0)),
        peak_floor=thresholds.get("best_peak_floor", metrics.get("best_peak_floor", 0.0)),
        load_high_flag=load_high_flag,
        error_high_flag=error_high_flag,
        spike_threshold=thresholds.get(
            "best_spike_threshold",
            metrics.get("best_spike_threshold", training.get("best_spike_threshold", 0.5)),
        ),
    )
    outputs = {
        "base_prediction": base,
        "peak_prediction": peak,
        "classifier_prediction": classification,
        "spike_probability": probability,
        "p90_prediction": p90,
        "blend_weight": np.asarray(blend_weight, dtype="float64"),
        "predicted_price": np.asarray(predicted, dtype="float64"),
    }
    if any(values.shape != (len(frame),) for values in outputs.values()):
        _fail("OUTPUT_SHAPE_MISMATCH", "模型组件输出不是一维 24 条")
    matrix = np.column_stack(list(outputs.values()))
    if not np.isfinite(matrix).all():
        _fail("OUTPUT_NONFINITE", "模型输出包含 NaN 或 Inf")
    index = pd.DatetimeIndex(timestamps)
    return pd.DataFrame({"timestamp": index.astype(str), **outputs})


def frame_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=False, lineterminator="\n", float_format="%.15g").encode("utf-8")).hexdigest()

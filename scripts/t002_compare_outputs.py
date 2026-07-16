from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from model_ops.result_hash import RESULT_VALUE_COLUMNS, compare_arrays, result_data_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    left_path = Path(args.left).resolve(strict=True)
    right_path = Path(args.right).resolve(strict=True)
    output_path = Path(args.output).resolve()
    left = pd.read_csv(left_path, encoding="utf-8-sig")
    right = pd.read_csv(right_path, encoding="utf-8-sig")
    left_times = pd.DatetimeIndex(pd.to_datetime(left["timestamp"], utc=True))
    right_times = pd.DatetimeIndex(pd.to_datetime(right["timestamp"], utc=True))
    comparison = {name: compare_arrays(left[name].to_numpy(), right[name].to_numpy()) for name in RESULT_VALUE_COLUMNS}
    left_hash = result_data_hash(left_times, left)
    right_hash = result_data_hash(right_times, right)
    report = {
        "left": str(left_path),
        "right": str(right_path),
        "left_rows": len(left),
        "right_rows": len(right),
        "timestamps_equal": left_times.equals(right_times),
        "left_result_data_hash": left_hash,
        "right_result_data_hash": right_hash,
        "result_data_hash_equal": left_hash == right_hash,
        "components": comparison,
        "all_components_equal": all(item["equal"] for item in comparison.values()),
    }
    report["status"] = "PASS" if (
        report["left_rows"] == report["right_rows"] == 24
        and report["timestamps_equal"]
        and report["result_data_hash_equal"]
        and report["all_components_equal"]
    ) else "FAIL"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "status", "left_rows", "right_rows", "result_data_hash_equal", "all_components_equal"
    )}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

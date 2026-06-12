# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from model_ops.actuals_updater import calculate_error_values
from model_ops.model_comparator import compare_candidate_to_active
from model_ops.model_monitor import decide_retrain, summarize_error_window
from model_ops.prediction_tracker import build_prediction_tracking_frame


class StageThreeModelOpsTests(unittest.TestCase):
    def test_prediction_tracking_frame_maps_future_result(self):
        future = pd.DataFrame(
            {
                "datetime": pd.date_range("2026-01-01", periods=2, freq="h"),
                "预测的未来24小时日前电价": [30.5, 40.5],
                "尖峰风险概率": [0.2, 0.8],
            }
        )
        result = build_prediction_tracking_frame(future, "run1", "model_run1", "features_a")
        self.assertEqual(len(result), 2)
        self.assertEqual(result["run_id"].iloc[0], "run1")
        self.assertEqual(result["model_version"].iloc[0], "model_run1")
        self.assertEqual(result["is_spike_risk"].tolist(), [0, 1])

    def test_error_calculation(self):
        errors = calculate_error_values(predicted_price=90, actual_price=100)
        self.assertEqual(errors["abs_error"], 10)
        self.assertAlmostEqual(errors["pct_error"], 10.0)

    def test_monitor_retrain_decision(self):
        recent = {"sample_count": 48, "rmse": 130.0}
        baseline = {"sample_count": 240, "rmse": 100.0}
        decision = decide_retrain(recent, baseline)
        self.assertTrue(decision.should_retrain)
        self.assertEqual(decision.status, "degraded")

    def test_error_window_summary(self):
        df = pd.DataFrame(
            {
                "predicted_price": [90.0, 110.0],
                "actual_price": [100.0, 100.0],
                "abs_error": [10.0, 10.0],
                "pct_error": [10.0, 10.0],
            }
        )
        summary = summarize_error_window(df)
        self.assertEqual(summary["sample_count"], 2.0)
        self.assertAlmostEqual(summary["rmse"], 10.0)

    def test_candidate_comparison_thresholds(self):
        decision = compare_candidate_to_active(
            {"rmse": 96.0, "peak_rmse": 50.0, "spike_rmse": 52.0},
            {"rmse": 100.0, "peak_rmse": 50.0, "spike_rmse": 50.0},
        )
        self.assertTrue(decision.promote)


if __name__ == "__main__":
    unittest.main()

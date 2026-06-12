# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from prediction_engine.features import build_feature_list, leakage_check_report


class LeakageFilterTests(unittest.TestCase):
    def test_build_feature_list_excludes_unavailable_current_hour_fields(self):
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2026-01-01", periods=3, freq="h"),
                "da_price": [10.0, 11.0, 12.0],
                "actual_load": [100.0, 101.0, 102.0],
                "rt_price": [9.0, 10.0, 11.0],
                "forecast_load": [98.0, 99.0, 100.0],
                "da_price_lag_1": [9.5, 10.5, 11.5],
            }
        )
        features = build_feature_list(df)
        self.assertNotIn("da_price", features)
        self.assertNotIn("actual_load", features)
        self.assertNotIn("rt_price", features)
        self.assertIn("forecast_load", features)
        self.assertIn("da_price_lag_1", features)

    def test_leakage_report_flags_raw_banned_columns(self):
        report = leakage_check_report(pd.DataFrame({"actual_load": [1], "forecast_load": [2]}))
        disabled_by_col = dict(zip(report["字段名"], report["是否禁用"]))
        self.assertEqual(disabled_by_col["actual_load"], 1)
        self.assertEqual(disabled_by_col["forecast_load"], 0)


if __name__ == "__main__":
    unittest.main()

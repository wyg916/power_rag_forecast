# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from prediction_engine.formal_forecast import add_residual_prediction_intervals


class FormalForecastIntervalTests(unittest.TestCase):
    def test_add_residual_prediction_intervals_uses_test_residuals(self):
        future = pd.DataFrame(
            {
                "datetime": pd.date_range("2026-01-03", periods=2, freq="h"),
                "预测的未来24小时日前电价": [100.0, 110.0],
            }
        )
        test_predictions = pd.DataFrame(
            {
                "datetime": pd.date_range("2026-01-01", periods=6, freq="h"),
                "真实值": [101.0, 104.0, 98.0, 110.0, 115.0, 118.0],
                "高峰增强融合预测值": [100.0, 100.0, 100.0, 109.0, 111.0, 120.0],
            }
        )
        result = add_residual_prediction_intervals(future, test_predictions)
        self.assertIn("预测下界_P10", result.columns)
        self.assertIn("预测上界_P90", result.columns)
        self.assertTrue((result["预测上界_P90"] >= result["预测下界_P10"]).all())
        self.assertEqual(result["预测区间方法"].iloc[0], "残差分布法_按小时P10_P90")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from prediction_engine.model_trainer import load_model_artifacts, save_model_artifacts


class ConstantModel:
    def predict(self, X):
        return [1.0 for _ in range(len(X))]


class ModelArtifactTests(unittest.TestCase):
    def test_save_and_load_model_artifacts(self):
        artifacts = {
            "base_name": "base",
            "peak_name": "peak",
            "classifier_name": "classifier",
            "best_alpha": 0.4,
            "best_floor": 0.25,
            "final_base_model": ConstantModel(),
            "final_peak_model": ConstantModel(),
            "final_classifier": None,
            "metrics_df": pd.DataFrame([{"模型": "base", "RMSE": 1.2}]),
            "peak_compare_df": pd.DataFrame([{"分组": "peak", "RMSE": 2.0}]),
            "validation_summary": pd.DataFrame([{"项目": "基础模型", "值": "base"}]),
        }
        frame = pd.DataFrame({"datetime": pd.date_range("2026-01-01", periods=2, freq="h"), "x": [1, 2]})
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = save_model_artifacts(
                artifacts,
                ["x"],
                train_df=frame,
                val_df=frame,
                test_df=frame,
                output_root=tmp,
                run_id="unit_test",
            )
            expected = [
                "base_model.joblib",
                "peak_model.joblib",
                "spike_classifier.joblib",
                "feature_cols.json",
                "training_config.json",
                "metrics.json",
                "thresholds.json",
                "model_card.md",
                "input_schema.json",
            ]
            for name in expected:
                self.assertTrue((artifact_dir / name).exists(), name)
            loaded = load_model_artifacts(artifact_dir)
            self.assertEqual(loaded["feature_cols"], ["x"])
            config = json.loads((Path(artifact_dir) / "training_config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["model_version"], "model_unit_test")


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
import importlib
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - dependency may not exist before requirements install
    yaml = None

from automation_common import save_config
try:
    from llm_client import LLMClient
except Exception:  # pragma: no cover - dependencies may not exist before requirements install
    LLMClient = None

try:
    build_peak_model_summary = importlib.import_module("02_build_ai_summary").build_peak_model_summary
except Exception:  # pragma: no cover - dependencies may not exist before requirements install
    build_peak_model_summary = None


class StageOneSafetyTests(unittest.TestCase):
    def test_extract_json_object_with_extra_text(self):
        if LLMClient is None:
            self.skipTest("requests/jsonschema 等运行依赖未安装；安装 requirements.txt 后会执行该测试。")
        raw = "说明文字 {\"executive_summary\":\"ok\",\"peak_risk\":\"risk\"} 结束"
        self.assertEqual(
            LLMClient.extract_json_object(raw),
            "{\"executive_summary\":\"ok\",\"peak_risk\":\"risk\"}",
        )

    def test_peak_model_summary_aliases(self):
        if build_peak_model_summary is None:
            self.skipTest("pandas/SQLAlchemy 等运行依赖未安装；安装 requirements.txt 后会执行该测试。")
        summary = {
            "高峰专项基础模型": "线性回归",
            "高峰专项模型": "Peak_RandomForest",
            "尖峰风险分类器": "Spike_HGB_Classifier",
            "最佳融合alpha": 0,
            "最佳peak_floor": 0,
        }
        result = build_peak_model_summary(summary)
        self.assertEqual(result["base_model_name"], "线性回归")
        self.assertEqual(result["peak_model_name"], "Peak_RandomForest")
        self.assertEqual(result["classifier_name"], "Spike_HGB_Classifier")
        self.assertEqual(result["best_alpha"], 0.0)
        self.assertEqual(result["best_peak_floor"], 0.0)

    def test_dispatch_script_has_no_recursive_delete(self):
        text = Path("04_dispatch_report.py").read_text(encoding="utf-8")
        self.assertNotIn("rm" + "tree", text)

    def test_save_config_sanitizes_secrets(self):
        if yaml is None:
            self.skipTest("PyYAML 未安装；安装 requirements.txt 后会执行该测试。")
        config = {
            "database": {"password": "secret"},
            "llm": {"api_key": "secret"},
            "market": {"pjm_subscription_key": "secret"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config(config, path)
            saved = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["database"]["password"], "")
        self.assertEqual(saved["llm"]["api_key"], "")
        self.assertEqual(saved["market"]["pjm_subscription_key"], "")


if __name__ == "__main__":
    unittest.main()

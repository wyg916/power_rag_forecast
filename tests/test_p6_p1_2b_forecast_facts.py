from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from tests.test_p6_p1_1a_data_center import _protected_counts


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_forecast_fact_endpoints_remain_read_only_and_traceable():
    before = _protected_counts()
    latest = client.get("/api/forecast/24h")
    runs = client.get("/api/forecast/runs?status=success&limit=3")
    quality = client.get("/api/data/quality")
    strategy = client.get("/api/strategy/today")
    assert all(response.status_code == 200 for response in [latest, runs, quality, strategy])
    assert len(latest.json()["series"]) == 24
    assert latest.json()["run_id"]
    assert latest.json()["model_version"]
    assert latest.json()["feature_version"]
    assert quality.json()["is_stale"] is True
    assert strategy.json()["run_id"] == latest.json()["run_id"]
    assert _protected_counts() == before


def test_previous_batch_is_not_replaced_by_history_mean():
    runs = client.get("/api/forecast/runs?status=success&limit=3").json()["items"]
    service = _read("frontend/src/services/forecastApi.ts")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    assert len(runs) == 1
    assert "previousRun = " in service
    assert "api.forecastRunResults(previousRun.run_id)" in service
    assert "当前只有一个成功预测批次" in service
    assert "previous = historyMean" not in service
    assert "上一批次/历史参考" not in design
    assert "历史小时均值（接口范围）" in design


def test_missing_confidence_interval_is_explicit_and_not_synthesized():
    service = _read("frontend/src/services/forecastApi.ts")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    assert "lower ?? Math.max" not in service
    assert "upper ?? price +" not in service
    assert "confidenceIntervalAvailable" in service
    assert "页面未将其作为正式置信区间展示" in service
    assert "置信区间待接入" in design
    assert "正式置信区间未接入，不参与解释" in design
    assert "100 - avgRisk * 35" not in service
    assert "Math.max(60, 100 -" not in service
    assert "api_prediction_confidence_unavailable" in service


def test_hour_ranges_and_windows_come_from_real_datetimes():
    service = _read("frontend/src/services/forecastApi.ts")
    assert "nextHourLabel(item.datetime)" in service
    assert "nextHourLabel(index)" not in service
    assert "localeCompare" in service
    assert "times.join('、')" in service


def test_data_health_uses_quality_timestamp_score_and_stale_reason():
    service = _read("frontend/src/services/forecastApi.ts")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    assert "api.dataQuality" in service
    assert "avg_check_pass_rate" in service
    assert "dataQuality?.generated_at" in service
    assert "dataQuality?.stale_reason" in service
    assert "10:30:00" not in service
    assert "异常原因" in design


def test_hour_advice_comes_from_strategy_api_and_has_source():
    service = _read("frontend/src/services/forecastApi.ts")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    assert "adviceForHour(strategy, item.datetime)" in service
    assert "api_strategy_today:" in service
    assert "function actionFor" not in service
    assert "接口建议" in design
    assert "建议来源" in page


def test_model_and_history_empty_semantics_do_not_use_success_defaults():
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    assert "上一成功批次不可用" in page
    assert "名称待接入" in design
    assert "模型解释接口未返回主要因素" in design
    assert "['负荷预期抬升', '新能源出力变化', '气温因素']" not in design

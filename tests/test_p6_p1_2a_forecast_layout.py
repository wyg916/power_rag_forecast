from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from tests.test_p6_p1_1a_data_center import _protected_counts


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_forecast_24h_uses_real_stale_run_without_read_side_effects():
    before = _protected_counts()
    response = client.get("/api/forecast/24h")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert len(payload["series"]) == 24
    assert payload["run_id"].startswith("run_")
    assert payload["model_version"]
    assert payload["feature_version"]
    assert payload["is_stale"] is True
    assert payload["stale_reason"] == "forecast_window_expired"
    assert _protected_counts() == before


def test_metric_cards_do_not_reuse_one_series_as_fake_per_metric_trend():
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    assert "MiniSparkline" not in design
    assert "ForecastMetricCards({ metrics }" in design
    assert "<ForecastMetricCards metrics={metricItems} />" in page
    assert "forecast-metric-source" in design


def test_forecast_chart_and_detail_table_have_internal_scroll_contracts():
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    styles = _read("frontend/src/styles.css")
    assert 'className="forecast-chart-body"' in design
    assert 'height="100%"' in design
    assert "scroll={{ y: compact ? 142 : 210, x: 1080 }}" in design
    assert ".forecast-chart-body" in styles
    assert "min-height: 0;" in styles
    assert "overflow: hidden;" in styles


def test_hour_explanation_is_a_real_local_detail_action():
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    assert "selectedHour" in page
    assert "<DetailDrawer" in page
    assert "onExplain={setSelectedHour}" in page
    assert "onClick={() => onExplain?.(row)}" in design
    for field in ["run_id", "model_version", "feature_version", "data_source"]:
        assert field in page


def test_forecast_secondary_actions_have_real_urls_or_explicit_disable_reason():
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    assert 'href="#/data/quality"' in design
    assert 'href="#/forecast/24h"' in design
    assert 'href="#/task/log"' in design
    assert 'href="#/report/list"' in design
    assert "disabledReason" in page
    assert "缺少报告上下文" in page
    assert '<Button type="link">' not in design


def test_forecast_keeps_unified_header_and_no_static_success_fallback():
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    service = _read("frontend/src/services/forecastApi.ts")
    assert "PageHeader" in page and "PageTabs" in page
    assert "PageDataState" in page
    assert "FactStatusBar" not in page
    assert "mockFallback: false" in service
    for forbidden in ["Math.random", "forecastMock", "staticForecastData"]:
        assert forbidden not in page + service

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
    assert "forecast-metric-source" not in design


def test_forecast_chart_and_detail_table_avoid_internal_scroll_workarounds():
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    styles = _read("frontend/src/styles.css")
    assert 'className="forecast-chart-body"' in design
    assert 'height="100%"' in design
    assert 'tableLayout="fixed"' in design
    assert "pageSize: compact ? 4 : 8" in design
    assert "scroll={{" not in design
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
    detail = page.split('<DetailDrawer', 1)[1].split('onClose=', 1)[0]
    for technical_field in ["预测批次", "模型版本", "特征版本", "model_version", "feature_version", "data_source"]:
        assert technical_field not in detail
    assert "建议来源" in detail


def test_forecast_secondary_actions_have_real_urls_or_explicit_disable_reason():
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    assert 'href="#/data/quality"' in design
    assert 'href="#/forecast/24h"' in design
    assert 'href="#/task/log"' in design
    assert 'href="#/report/list"' in design
    assert "disabledReason" in page
    assert "window.location.hash = '#/strategy/strategy-high'" in page
    assert '<Button type="link">' not in design


def test_forecast_keeps_unified_header_and_no_static_success_fallback():
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    service = _read("frontend/src/services/forecastApi.ts")
    assert "PageHeader" in page and "PageTabs" in page
    assert "PageDataState" in page
    assert "FactStatusBar" not in page
    assert "mockFallback: false" in service
    assert "!showContent ? <PageDataState" in page
    for forbidden in ["Math.random", "forecastMock", "staticForecastData"]:
        assert forbidden not in page + service


def test_forecast_frontend_does_not_render_audit_or_expiry_metadata():
    page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    rendered = page + design
    for forbidden in [
        "数据已过期", "预测适用窗口已结束", "生成时间", "更新时间", "run_id",
        "模型版本", "特征版本", "预测日期", "区域", "推理模型", "适用窗口", "批次状态", "异常原因"
    ]:
        assert forbidden not in rendered

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.source_contract import (
    SourceType,
    _forecast_stale,
    attach_source_meta,
    source_meta,
)


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_fact_metadata_contract_classifies_every_supported_origin() -> None:
    expected = {
        SourceType.REAL: "real_current",
        SourceType.HISTORICAL: "real_historical",
        SourceType.SIMULATED: "simulation",
        SourceType.DEMO: "seed",
        SourceType.SEED: "seed",
        SourceType.FALLBACK: "degraded",
        SourceType.DERIVED: "derived",
        SourceType.AI_INFERRED: "ai_inferred",
        SourceType.UNAVAILABLE: "unavailable",
    }
    required = {
        "data_origin", "source_type", "source_name", "generated_at", "updated_at",
        "valid_from", "valid_to", "freshness_status", "is_stale", "staleness_reason",
        "run_id", "model_version", "feature_version", "data_version", "simulation",
        "degraded", "availability", "unavailable_reason",
    }
    for source_type, origin in expected.items():
        meta = source_meta(
            source_type,
            "electricity_day_ahead_price",
            generated_at="2026-07-31T08:00:00Z",
        )
        assert required <= meta.keys()
        assert meta["data_origin"] == origin
        assert meta["simulation"] is (source_type is SourceType.SIMULATED)
        assert meta["degraded"] is (source_type is SourceType.FALLBACK)
    assert source_meta(SourceType.HISTORICAL, "report")["is_stale"] is True


def test_attach_source_meta_prevents_conflicting_root_truth_fields() -> None:
    meta = source_meta(
        SourceType.HISTORICAL,
        "report",
        run_id="run-history",
        valid_to="2026-07-01T00:00:00Z",
    )
    payload = attach_source_meta(
        {"source_type": "real", "is_stale": False, "freshness_status": "current"},
        meta,
    )
    assert payload["source_type"] == "historical"
    assert payload["is_stale"] is True
    assert payload["freshness_status"] == "historical"
    assert payload["staleness_reason"] == "historical_record"


def test_forecast_freshness_uses_business_window_and_explicit_reason() -> None:
    now = datetime.now(timezone.utc)
    current = _forecast_stale({"forecast_end_at": now + timedelta(hours=2)}, historical=False)
    expired = _forecast_stale({"forecast_end_at": now - timedelta(hours=2)}, historical=False)
    historical = _forecast_stale({"forecast_end_at": now + timedelta(hours=2)}, historical=True)
    missing = _forecast_stale({}, historical=False)
    assert current[0] is False and current[1] is None
    assert expired[:2] == (True, "forecast_window_expired")
    assert historical[:2] == (True, "historical_run")
    assert missing[:2] == (True, "generated_at_missing")


def test_prediction_values_are_never_relabelled_as_observed_or_realtime_price() -> None:
    service = _read("frontend/src/services/forecastApi.ts")
    pages = _read("frontend/src/components/forecast/ForecastDesign.tsx") + _read(
        "frontend/src/pages/forecast/ForecastCenterPage.tsx"
    )
    price_keys = service.split("const PRICE_KEYS", 1)[1].split("];", 1)[0]
    assert "actual_price" not in price_keys
    assert "clearing_price" not in price_keys
    assert "readObservedPrice" in service
    assert "实时电价" not in pages
    for field in ["validFrom", "validTo", "runId", "modelVersion", "featureVersion", "freshnessStatus"]:
        assert field in service


def test_report_has_no_fabricated_comparison_reviewer_or_static_business_fact() -> None:
    page = _read("frontend/src/pages/report/ReportCenterPage.tsx")
    service = _read("frontend/src/services/reportApi.ts")
    combined = page + service
    for forbidden in ["0.85", "同比 +", "较昨日 +", "张三", "李四", "王五", "2025-06-14", "2025-06-21"]:
        assert forbidden not in combined
    assert "实时电价" not in combined
    assert "?? '--'" in page
    assert "当前无上一版本或同比基线，不生成对比结论" in page
    assert "reviewer: user.username" in page


def test_strategy_separates_record_review_validity_simulation_and_execution() -> None:
    service = _read("frontend/src/services/strategyApi.ts")
    design = _read("frontend/src/components/strategy/StrategyDesign.tsx")
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    assert "strategyStatus" in service and "strategyUsable" in service
    assert "governedStrategy?.is_stale || today?.is_stale || forecast?.is_stale" in service
    for wording in ["测算收益", "非实际结算", "不可作为当前策略", "模拟设备 / 非实际执行"]:
        assert wording in design
    assert "PageDataState" in page
    assert "showContent" in page


def test_dashboard_kpi_name_matches_forecast_spread_and_missing_values_stay_missing() -> None:
    service = _read("frontend/src/services/homeDashboardApi.ts")
    page = _read("frontend/src/pages/dashboard/DashboardPage.tsx")
    assert "key: 'strategy_spread'" in service
    assert "title: '预测峰谷价差'" in service
    assert "不代表收益或结算结果" in service
    assert "updatedAt: meta.updated_at" in service
    assert "PageDataState" in page
    assert "?? '--'" in page


def test_seed_and_unavailable_records_cannot_become_core_page_success_fallbacks() -> None:
    core_services = "\n".join(
        _read(path)
        for path in [
            "frontend/src/services/homeDashboardApi.ts",
            "frontend/src/services/forecastApi.ts",
            "frontend/src/services/reportApi.ts",
            "frontend/src/services/strategyApi.ts",
        ]
    )
    assert "mockFallback: true" not in core_services
    assert "source_type === 'seed'" not in core_services
    assert "freshnessStatus === 'unavailable'" in core_services
    unavailable = source_meta(SourceType.UNAVAILABLE, "strategy", unavailable_reason="no_facts")
    assert unavailable["availability"] == "unavailable"
    assert unavailable["freshness_status"] == "unavailable"


def test_data_center_keeps_registered_business_dataset_and_truth_state_contract() -> None:
    page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    service = _read("frontend/src/services/dataApi.ts")
    assert "PageDataState" in page
    assert "CatalogPanel" in page and "SourceStatusBar" in page
    assert "api.dataDatasets" in service and "api.dataFreshness" in service
    assert "qualityItems" in service and "isStale" in service and "generatedAt" in service
    dataset_service = _read("backend/app/services/dataset_query_service.py")
    assert "(?:day3_close|day5)" in dataset_service


@pytest.mark.parametrize("viewport", [(1366, 768), (1440, 900), (1600, 900), (1920, 1080)])
def test_truth_pages_have_shared_responsive_overflow_guards(viewport: tuple[int, int]) -> None:
    width, height = viewport
    assert width >= 1366 and height >= 768
    styles = _read("frontend/src/styles.css")
    assert "overflow-x: hidden" in styles
    assert "@media (max-width: 1600px)" in styles
    assert "@media (max-width: 1500px)" in styles
    for class_name in ["home-dashboard-page", "forecast-design-page", "report-workbench", "strategy-design-page"]:
        assert class_name in styles

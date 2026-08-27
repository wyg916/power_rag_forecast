from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.data_access import database_engine
from backend.app.main import app


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _strategy_write_counts() -> dict[str, int]:
    engine = database_engine()
    assert engine is not None
    with engine.connect() as conn:
        return {
            table: int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0)
            for table in ("strategy_advice", "strategy_reviews", "audit_logs")
        }


def test_strategy_context_is_migrated_into_shared_page_header():
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    design = _read("frontend/src/components/strategy/StrategyDesign.tsx")

    assert 'className="strategy-page-header"' in page
    assert "metadata={(" in page
    assert "filters={(" in page
    assert "actions={headerActions}" in page
    assert "strategy-header-metadata" in page
    assert "strategy-header-filters" in page
    assert "StrategyContextBar" not in page + design


def test_strategy_header_actions_are_real_permission_aware_and_collapsible():
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")

    assert "onClick: loadData" in page
    assert "exportCsv(" in page
    assert "canConfigure = canPerformAction('strategy:manage')" in page
    assert "hidden: !canConfigure" in page
    assert "collapseAtNarrow: true" in page
    assert "批量通过（暂不可用）" in page
    assert "批量驳回（暂不可用）" in page
    assert "为保证逐条证据核验与审计追踪" in page
    assert "Math.random" not in page


def test_strategy_header_uses_neutral_business_metadata_without_technical_trace_blocks_or_fallback():
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    service = _read("frontend/src/services/strategyApi.ts")

    assert "data?.strategyDate" in page
    metadata = page.split('className="strategy-header-metadata"', 1)[1].split("</div>", 1)[0]
    for field in ("strategyVersion", "modelVersion", "sourceType", "runId", "generatedAt"):
        assert field not in metadata
        assert field in service
    assert "strategyVersion: governedItems[0]?.strategy_version || ''" in service
    assert "region: devices[0]?.region || governedItems[0]?.region || forecast?.region || today?.region || latest?.region || null" in service
    assert "const resolvedConfig = config && typeof config === 'object' ? config : {}" in service
    assert "region: '浙江省'" not in service
    assert "high_price_threshold: 160" not in service
    assert "modelVersion: governedItems[0]?.model_version || forecast?.model_version || '???'" not in service
    assert "当前策略接口未提供区域字段，不能伪造筛选值" in page


def test_strategy_metric_cards_are_compact_without_clipping_complete_semantics():
    base_styles = _read("frontend/src/styles.css")
    strategy_styles = _read("frontend/src/pages/strategy/strategy-center-layout.css")
    metric_block = strategy_styles.split(".strategy-design-page .strategy-metric {", 1)[1].split(
        ".strategy-design-page .strategy-metric-icon", 1
    )[0]
    strong_block = base_styles.split(".strategy-metric strong {", 1)[1].split(".strategy-metric p", 1)[0]
    description_block = base_styles.split(".strategy-metric p {", 1)[1].split(".strategy-card", 1)[0]

    assert "height: 88px" in metric_block
    assert "min-height: 88px" in metric_block
    assert "padding: 8px 10px" in metric_block
    assert "overflow-wrap: anywhere" in strong_block
    assert "overflow-wrap: anywhere" in description_block
    assert "text-overflow: ellipsis" not in strong_block
    assert "text-overflow: ellipsis" not in description_block
    assert "white-space: nowrap" not in strong_block
    assert "white-space: nowrap" not in description_block


def test_strategy_three_subroutes_and_narrow_more_contract_are_preserved():
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    router = _read("frontend/src/app/router.tsx")
    header = _read("frontend/src/components/common/PageHeader.tsx")
    styles = _read("frontend/src/styles.css")
    strategy_styles = _read("frontend/src/pages/strategy/strategy-center-layout.css")

    for key in ("strategy-high", "strategy-storage", "strategy-review"):
        assert key in page
    assert "'strategy-low': 'strategy-storage'" in router
    assert "page-heading-more" in header
    assert "@container (max-width: 1150px)" in styles
    assert ".page-heading-secondary-action" in styles
    assert "@media (max-width: 1700px)" in strategy_styles
    assert ".strategy-design-page .strategy-page-header .page-heading-secondary-action" in strategy_styles
    assert "FactStatusBar" not in page


def test_strategy_tabs_are_a_prominent_equal_width_navigation_band_and_context_moves_right():
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    strategy_styles = _read("frontend/src/pages/strategy/strategy-center-layout.css")

    assert 'className="strategy-meta-date"' in page
    assert 'className="strategy-meta-status"' in page
    assert "grid-template-columns: minmax(540px, 600px) minmax(0, 1fr)" in strategy_styles
    assert ".strategy-page-tabs .ant-tabs-nav-list" in strategy_styles
    assert "flex: 1 1 0" in strategy_styles
    assert ".strategy-page-tabs .ant-tabs-tab-active" in strategy_styles
    assert "background: #087a5b" in strategy_styles


def test_strategy_overview_cards_fill_the_row_and_execution_progress_is_explicit():
    design = _read("frontend/src/components/strategy/StrategyDesign.tsx")
    strategy_styles = _read("frontend/src/pages/strategy/strategy-center-layout.css")
    bottom_block = strategy_styles.split(".strategy-design-page .strategy-overview-bottom {", 1)[1].split(
        ".strategy-design-page .mini-panel", 1
    )[0]

    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in bottom_block
    assert "padding-right: 0" in bottom_block
    assert "execution-progress-wrap" in design
    assert "执行完成率" in design
    assert 'trailColor="#e7eef3"' in design


def test_strategy_storage_and_review_fill_space_from_existing_api_rows_only():
    design = _read("frontend/src/components/strategy/StrategyDesign.tsx")
    service = _read("frontend/src/services/strategyApi.ts")

    assert "storage-device-summary" in design
    assert "storage-execution-summary" in design
    assert "executions.filter" in design
    assert "rows.reduce" in design
    assert "calc(100dvh - 560px)" in design
    assert "Math.random" not in design
    assert "executionItems = (Array.isArray(runtime?.execution_items)" in service
    assert "devices = Array.isArray(runtime?.devices)" in service


def test_strategy_short_desktop_viewport_has_a_non_clipping_height_budget():
    design = _read("frontend/src/components/strategy/StrategyDesign.tsx")
    strategy_styles = _read("frontend/src/pages/strategy/strategy-center-layout.css")

    assert "@media (min-width: 1181px) and (max-height: 820px)" in strategy_styles
    assert "height: 92px" in strategy_styles
    assert "grid-template-rows: minmax(0, .88fr) minmax(226px, 1.12fr)" in strategy_styles
    assert "clamp(154px, calc(100dvh - 560px), 392px)" in design


def test_strategy_get_chain_has_no_strategy_or_audit_write_side_effects():
    before = _strategy_write_counts()
    paths = (
        "/api/strategy/today",
        "/api/strategy/latest",
        "/api/anomaly/latest",
        "/api/strategy/config",
        "/api/forecast/24h",
        "/api/strategies?limit=100",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
    assert _strategy_write_counts() == before

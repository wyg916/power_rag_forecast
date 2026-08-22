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
    styles = _read("frontend/src/styles.css")
    metric_block = styles.split(".strategy-metric {", 1)[1].split(".strategy-metric-icon", 1)[0]
    strong_block = styles.split(".strategy-metric strong {", 1)[1].split(".strategy-metric p", 1)[0]
    description_block = styles.split(".strategy-metric p {", 1)[1].split(".strategy-card", 1)[0]

    assert "flex: 0 0 98px" in styles
    assert "padding: 11px 12px" in metric_block
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

    for key in ("strategy-high", "strategy-storage", "strategy-review"):
        assert key in page
    assert "'strategy-low': 'strategy-storage'" in router
    assert "page-heading-more" in header
    assert "@container (max-width: 1150px)" in styles
    assert ".page-heading-secondary-action" in styles
    assert "FactStatusBar" not in page


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

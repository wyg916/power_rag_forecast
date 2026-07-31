from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_sc006_uses_one_shared_three_page_header_and_layout_system() -> None:
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    assert page.count("\n      <PageHeader\n") == 1
    assert page.count("<StrategyMetricStrip") == 1
    assert "items={strategyTabs}" in page
    assert "activeKey={activeTabKey}" in page
    assert "onChange={handleStrategyTabChange}" in page
    for mode in ("overview", "storage", "review"):
        assert f"mode === '{mode}'" in page


def test_sc006_exposes_the_same_trace_metadata_on_all_subpages() -> None:
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    metadata_start = page.index('className="strategy-header-metadata"')
    metadata_end = page.index("</div>", metadata_start)
    metadata = page[metadata_start:metadata_end]
    for field in ("strategyDate", "strategyVersion", "modelVersion", "runId", "generatedAt", "sourceType"):
        assert field in metadata
    assert "staleReason" in metadata
    assert "strategy-meta-run" in metadata
    assert "strategy-meta-stale" in metadata


def test_review_filter_policy_is_explicit_and_can_be_cleared() -> None:
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    assert "REVIEW_FILTER_POLICY = 'preserve-within-session'" in page
    assert "data-filter-policy={mode === 'review' ? REVIEW_FILTER_POLICY : 'page-scoped'}" in page
    assert "onSubNavigate(key)" in page
    assert "setReviewFilters(DEFAULT_REVIEW_FILTERS)" in page
    assert "清除筛选" in page


def test_review_selection_tracks_the_filtered_result_set() -> None:
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    assert "filteredReviewRows.some((item: any) => item.key === current)" in page
    assert "filteredReviewRows[0]?.key" in page
    assert "rows.find((row: any) => row.key === selectedKey) || rows[0]" in _read(
        "frontend/src/components/strategy/StrategyDesign.tsx"
    )


def test_strategy_source_metadata_has_bounded_narrow_screen_styles() -> None:
    styles = _read("frontend/src/styles.css")
    assert ".strategy-header-metadata .strategy-meta-run strong" in styles
    assert ".strategy-header-metadata .strategy-meta-stale .ant-tag" in styles
    assert ".strategy-header-metadata { flex-wrap: wrap; justify-content: flex-start; }" in styles


def test_p13b_does_not_add_frontend_business_fallbacks() -> None:
    page = _read("frontend/src/pages/strategy/StrategyCenterPage.tsx")
    service = _read("frontend/src/services/strategyApi.ts")
    assert "Math.random" not in page
    assert "PageDataState" in page
    assert "showContent" in page
    assert "mockFallback: false" in service
    assert "PHASE5_D_TEST_DATABASE_URL" not in page

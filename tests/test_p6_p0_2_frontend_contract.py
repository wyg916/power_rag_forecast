from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_unified_header_is_the_only_data_forecast_header():
    header = _read("frontend/src/components/common/PageHeader.tsx")
    data_page = _read("frontend/src/pages/data/DataCenterPage.tsx")
    forecast_page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    data_design = _read("frontend/src/components/data/DataCenterDesign.tsx")
    forecast_design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    styles = _read("frontend/src/styles.css")

    for contract in ["navigation", "metadata", "filters", "actions", "collapseAtNarrow", "disabledReason"]:
        assert contract in header
    assert "page-heading-more" in header
    assert "@container (max-width: 1150px)" in styles
    assert "PageHeader" in data_page and "PageHeader" in forecast_page
    assert "PageTabs" in data_page and "PageTabs" in forecast_page
    assert "DataPageHeader" not in data_design
    assert "ForecastPageHeader" not in forecast_design


def test_view_state_contract_has_seven_distinct_states_and_metadata():
    state = _read("frontend/src/services/viewState.ts")
    states = ["loading", "empty", "error", "stale", "success", "unauthorized", "forbidden"]
    for name in states:
        assert f"'{name}'" in state
    for field in [
        "source",
        "generatedAt",
        "runId",
        "modelVersion",
        "featureVersion",
        "staleReason",
        "errorCode",
        "errorMessage",
        "canRetry",
    ]:
        assert field in state


def test_api_error_preserves_http_status_for_401_and_403_mapping():
    api = _read("frontend/src/api.ts")
    states = _read("frontend/src/services/viewState.ts")
    assert "export class ApiError extends Error" in api
    assert "readonly status: number" in api
    assert "throw new ApiError(response.status" in api
    assert "descriptor.status === 401" in states
    assert "descriptor.status === 403" in states


def test_refresh_and_permission_actions_are_real_or_explicitly_disabled():
    data = _read("frontend/src/pages/data/DataCenterPage.tsx")
    forecast = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    for source in [data, forecast]:
        assert "onClick: loadData" in source
        assert "loading," in source
    assert "api.dataRefresh()" in data
    assert "data:sync" in data
    assert "api.runForecast()" in forecast
    assert "forecast:run" in forecast
    assert "strategy:generate" in forecast
    assert "disabled: true" in forecast
    assert "缺少报告上下文" in forecast


def test_forecast_static_success_fallbacks_are_removed():
    forecast_service = _read("frontend/src/services/forecastApi.ts")
    forecast_page = _read("frontend/src/pages/forecast/ForecastCenterPage.tsx")
    forecast_design = _read("frontend/src/components/forecast/ForecastDesign.tsx")
    forbidden = ["2025-06-21", "'v3.2.1'", "'浙江省'", "['负荷预测', '新能源出力', '气温变化']"]
    combined = forecast_service + forecast_page + forecast_design
    for value in forbidden:
        assert value not in combined
    assert "mockFallback={false}" not in forecast_page
    assert "已启用兜底数据" not in _read("frontend/src/components/common/States.tsx")


def test_assistant_api_failure_does_not_import_static_success_payload():
    assistant_service = _read("frontend/src/services/assistantApi.ts")
    assert "assistantMock" not in assistant_service
    assert "error: errorMessage(error)" in assistant_service
    assert "conversations: []" in assistant_service


def test_no_fact_status_bar_regression_in_global_or_main_pages():
    targets = [
        "frontend/src/layout/BasicLayout.tsx",
        "frontend/src/pages/dashboard/DashboardPage.tsx",
        "frontend/src/pages/data/DataCenterPage.tsx",
        "frontend/src/pages/forecast/ForecastCenterPage.tsx",
        "frontend/src/pages/strategy/StrategyCenterPage.tsx",
        "frontend/src/pages/assistant/AssistantPage.tsx",
        "frontend/src/pages/report/ReportCenterPage.tsx",
        "frontend/src/pages/model/ModelCenterPage.tsx",
        "frontend/src/pages/knowledge/KnowledgeBasePage.tsx",
        "frontend/src/pages/task/TaskCenterPage.tsx",
        "frontend/src/pages/settings/SettingsPage.tsx",
    ]
    for target in targets:
        assert "FactStatusBar" not in _read(target)


def test_page_header_layout_prevents_horizontal_page_overflow():
    styles = _read("frontend/src/styles.css")
    for selector in [
        ".page-heading-unified",
        ".page-heading-copy",
        ".page-heading-utility",
        ".page-heading-filters",
    ]:
        assert selector in styles
    assert "min-width: 0;" in styles
    assert "grid-template-columns: minmax(300px, 0.8fr) minmax(0, 1.6fr);" in styles


def test_all_ten_main_pages_use_the_shared_page_header_path():
    direct_pages = [
        "frontend/src/pages/dashboard/DashboardPage.tsx",
        "frontend/src/pages/data/DataCenterPage.tsx",
        "frontend/src/pages/forecast/ForecastCenterPage.tsx",
        "frontend/src/pages/strategy/StrategyCenterPage.tsx",
        "frontend/src/pages/report/ReportCenterPage.tsx",
        "frontend/src/pages/model/ModelCenterPage.tsx",
        "frontend/src/pages/knowledge/KnowledgeBasePage.tsx",
        "frontend/src/pages/task/TaskCenterPage.tsx",
    ]
    for target in direct_pages:
        assert "PageHeader" in _read(target), target

    app = _read("frontend/src/app/App.tsx")
    page_container = _read("frontend/src/layout/PageContainer.tsx")
    assert "<PageHeader" in page_container
    hide_expression = app.split("hideHeader=", 1)[1].split(">", 1)[0]
    assert "'assistant'" not in hide_expression
    assert "'settings'" not in hide_expression
    assert "DataPageHeader" not in _read("frontend/src/components/data/DataCenterDesign.tsx")
    assert "ForecastPageHeader" not in _read("frontend/src/components/forecast/ForecastDesign.tsx")
    assert "StrategyPageHeader" not in _read("frontend/src/components/strategy/StrategyDesign.tsx")


def test_migrated_header_actions_keep_permission_and_noop_guards():
    dashboard = _read("frontend/src/pages/dashboard/DashboardPage.tsx")
    model = _read("frontend/src/pages/model/ModelCenterPage.tsx")
    knowledge = _read("frontend/src/pages/knowledge/KnowledgeBasePage.tsx")
    task = _read("frontend/src/pages/task/TaskCenterPage.tsx")
    assert "report:generate" in dashboard
    assert "task:run" in model
    assert "knowledge:write" in knowledge
    assert "task:run" in task
    assert "selectedTaskKind === 'all'" in task
    assert "请先选择具体任务类型" in task

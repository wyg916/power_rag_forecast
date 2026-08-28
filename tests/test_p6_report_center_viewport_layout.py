from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_report_center_uses_one_shared_toolbar_and_status_row():
    page = _read("frontend/src/pages/report/ReportCenterPage.tsx")

    assert "import './report-center-layout.css';" in page
    assert "报告中心 / 日报" in page
    assert "报告中心 / 报告审核与发布" in page
    assert page.count("<ReportStatusKpiRow") == 1
    assert "ReportMetricPair" not in page
    assert '<header className="report-page-toolbar">' in page


def test_report_workspace_closes_the_viewport_and_scrolls_inside_panes():
    styles = _read("frontend/src/pages/report/report-center-layout.css")

    assert "height: 100%;" in styles
    assert "flex-direction: column;" in styles
    assert "flex: 1 1 0;" in styles
    assert "grid-template-columns: minmax(260px, 286px) minmax(0, 1fr) minmax(300px, 320px);" in styles
    assert ".report-workbench .report-list-scroll" in styles
    assert ".report-workbench .report-preview-body" in styles
    assert ".report-workbench .report-review-body" in styles
    assert ".report-workbench .report-side-scroll" in styles
    assert styles.count("overflow-y: auto;") >= 4
    assert "--report-ai-safe-area: 72px;" in styles


def test_report_toolbar_is_opaque_and_does_not_use_extreme_z_index():
    styles = _read("frontend/src/pages/report/report-center-layout.css")
    toolbar = styles.split(".report-workbench .report-page-toolbar {", 1)[1].split("}", 1)[0]

    assert "position: sticky;" in toolbar
    assert "isolation: isolate;" in _read("frontend/src/pages/report/report-center-layout.css")
    assert "background: #fff;" in toolbar
    assert "z-index: 20;" in toolbar
    assert "999999" not in styles


def test_report_list_is_compact_and_preserves_full_text_via_tooltips():
    page = _read("frontend/src/pages/report/ReportCenterPage.tsx")
    styles = _read("frontend/src/pages/report/report-center-layout.css")

    assert "height: 74px;" in styles
    assert "grid-template-columns: minmax(0, 1fr) 68px;" in styles
    assert ".report-workbench .report-list-item-copy" in styles
    assert "flex-direction: column;" in styles
    assert "max-width: 68px;" in styles
    assert "-webkit-line-clamp: 2;" in styles
    assert "text-overflow: ellipsis;" in styles
    assert "<Tooltip title={item.title}>" in page
    assert "<Tooltip title={item.report_id}>" in page
    assert "shortTime(item.generated_at || item.updated_at || item.created_at)" in page


def test_report_successor_layout_uses_shared_dense_preview_contracts():
    styles = _read("frontend/src/pages/report/report-center-layout.css")

    assert "--report-toolbar-height: 54px;" in styles
    assert "--report-kpi-height: 70px;" in styles
    assert "height: 66px;" in styles
    assert "grid-template-columns: minmax(0, 1.22fr) minmax(0, 1fr);" in styles
    assert "width: 40% !important;" in styles
    assert "height: 184px !important;" in styles
    assert "height: 110px;" in styles
    assert "height: 92px !important;" in styles
    assert "grid-template-rows: repeat(2, minmax(0, 1fr));" in styles


def test_report_status_metrics_center_the_note_beside_the_value():
    styles = _read("frontend/src/pages/report/report-center-layout.css")

    metric_main = styles.split(".report-workbench .report-status-kpi-row .metric-main {", 1)[1].split("}", 1)[0]
    title_row = styles.split(".report-workbench .report-status-kpi-row .metric-title-row {", 1)[1].split("}", 1)[0]
    metric_value = styles.split(".report-workbench .report-status-kpi-row .metric-value {", 1)[1].split("}", 1)[0]
    metric_note = styles.split(".report-workbench .report-status-kpi-row .metric-note {", 1)[1].split("}", 1)[0]

    assert "min-height: 0;" in metric_main
    assert "grid-template-columns: minmax(0, 1fr) auto auto minmax(0, 1fr);" in metric_main
    assert "grid-template-rows: auto minmax(0, 1fr);" in metric_main
    assert "grid-column: 1 / -1;" in title_row
    assert "grid-column: 2;" in metric_value
    assert "grid-column: 3;" in metric_note
    assert "margin-top: 0;" in metric_note
    assert "white-space: nowrap;" in metric_note


def test_report_right_rail_bottom_edges_close_with_the_center_preview():
    styles = _read("frontend/src/pages/report/report-center-layout.css")

    daily_scroll = styles.split(".report-workbench .report-main-grid .report-side-scroll {", 1)[1].split("}", 1)[0]
    daily_timeline = styles.split(".report-workbench .report-main-grid .report-timeline-card {", 1)[1].split("}", 1)[0]
    review_scroll = styles.split(".report-workbench .report-review-side .report-side-scroll {", 1)[1].split("}", 1)[0]
    review_grid = styles.split(".report-workbench .report-review-info-grid {", 1)[1].split("}", 1)[0]
    review_card = styles.rsplit(".report-workbench .report-small-info {", 1)[1].split("}", 1)[0]

    assert "display: flex;" in daily_scroll
    assert "padding-bottom: 0;" in daily_scroll
    assert "width: 100%;" in daily_timeline
    assert "height: 100%;" in daily_timeline

    assert "display: grid;" in review_scroll
    assert "grid-template-rows: auto minmax(0, 1fr);" in review_scroll
    assert "padding-bottom: 0;" in review_scroll
    assert "height: 100%;" in review_grid
    assert "grid-template-rows: repeat(2, minmax(0, 1fr));" in review_grid
    assert "width: 100%;" in review_card
    assert "height: 100%;" in review_card


def test_report_business_handlers_and_permission_guards_are_unchanged():
    page = _read("frontend/src/pages/report/ReportCenterPage.tsx")

    for handler in (
        "api.generateReport()",
        "api.regenerateReport(activeReport.report_id)",
        "api.approveReport(activeReport.report_id, payload)",
        "api.rejectReport(activeReport.report_id, payload)",
        "api.publishReport(activeReport.report_id, payload)",
        "api.reportDownload(activeReport.report_id)",
    ):
        assert handler in page
    assert "canPerformAction" in page
    for permission in ("report:download", "report.generate", "report:review"):
        assert permission in page
    for label in (
        "下载报告（PDF）",
        "下载报告（Excel）",
        "查看详情",
        "进入审核",
        "重新生成",
        "复制报告链接",
        "归档报告",
        "删除报告",
        "通过",
        "驳回",
        "发布报告",
    ):
        assert label in page

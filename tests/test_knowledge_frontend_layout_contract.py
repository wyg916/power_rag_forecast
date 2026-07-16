from __future__ import annotations

from pathlib import Path


KNOWLEDGE_PAGE = Path("frontend/src/pages/knowledge/KnowledgeBasePage.tsx")
STYLES = Path("frontend/src/styles.css")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_knowledge_page_is_single_workbench_not_tab_stack() -> None:
    content = read_text(KNOWLEDGE_PAGE)

    assert "PageTabs" not in content
    assert "activeSubKey" not in content
    assert "onSubNavigate" not in content
    assert "knowledge-workbench-page" in content
    assert "knowledge-top-workspace" in content
    assert "knowledge-title-block" in content
    assert "knowledge-toolbar-card" in content
    assert "knowledge-kpi-grid" in content
    assert "knowledge-content-grid" in content
    assert "knowledge-search-grid" in content
    assert "knowledge-flow-card knowledge-flow-card-top" in content
    assert 'title="索引流程"' not in content


def test_knowledge_page_uses_existing_real_api_boundaries() -> None:
    content = read_text(KNOWLEDGE_PAGE)

    assert "getKnowledgeBaseData()" in content
    assert "searchKnowledge(text, topK)" in content
    assert "api.knowledgeIndexLocal()" in content
    assert "api.knowledgeEmbeddingRefresh()" in content
    assert "api.knowledgeUpload(file)" in content
    assert "api.knowledgeBatchValidate" in content
    assert "api.knowledgeExport()" in content
    assert "postgresql_kb_documents" in content
    assert "CloudUploadOutlined" in content
    assert "DownloadOutlined" in content
    assert "Button disabled" not in content
    assert "knowledgeMock" not in content


def test_knowledge_page_does_not_render_frontend_mock_or_placeholder_labels() -> None:
    content = read_text(KNOWLEDGE_PAGE)

    forbidden = ["列表接口待接入", "上传接口待接入", "QA 接口待接入", "派生", "兜底数据"]
    for value in forbidden:
        assert value not in content


def test_knowledge_layout_has_responsive_grid_contract() -> None:
    styles = read_text(STYLES)

    assert ".knowledge-workbench-page" in styles
    assert ".knowledge-top-workspace" in styles
    assert ".knowledge-content-grid" in styles
    assert ".knowledge-kpi-grid" in styles
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in styles
    assert "grid-template-columns: minmax(0, 2.25fr) minmax(360px, 0.85fr)" in styles
    assert ".knowledge-search-grid" in styles
    assert "@media (max-width: 1180px)" in styles

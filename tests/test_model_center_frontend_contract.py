from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "src" / "pages" / "model" / "ModelCenterPage.tsx"
SERVICE = ROOT / "frontend" / "src" / "services" / "modelApi.ts"
API = ROOT / "frontend" / "src" / "api.ts"


def test_model_center_page_is_lifecycle_workbench():
    text = PAGE.read_text(encoding="utf-8")
    assert "一体化总览" not in text
    assert "Active 模型" in text
    assert "预测效果对比图" in text
    assert "误差趋势" in text
    assert "候选模型准入规则" in text
    assert "训练状态" in text
    assert "回滚操作" in text
    assert "查看详情" in text
    assert "查看训练日志" in text
    assert "治理记录" in text
    assert "chat" not in text.lower()


def test_model_center_frontend_uses_backend_api_not_mock():
    page = PAGE.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    assert "modelMock" not in page
    assert "modelMock" not in service
    assert "getModelCenterData" in page
    assert "modelCenterOverview" in service
    assert "getModelVersionDetail" in service
    assert "getModelTrainingLogs" in service
    assert "/api/models/center/overview" in api
    assert "/api/models/center/versions/" in api
    assert "/api/models/center/training/start" in api
    assert "/api/models/center/rollback" in api
    assert "/api/tasks/" in api

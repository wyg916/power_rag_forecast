from __future__ import annotations

from backend.app.workers import tasks


def test_python_task_success_updates_status(monkeypatch):
    saved: list[tuple[str, dict]] = []

    def fake_save(record, status=None, log_text=None):
        saved.append((status or record.get("status"), record))
        return True

    monkeypatch.setattr(tasks, "save_task_record", fake_save)
    result = tasks._run_python_task(
        task_id="task_success",
        run_id="run_success",
        kind="knowledge_import",
        payload={},
        handler=lambda payload: {"available": True, "result_ref": "ok"},
    )
    assert result["status"] == "success"
    assert result["progress"] == 100
    assert result["worker_id"]
    assert [item[0] for item in saved] == ["running", "success"]


def test_python_task_failure_updates_status(monkeypatch):
    saved: list[tuple[str, dict]] = []

    def fake_save(record, status=None, log_text=None):
        saved.append((status or record.get("status"), record))
        return True

    def fail(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "save_task_record", fake_save)
    result = tasks._run_python_task(
        task_id="task_failed",
        run_id="run_failed",
        kind="embedding_refresh",
        payload={},
        handler=fail,
    )
    assert result["status"] == "failed"
    assert result["error_message"] == "boom"
    assert result["progress"] == 100
    assert [item[0] for item in saved] == ["running", "failed"]


def test_business_python_task_handler_receives_context(monkeypatch):
    saved: list[tuple[str, dict]] = []
    logs: list[dict] = []

    def fake_save(record, status=None, log_text=None):
        saved.append((status or record.get("status"), record))
        return True

    def fake_log(task_id, **kwargs):
        logs.append({"task_id": task_id, **kwargs})
        return True

    def handler(payload, context):
        context.log("predict", "执行模型预测", progress=55, metadata={"payload": payload})
        return {"available": True, "run_id": "task_price_test", "result_ref": "forecast_results"}

    monkeypatch.setattr(tasks, "save_task_record", fake_save)
    monkeypatch.setattr(tasks, "append_task_log", fake_log)
    monkeypatch.setattr(tasks, "update_task_runtime_state", lambda *args, **kwargs: True)
    result = tasks._run_python_task(
        task_id="task_price_predict",
        run_id="run_price_predict",
        kind="price_predict",
        payload={"horizon": 24},
        handler=handler,
    )
    assert result["status"] == "success"
    assert result["metadata"]["result"]["run_id"] == "task_price_test"
    assert any(item["step"] == "predict" for item in logs)
    assert saved[-1][1]["result_ref"] == "forecast_results"

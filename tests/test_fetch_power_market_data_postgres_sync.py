from __future__ import annotations

import scripts.import_stage1_raw_data_to_postgres as stage1_importer

import fetch_power_market_data as fetcher


def test_stage1_postgres_sync_skips_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POWER_MARKET_SYNC_STAGE1_POSTGRES", raising=False)

    result = fetcher.sync_stage1_raw_to_postgres()

    assert result["status"] == "skipped"
    assert result["reason"] == "disabled"


def test_stage1_postgres_sync_calls_importer_without_leaking_url(monkeypatch, capsys):
    calls = {}

    def fake_run_import(dry_run: bool, replace: bool, limit: int | None):
        calls.update({"dry_run": dry_run, "replace": replace, "limit": limit})
        return {
            "status": "ok",
            "total_rows": 3,
            "results": [
                {"table": "raw_market", "rows": 1, "status": "ok"},
                {"table": "raw_weather", "rows": 1, "status": "ok"},
                {"table": "raw_load", "rows": 1, "status": "ok"},
            ],
        }

    monkeypatch.setenv("DATABASE_URL", "unit-test-database-url")
    monkeypatch.setenv("POWER_MARKET_STAGE1_REPLACE", "0")
    monkeypatch.setenv("POWER_MARKET_STAGE1_LIMIT", "10")
    monkeypatch.setattr(stage1_importer, "run_import", fake_run_import)

    result = fetcher.sync_stage1_raw_to_postgres()

    assert result["status"] == "ok"
    assert calls == {"dry_run": False, "replace": False, "limit": 10}
    output = capsys.readouterr().out
    assert "unit-test-database-url" not in output

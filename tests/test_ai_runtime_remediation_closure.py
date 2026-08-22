from __future__ import annotations

from scripts.chatbi_contract_gate import evaluate


def test_chatbi_catalog_and_golden_50_contract_gate() -> None:
    result = evaluate()
    assert result["status"] == "PASS"
    assert result["catalog"]["missing_contract_fields"] == []
    assert result["golden"]["question_count"] == 50
    assert result["golden"]["passed_count"] == 50
    assert all(result["golden"]["required_coverage"].values())
    assert result["golden"]["raw_sql_execution_by_llm"] == 0

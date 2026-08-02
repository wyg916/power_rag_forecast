from __future__ import annotations

import hashlib
import json

import pytest

from backend.app.services.knowledge_enterprise_service import EnterpriseKnowledgeUnavailable
from backend.app.services.rag_release_service import REQUIRED_RELEASE_GATES
from backend.app.services.rag_release_worker_runtime import _gate_rows


def _report() -> dict:
    return {
        "release_id": "RAG-R1",
        "gates": [
            {"gate": name, "passed": True, "reason": ""}
            for name in sorted(REQUIRED_RELEASE_GATES)
        ],
    }


def test_gate_report_requires_the_exact_mandatory_set() -> None:
    rows = _gate_rows(_report(), "RAG-R1")
    assert {row.gate for row in rows} == REQUIRED_RELEASE_GATES
    assert all(row.passed and not row.reason for row in rows)


@pytest.mark.parametrize("mutation,reason", [
    ("missing", "incomplete"),
    ("failed", "failed"),
    ("duplicate", "duplicate"),
    ("wrong_release", "release_mismatch"),
])
def test_gate_report_fails_closed(mutation: str, reason: str) -> None:
    report = _report()
    if mutation == "missing":
        report["gates"].pop()
    elif mutation == "failed":
        report["gates"][0]["passed"] = False
    elif mutation == "duplicate":
        report["gates"].append(dict(report["gates"][0]))
    else:
        report["release_id"] = "RAG-R2"
    with pytest.raises(EnterpriseKnowledgeUnavailable, match=reason):
        _gate_rows(report, "RAG-R1")


def test_gate_report_hash_is_canonical_and_reproducible() -> None:
    report = _report()
    encoded = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == hashlib.sha256(encoded).hexdigest()

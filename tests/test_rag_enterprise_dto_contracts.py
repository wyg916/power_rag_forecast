from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.knowledge_enterprise_contracts import (
    AccessPolicyContract,
    CitationContract,
    IngestionCreateRequest,
    QAEvaluationContract,
    contract_schema_bundle,
)


HASH = "a" * 64


def _citation(**changes):
    values = {
        "document_id": "doc-1",
        "version_id": "version-1",
        "chunk_id": "chunk-1",
        "release_id": "RAG-R1",
        "page": 1,
        "section_path": ["第一章"],
        "char_start": 0,
        "char_end": 4,
        "bbox": (0.0, 0.0, 10.0, 10.0),
        "asset_id": None,
        "quote": "证据文本",
        "content_hash": HASH,
    }
    values.update(changes)
    return values


def test_client_ingestion_contract_rejects_tenant_override_and_bad_acl():
    payload = {
        "filename": "policy.pdf",
        "media_type": "application/pdf",
        "size_bytes": 10,
        "content_sha256": HASH,
        "idempotency_key": "upload-0001",
        "acl": {"visibility": "tenant"},
    }
    assert IngestionCreateRequest.model_validate(payload).filename == "policy.pdf"
    with pytest.raises(ValidationError):
        IngestionCreateRequest.model_validate(payload | {"tenant_id": "other"})
    with pytest.raises(ValidationError):
        AccessPolicyContract(visibility="restricted")


@pytest.mark.parametrize(
    "changes",
    (
        {"char_start": 4, "char_end": 4},
        {"bbox": (10.0, 0.0, 0.0, 10.0)},
        {"bbox": (0.0, 0.0, 1.0, 1.0), "page": None},
        {"content_hash": "bad"},
    ),
)
def test_citation_locator_is_strict(changes):
    with pytest.raises(ValidationError):
        CitationContract.model_validate(_citation(**changes))
    assert CitationContract.model_validate(_citation()).version_id == "version-1"


def test_qa_confidence_is_numeric_not_a_numeric_string():
    payload = {
        "evaluation_id": "eval-1",
        "tenant_id": "default",
        "release_id": "RAG-R1",
        "question_id": "q-1",
        "passed": True,
        "confidence": 0.97,
        "citations": [_citation()],
        "latency_ms": 12.5,
        "run_id": "run-1",
        "trace_id": "trace-1",
    }
    assert QAEvaluationContract.model_validate(payload).confidence == 0.97
    with pytest.raises(ValidationError):
        QAEvaluationContract.model_validate(payload | {"confidence": "0.97"})
    with pytest.raises(ValidationError):
        QAEvaluationContract.model_validate(payload | {"citations": []})


def test_json_schema_bundle_is_versioned_and_request_has_no_tenant_field():
    bundle = contract_schema_bundle()
    assert bundle["contract_version"] == "rag-enterprise-api/v1"
    assert len(bundle["schema_sha256"]) == 64
    request_schema = bundle["schemas"]["IngestionCreateRequest"]
    assert "tenant_id" not in request_schema["properties"]
    assert request_schema["additionalProperties"] is False

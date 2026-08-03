# Test Summary

## Governance tests

- Command scope: `tests/test_rag_r1_candidate_ai_acceptance.py` and `tests/test_rag_r1_candidate_acceptance.py`
- Result: `18 passed in 2.14s`
- Exit code: 0

## JSON and schema

- Strict JSON files: 12
- Duplicate keys: 0
- Retrieval questions: 50; critical: 15
- AI questions: 100; critical: 30
- Review batches: retrieval 25+25; AI 25+25+25+25; critical 30
- Batch union and source SHA-256: PASS
- Manifest status: `PENDING_HUMAN_APPROVAL`

## Static scans

- Sensitive findings across accepted 20 files: 0
- Exact question ID/text constants and question-specific branches: 0
- Answer hardcoding: not found; critical threshold lowering: false

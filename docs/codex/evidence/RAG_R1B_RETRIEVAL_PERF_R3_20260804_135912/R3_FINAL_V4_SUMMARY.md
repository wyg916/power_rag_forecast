# RAG-R1B Retrieval Performance R3 Audit-Closed Final Evidence

## Decision

- Status: **RETRIEVAL PERFORMANCE NOT PASS**
- Controller handoff: **DO NOT HAND OFF**
- Starting HEAD: `63fc9fc67172681665e97dbf71e54cf1d617a9a4`
- Scope: frozen development 40 only. Hidden 10 and full 50 were not read.
- Final matrix: four scenarios complete; aggregate gate `FAIL`.
- Per-scenario gate: 18/20 checks passed.
- Failed checks: warm/cold P95 over 1500 ms and frozen expected-evidence/top-5 contract conflict.
- Database writes: 0. Qdrant writes: 0. Alias, snapshot, release, and publication actions: 0.

## Frozen and runtime identity

- Development SHA-256: `0ed7f294607504c83c4c566135d8cf3eccea1c466aa5d6bc439a5b2880e65a6d`
- Manifest SHA-256: `123c8cf57034c8b59dfaf477d8626945255a3f94dda5609103e4275818829c49`
- Candidate corpus SHA-256: `ed5f62ad50a36207ca7d0e729ae2bfb054e276b40816d8ac1da04eb376468ed7`
- Candidate: `RAG-R1 / rag_chunks_RAG-R1 / 8339`
- Embedding: BGE large zh v1.5, 1024 dimensions.
- Reranker: BGE reranker v2 m3, `sha256:2a581f058542bd175695f8f92097b7aa4fbdac637ad486739f26e4cbc11ca159`.
- Effective runtime: PyTorch CPU FP32, batch 8, max length 64, 3 rerank candidates, 8/1 Torch threads.
- Evaluator protocol SHA-256: `07962fdcc6a996d5a30f10edf506bd997c1c4689f181bf402eac5d9998302323`.

## Before and final latency

| Scenario | Baseline P50 | Baseline P90 | Baseline P95 | Final P50 | Final P90 | Final P95 | Final P99/max |
|---|---:|---:|---:|---:|---:|---:|---:|
| cold miss | 3325.033 | 5488.295 | 8461.506 | 1531.174 | 2086.865 | 2547.360 | 15239.505 |
| warm miss | 3445.336 | 5691.513 | 5886.746 | 1468.384 | 1839.457 | 2324.463 | 3101.324 |
| cold hit | 2913.821 | 5183.507 | 5341.315 | 1176.121 | 1798.797 | 2614.966 | 8819.648 |
| warm hit | 2941.114 | 5108.694 | 5726.469 | 1168.722 | 1818.762 | 2111.111 | 2652.433 |

Warm cache-miss P95 improved by 3562.283 ms (60.51%) but remains 824.463 ms over the 1500 ms gate.

## Warm cache-miss stage P95

| Stage | Baseline ms | Final ms |
|---|---:|---:|
| auth / ACL | 1.874 | 1.358 |
| query embedding | 704.313 | 495.947 |
| sparse | 164.500 | 106.635 |
| dense | 144.059 | 108.142 |
| Qdrant wall | 591.010 | 147.708 |
| RRF | 1.190 | 0.580 |
| duplicate merge | 0.417 | 0.212 |
| parent expansion | 0.179 | 0.034 |
| content security | 19.394 | 19.363 |
| reranker | 5236.838 | 1404.092 |
| citation hash | 1.083 | 0.677 |
| PostgreSQL metadata | not measured | CONTROLLER_READ_ONLY_METADATA_PENDING |
| serialization | 0.241 | 0.200 |
| cache bookkeeping | 0.156 | 0.127 |

Sparse and dense execute concurrently; their percentiles must not be summed.

## Quality and security

- All four scenarios: R@3 100%, R@5 100%, MRR 94.58%, critical 12/12, structural Citation 100%.
- Baseline MRR was 95.83%; final MRR is lower by 1.25 percentage points but remains above the 85% gate.
- All four scenarios: ACL negative probes 40/40 blocked, tenant leakage 0.
- All four scenarios: malicious-content probes 3/3 blocked.
- All four scenarios: pipeline errors 0, Qdrant writes 0, Secret scan matches 0, Admin Key loaded 0.
- All four scenarios: actual runtime environment allowlist enforced; unapproved environment key count 0.
- R3 disables dotenv autoload, removes non-allowlisted inherited environment values before evaluation, and restores the prior process environment in `finally`.
- R3 programmatic gold/evaluate APIs require an explicit runtime profile. CLI cache writes are limited to the final output evidence directory.
- Process isolation, unique nonces, prewarm state, cache flags, runtime identity, result signatures, ACL signatures, security evidence, and collection identity all passed.
- Golden expected-chunk full coverage is 40.00%, average 50.71%. Five frozen questions require more than five expected chunks; maximum is nine. The evaluator correctly fails closed instead of relabeling this as Citation PASS.

## Real blockers

1. The approved runtime is CPU-only Torch. The formal three-candidate reranker has warm-miss stage P95 1404.092 ms, leaving no compliant headroom for embedding, Qdrant, ACL, security, Citation, and serialization within a 1500 ms end-to-end gate.
2. The frozen expected-evidence contract cannot be fully represented in top five for five questions. The performance branch did not change answers or lower this gate.
3. PostgreSQL read-only metadata reconciliation remains `CONTROLLER_READ_ONLY_METADATA_PENDING`.

Further progress requires a controller-approved accelerated runtime (CUDA-enabled Torch or approved ONNX/OpenVINO runtime and artifacts), followed by the same development-40 protocol. Hidden-10/full-50 remain controller-only.

## Raw evidence

- Final matrix: `final_v4_audit_closed_fp32_t8_b8_l64_c3_development40_matrix.json`, SHA-256 `21e9e35e302f68dee12c2cc2c713924cb854b0d9a908b88d4768601daee0f1d9`
- Cold-hit child: `final_v4_audit_closed_fp32_t8_b8_l64_c3_development40_matrix.cold-hit-child.json`, SHA-256 `9af510ef8bc64a5441bdfcb6fae1292fe7116da08abdb185e86f7a3d1c4928c9`
- Baseline matrix: `baseline2_63fc_development40_matrix.json`, SHA-256 `1975ae9067faf6962e1e8f5c77d91a6207d278cd14d74938fe989d398bb2435d`

The raw reports remain in the worktree evidence directory. The compact evidence JSON is committed for durable review without embedding caches or secrets.

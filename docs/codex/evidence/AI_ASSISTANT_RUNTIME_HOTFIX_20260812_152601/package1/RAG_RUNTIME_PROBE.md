# RAG-R1 预生产候选运行探针

## 配置契约

```text
available=True
issues=()
target_mode=preproduction_candidate
release_id=RAG-R1
collection=rag_chunks_RAG-R1
alias=
access_mode=read_only
candidate_evidence=True
```

## 真实只读查询

```text
available=True
reason=
request_count=1
candidate_count=5
release_id=RAG-R1
target_mode=preproduction_candidate
collection=rag_chunks_RAG-R1
qdrant_wall_ms=2015.937
```

探针仅加载获批只读 Qdrant 配置，未输出密钥，未向后端注入 Admin Key，未创建、更新、删除集合/点位/alias/snapshot。

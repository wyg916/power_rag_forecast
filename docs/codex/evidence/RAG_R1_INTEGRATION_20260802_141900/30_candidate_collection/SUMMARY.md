# RAG-R1 Candidate Collection 正式构建证据

## 结论

`PASS`（仅 Candidate Collection）。当前并非 Published release，`rag_chunks_current` 未切换，Qdrant snapshot 未创建，PostgreSQL 未写入。

- Qdrant：`1.18.2`
- Collection：`rag_chunks_RAG-R1`
- 状态：`green`
- Point：`8,339`
- Dense：`dense` / `1024` / `Cosine` / BGE-large-zh-v1.5 / normalized
- Sparse：`bm25` / `8,298` 个有词项点 / `41` 个 dense-only 点
- Payload indexes：`22/22`
- Strict mode：启用
- Alias：`rag_chunks_current` 不存在，前后均为 `null`
- Snapshot：`0`
- Read-only smoke：dense `PASS`，BM25 `PASS`

## 不可变输入与产物

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `candidate_corpus.json` | 8,613,984 | `ed5f62ad50a36207ca7d0e729ae2bfb054e276b40816d8ac1da04eb376468ed7` |
| `candidate_build_report.json` | 26,263 | `b1da669260a326e0dba8063fe4ec12a300fe0adda30500cf096eddcdf87bcbe1` |
| `candidate_release_envelope.json` | 8,615,168 | `fd421477cee67f5b373a113741dbd9b16a87d6a63ddf6c5220720dcbf020ddfa` |
| `bm25_profile.json` | 1,053,719 | `4f266825b56adba835e5b76dedbeaf5bec8f2bc2ba0340ba05fa2cf8e88cec16` |
| `embedding_manifest.json` | 14,741 | `21c0b28bb7887b9bb96f857e81f8c227ecb5bf06738d63855b2ce1268eb2e3cd` |
| `candidate_collection_report.json` | 2,043 | `6158284cb08e9e7b95248c1ba2cea2f974c2d53349db394531b5dd382061e39e` |

Embedding 分片共 `66` 个、总计 `35,124,700` 字节；manifest 内部哈希为 `09a00a33f7ea0e859a1237ccdc6353a3e3cb5c6e311c25ff920a51dd416e39c0`，chunk `8,339`，维度 `1,024`，模型 manifest `a6854a4b265bc6c7159d02927ece3548e63e7b57cf49deee2a77b94bbb0ec3fa`。

Collection 输入哈希：`8cec3d8630dd5ce3693dddc261b5926d174b1522b49c7cae053326f408b96be7`。

## 正式运行与幂等门禁

1. 初次正式上传完成 `8,339/8,339`，最终顺序 scroll 因 E 盘长尾读取超时而 fail-closed；未生成当前脚本的 PASS 结论。
2. 将审计改为确定性 UUID 批量 retrieve，并以 Collection 精确点数联合证明无未知点、无缺失；5xx 仅允许有限对半拆分，最小 64 仍失败即终止。
3. 发现重跑重复 `PUT payload index` 会持有 segment 写锁；修复为严格校验既有索引类型，仅创建缺失索引。
4. 单一正式复跑完成初始 ID 审计 `8,339/8,339`、幂等 upsert `8,339/8,339`、最终 ID 审计 `8,339/8,339`、snapshot/alias 边界及 read-only dense/BM25 查询。
5. 20:17 已有另一合格运行写入不可变报告；当前实现未覆盖文件，而是逐字段验证全部核心事实并接受已验证旧 schema。最终再次完整复跑返回：`{"alias_after": null, "collection": "rag_chunks_RAG-R1", "phase": "upload", "point_count": 8339, "release_id": "RAG-R1", "status": "PASS"}`。

定向回归：`23 passed`；`py_compile`、`git diff --check`、敏感字段值检查均通过。扫描只命中环境变量名和 HTTP header 键，未输出任何 Key 值。

## Qdrant 运行边界

- 镜像：`qdrant/qdrant:v1.18.2@sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c`
- 容器 image id：`sha256:e13294053db80229932ca53f6ace97c3da1ae2581b770373e187a15707244eb5`
- E 盘挂载：`storage`、`snapshots`、`tls`
- 外部网络调用：`0`
- Admin Key 仅用于 Candidate 写入；正式查询 smoke 使用 Read-only Key；Key 值未进入证据或 Git。

## 已知风险与下一步

Docker Desktop 对 E 盘 bind mount 给出“无法保证数据安全”的文件系统警告，当前保持 `PASS_WITH_RISK`；数据未损坏，但正式发布前必须生成并验证 Qdrant snapshot 和 PostgreSQL snapshot。

下一步是 PostgreSQL Candidate 元数据与 release items，随后接入 API/认证/AI/UI、评测、全量回归、双快照、alias 原子切换及回滚演练。生产切换仍为 `NO`。

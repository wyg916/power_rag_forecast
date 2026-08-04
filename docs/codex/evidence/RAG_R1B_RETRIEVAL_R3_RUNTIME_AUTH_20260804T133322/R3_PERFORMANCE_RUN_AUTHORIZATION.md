# RAG-R1B 检索性能 R3 运行授权

状态：`R3 DEVELOPMENT AUTHORIZED / LIVE PASS PENDING`。

## 接收边界

- `63fc9fc67172681665e97dbf71e54cf1d617a9a4` 仅登记为性能实验检查点。
- 接收状态：`PENDING`；来源提交 live 验收：`NOT EXECUTED`；P95：`NOT PROVEN`；主控接收：`NO`。
- 主控没有 cherry-pick、merge、rebase 或改写该提交。

## Candidate 与 Qdrant

- release：`RAG-R1`，状态 `candidate`，`is_current=false`。
- Collection：`rag_chunks_RAG-R1`；8,339 points；22 个 payload 索引；dense 1024；sparse `bm25`。
- Qdrant：1.18.2，TLS/HTTP health、strict mode、无 Key 拒绝、只读 Key 可读不可写均 PASS。
- alias 目标仍为 NULL；snapshot 数量 0；Candidate 状态 SHA 未变化。
- Git 外只读配置：`E:\智能运营分析项目_运行资产\rag-r1\performance\r3-qdrant-readonly.env`。该文件包含只读 Key，不含 Admin Key、数据库密码或完整数据库 DSN；不得复制到 Git、日志或报告。

## PostgreSQL

- 主控以强制只读事务验证 `RAG-R1` release 与 Qdrant Collection、BGE 1024 profile 一致，数据库写入 0。
- 当前本地 `.env` 的 PostgreSQL 身份是 `postgres` 超级用户，不能作为最小权限身份交给性能任务。
- 新建持久只读角色的操作未获安全门禁授权，因此 PostgreSQL Secret/DSN 不注入 Ultra；R3 中 PostgreSQL metadata 阶段由主控代跑并复核。
- 这不是对“最小权限 PostgreSQL 身份”的 PASS 声明；不得在报告中改写为已注入专用只读账号。

## 冻结 50 题

- 状态：`AI_SURROGATE_GOLD_STANDARD_FROZEN_PENDING_FORMAL_REVALIDATION`。
- 固定字段：`human_verified=false`、`automated_consensus_verified=true`、`verification_mode=multi_agent_independent_consensus`。
- manifest：`docs/codex/evidence/RAG_R1B_GOLDEN_AI_CONSENSUS_20260804T023000/retrieval_consensus_manifest.json`；文件 SHA-256 `123c8cf57034c8b59dfaf477d8626945255a3f94dda5609103e4275818829c49`。
- 开发 40 题：`retrieval_development_40.json`；SHA-256 `0ed7f294607504c83c4c566135d8cf3eccea1c466aa5d6bc439a5b2880e65a6d`。
- 隐藏 10 题：`retrieval_hidden_10.sealed.json`；SHA-256 `55368d9a5eadadd6c84d6ac3e31bb2704e3d3d2eb8534d1e683af7bd044cddab`。
- 全 50 题主控副本：`retrieval_ai_consensus_50.json`；SHA-256 `1e526ee2f4c2feda72a27c52fdc08b68888fccd02be2302110e45c1e2674df7e`。
- Ultra 调优期间只可读取 manifest 与开发 40 题；不得读取隐藏 10 题或全 50 题答案。隐藏集与最终全 50 题复验由主控执行。
- 题集覆盖 tenant、ACL、Citation、critical 与拒答；不得依据失败结果修改黄金答案。

## 固定机器与运行时

- CPU：Intel i7-9750H，6C/12T；内存 17,095,184,384 bytes。
- GPU：GTX 1660 Ti 6 GiB，驱动 610.62；但当前 PyTorch 为 `2.12.1+cpu`、CUDA 为 NULL。
- 允许运行时：现有 Python 3.11.9、CPU-only PyTorch、Transformers 4.57.6、sentence-transformers 3.4.1。
- 未授权安装新 CUDA/ONNX/INT8 运行时或依赖；不得换机器制造 PASS。

## R3 边界与最终门禁

- 严格遵守 `docs/codex/tasks/16_RAG_R1B_RETRIEVAL_PERFORMANCE.md` 白名单。
- 禁止修改数据库、迁移、公共配置、Compose、公共 API、黄金答案、release、alias 或 snapshot；禁止发布。
- 不得跳过 reranker、ACL、Citation，不得只测缓存命中，不得缩小正式题量。
- R3 应先在开发 40 题完成优化并提交新的独立提交；主控再执行隐藏 10 题和全 50 题四象限复验。
- 正式报告必须包含 cold miss、warm miss、cold hit、warm hit，P50/P90/P95/P99/max 和全部阶段耗时。
- 最终门槛保持 P95 ≤1.5s、R@3 ≥90%、R@5 ≥98%、MRR ≥85%、critical 100%、Citation 100%、ACL 不退化。
- 当前结论保持：`RETRIEVAL PERFORMANCE NOT PASS`。

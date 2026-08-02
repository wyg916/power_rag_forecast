# RAG-I6 Candidate 发布交接包证据

## 基线与范围

- I6 前提交：`0d24fdc3009325b763b1e6df5b0724082c2e6af9`。
- 指定主线 `beta10d/day4-data-access-security@0ee5c617` 无冲突合并，合并提交：`8222c506a70eaa3a7ee15829ce209b60d6fd2e1f`。
- E 盘检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_194303_RAG_I6_PRE`。
- I6 范围：交接模块、对应测试、pipeline 依赖声明和本证据，共 4 个文件；实现与测试 600 个物理行、523 个非空行，另有 1 行依赖声明，低于 800 行上限。

## 实现结果

- 新增版本化 `rag-candidate-release-envelope/v1`，显式携带 tenant/release、三类 frozen schema、ledger/corpus/manifest/artifact SHA-256、完整 Embedding approval identity、七类计数及原始 I5 Candidate artifact。
- 从序列化 ledger 与 I5 artifact 重新计算并交叉校验全部交接哈希；重新执行 frozen manifest JSON Schema 校验，不接受调用方摘要。
- 交叉校验 ledger 状态、source partition、document/version、Chunk/Asset 引用、内容/quote hash、隔离/重复规则和所有计数；任一不一致整体 fail-closed。
- Embedding approval 独立注入并固定 BGE Large 1024；provider/model/approved version/dimension/model SHA/sparse profile 全部进入 envelope。
- sink port 必须返回严格 receipt：tenant、release、envelope hash、stored=True；None、错 hash、跨租户、未存储或异常均拒绝。
- 未知构建或 sink 异常只返回稳定脱敏错误码，不保留路径、内容或原始异常链。
- `knowledge_pipeline/requirements.txt` 显式固定既有环境版本 `jsonschema==4.26.0`；本任务仅补充声明，未安装、下载或联网。

## 测试

- I6 定向：`11 passed in 0.52s`。
- 全部 `test_rag_enterprise_*.py` 回归：`200 passed in 4.57s`。
- 覆盖确定性、四级 hash 篡改、schema/计数篡改、跨租户、profile mismatch、sink 异常和 receipt 四类伪成功。

## 外部影响与回滚

- 仅使用 synthetic fixture 和内存 sink；未处理 83 份正式资料，未写 `.runtime`、PostgreSQL、Qdrant、模型、网络或正式文件。
- I6 使用普通 `git revert <I6-commit>` 回滚；主线合并提交可独立审计和回滚。无外部状态需要恢复。

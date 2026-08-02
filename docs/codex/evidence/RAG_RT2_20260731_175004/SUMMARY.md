# RAG-RT2 实施证据摘要

## 范围

- 分支：`codex/rag-enterprise-runtime`
- 基线：`d24c7df88a4863ab4ef1f36bd7fce554532dff43`
- 前置检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_173711_RAG_RT2_PRE`
- 本包仅实现发布感知的只读向量存储契约、混合检索核心和企业模式拒绝旧旁路。

## 实现结果

- `qdrant_vector_store.py`：以注入 transport 隔离客户端依赖，Collection 仅从 `ReleaseIdentity` 派生。
- 查询强制带 tenant、release、published、有效期、ACL 和 embedding profile 过滤，返回 payload 再次校验。
- 资源 ACL 指纹仅作为非空审计字段；实际授权按 tenant 与 public/user/roles 判定，避免误拒公开或多 ACL 文档。
- Dense 查询拒绝 NaN、Inf 和全零向量，统一返回 `query_embedding_invalid` 且不触发 transport。
- `hybrid_retrieval_service.py`：实现 Dense/Sparse/Structured 召回、稳定 RRF、版本级去重、动态 K、父块扩展和权限隔离缓存键。
- `rag_service.py`：企业模式只允许新版 store；缺上下文、证据或契约不一致时返回 unavailable。
- `vector_index_service.py`：企业模式拒绝 NPZ 本地向量索引构建与查询。
- 正式链路未接入 PostgreSQL 扫描、本地文件 fallback、Seed、Hash Embedding 或启发式 rerank。

## 测试证据

- 新增纯函数/fake transport 测试：`12 passed in 0.42s`。
- RT1、RT2 与相关 RAG/API 回归：`72 passed, 2 deselected in 8.01s`。
- ACL 指纹语义及非法 Dense 向量修复后，主线独立复核 RT1/RT2/契约/权限：`47 passed`。
- 覆盖 tenant/ACL/release/profile 过滤、只读无写、缓存隔离、稳定 RRF、动态 K、父子块、无证据拒答和企业模式旧旁路封锁。
- 两项 deselected 为基线既有陈旧断言：旧混合检索样本缺 `domain`；旧上传测试仍期望 analyst 写权限，而当前安全契约要求 reviewer。
- 临时目录位于工作树 `.codex_tmp`，未写 C 盘。

## 未触达与风险边界

- 未联网、未下载或加载模型、未安装 `qdrant-client`。
- 未连接 PostgreSQL/Qdrant，未执行迁移、Compose、外部服务调用或密钥操作。
- 未修改 API 契约、公共配置、前端和权限矩阵。
- 本包验证的是 transport 契约和检索语义；真实 Qdrant 适配、配置注入、API 上下文注入及模型实测由后续串行集成包完成。

## 回滚

- 提交后使用 `git revert <RAG-RT2-commit>` 回滚本包。
- 如需核对提交前状态，使用上述 E 盘检查点中的 `RESTORE.md`、Git 状态和文件哈希证据。
- 本包无数据库、向量集合、模型或外部状态变更，无需数据恢复。

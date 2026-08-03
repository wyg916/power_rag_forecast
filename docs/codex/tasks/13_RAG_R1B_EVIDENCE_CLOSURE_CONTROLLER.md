# RAG-R1B 证据闭环主控任务

## 目标

以 `beta10d/rag-r1-final-integration` 的已验收代码树为权威实现，将
`beta10d/rag-r1-integration` 纳入可追溯提交祖先，建立唯一 RAG-R1B 集成工作线，并隔离 OCR、黄金集、检索性能三个并行任务。

## 主控专属权限

只有主控可以修改正式 PostgreSQL、迁移、公共配置、Compose、公共 API 契约，执行 merge/cherry-pick，创建 snapshot，切换 alias，更新 release 状态或发布。

## 基线决策

- `beta10d/rag-r1-final-integration` 包含发布 worker、发布 API、候选检索/AI 验收器、受治理 UI 与最终门禁，是权威代码树。
- `beta10d/rag-r1-integration` 保留更早的平行实现、过程证据和凭据回显阻断记录，不把已被权威实现替代的文件重新叠加。
- 主控使用双父 merge 提交记录两条来源历史；merge 后代码树必须与 final-integration 精确同 tree。
- 三个并行任务必须从主控交接时公布的同一基线 HEAD 创建，不得自行 rebase、merge 或 cherry-pick。

## 当前发布边界

- Release 保持 `candidate` / `is_current=false`。
- 不创建 Qdrant snapshot，不切换 `rag_chunks_current` alias。
- 不发布、不生产切换、不进入原 Day 9/Day 10。
- 三项证据门禁全部通过前，主控也不得改变上述状态。

## 回滚

- Git：对主控新增提交执行 `git revert`，禁止 reset。
- 凭据：已回显旧密码不得恢复；故障时再次生成新密码并同步 Git 外受限配置。
- 数据库：本准备任务只轮换 `beta10d_app_login` 密码并终止旧会话，不修改 ACL、结构或业务数据。


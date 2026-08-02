# RAG-R1 AI Claim/Citation 集成收口

- 状态：`PASS`（仅 AI 与企业检索契约；Candidate 仍未发布）。
- `/api/ai/rag-answer`、主 Chat、流式 Chat 与 Agent Analyze 均接入服务端认证派生的 enterprise retrieval context；客户端通过 Body、Query 或 Header 覆盖 `tenant_id` 均被拒绝。
- AI 统一返回 `answer`、`claims`、`citations`、`grounding_status`、`refusal_reason`、`release_id`、`trace_id`、`degraded_components`。
- 知识型回答只从已完成 locator/hash 校验的 Citation 构造 Claim；每个 Claim 必须绑定现有 Citation ID，引用缺失、伪造或篡改时 fail closed 并拒答。
- 普通响应只返回不透明 `trace_id`，不返回原始 Trace；Collection、Provider、模型路径、Key、内部诊断原因均未暴露。
- 确定性数字型经营问题继续以受控业务工具作为事实源；补充 RAG 证据不会进入其公开 Claim/Citation，也不能覆盖 SQL/预测工具答案。
- 当前真实状态仍为 `RAG-R1/candidate/is_current=false`。受限数据库身份的真实 API 冒烟返回 200 + `release_unavailable`，Claims/Citations 为空，Qdrant transport 构造 0 次，Candidate Collection 未查询。
- 三张 RAG 运行审计表冒烟前后计数均为 `[0,0,2]`，持久化写入 0；数据库、Qdrant、alias、snapshot、Published 与生产切换均未变化。
- 扩大定向回归 `146 passed`；Claim/Citation 聚焦测试 `28 passed`；Python compile、权限矩阵 `--check`、`git diff --check` 和真实敏感值扫描均 PASS。
- 范围：10 个代码/测试文件，697 行有效新增、22 行删除，小于 20 文件/1000 行门禁。

## 尚未收口

- Candidate 仍没有 Published/current 状态，因此真实正向 Qdrant hybrid + AI grounded answer 必须等待全部评测门禁通过和受控发布后验证；本包只验证单元正向路径与当前真实 fail-closed 路径。
- 旧 AI 数据依赖测试需要在其既定数据环境中执行；AssistantPage 复制标签契约属于下一 UI 任务包。两项均保留到对应阶段，不据此宣称 RAG-R1 总体完成。
- Candidate 评测、snapshot、受控发布、alias 原子切换与回滚演练均尚未执行。

## 回滚

- 代码和任务状态：对本任务原子提交执行 `git revert <commit>`。
- 数据库：本包持久化写入为 0，无数据库恢复动作。
- Qdrant：本包未查询 Candidate Collection、未切 alias、未写 collection、未生成 snapshot，无 Qdrant 回滚动作。

# Package 1 — 运行时总控修复验收

- 基线：`fefb72f6c56e387a10bd2a4d798813593f1f2334`
- 分支：`hotfix/ai-assistant-runtime-providers-20260812`
- 状态：PASS
- 改动文件数：14（业务/启动代码 12、运行时路由 1、专属测试 1）
- 有效增删：411 行增加、44 行删除；未超过单包 20 文件/1000 行限制。

## 验收结果

1. 运行时路由已覆盖 `GENERAL_CHAT / CHATBI / RAG_QA / BUSINESS_ANALYSIS / BUSINESS_ADVICE / REPORT_GENERATION`，普通闲聊与日期问题不再前置依赖 RAG。
2. AnalysisPlan 可规范化 provider message、`reasoning_content`、JSON fence、包装对象、camelCase 与 tool-call arguments；首次校验失败仅执行一次带 schema/错误信息的定向修复。
3. 自动生成的非法计划转为明确 unavailable；用户显式提交的非法计划继续保持 422 fail-closed 契约。
4. 非显式记忆问题允许 PostgreSQL 记忆读写故障降级，响应标记 degraded components；显式记忆操作仍 fail-closed。
5. 预生产模式只读直连候选集合 `rag_chunks_RAG-R1`，不读取或切换 production alias；候选证据固定校验 8,339 points、1024 维、candidate 状态与 alias before/after 均为空。

## 测试证据

- 定向与受影响矩阵：`71 passed, 4 skipped`；4 项均为既有 `isolated PostgreSQL gate only` 条件跳过。
- RAG 运行契约：`available=True`、`issues=()`、`target_mode=preproduction_candidate`、`alias=''`、`access_mode=read_only`。
- RAG 真实只读稀疏查询：`available=True`、`candidate_count=5`、`collection=rag_chunks_RAG-R1`、`target_mode=preproduction_candidate`、`qdrant_wall_ms=2015.937`。
- `git diff --check`：PASS。

## 边界与回滚

- 未执行数据库迁移、业务数据写入、模型切换、RAG alias 切换、snapshot、production cutover、外部 Provider 调用或远程推送。
- 回滚：对本包独立提交执行 `git revert <package1_sha>`；PRE 检查点位于 `backups/phase3/20260812_152601257_AI_ASSISTANT_HOTFIX_PRE`。

# PROJECT1 v2.12.0 Final Integration Stage 2 / C + B 报告

## 结论

- `STATUS=PASS`
- `START_INTEGRATION_SHA=ed5fccdc3f22b5592ff83310fd9ea4ee72b010c9`
- `C_SHA=521f18a9ad651dc1edcf0358a27cc78a35bf6944`
- `C_MERGE_COMMIT=549d5e5129c0393074cb239c45ae14a820953d29`
- `B_SHA=4d1d87463dd4e45f8f01cb15ce958711f6e06099`
- `B_MERGE_COMMIT=ebc08b25626980f2b000c1dfa028f054442f9f42`
- `INTEGRATION_CODE_SHA=aa2114f417ab39534750c7bcc06e73741e7080e0`
- C、B 均使用普通 `git merge --no-ff` 合并；未 squash、未 cherry-pick 子集、未使用 ours/theirs。
- 两次合并冲突均只涉及 `docs/codex/TASK_STATUS.md`，逐段保留各侧事实记录并移除冲突标记；业务代码无冲突。
- C 与 B 合并后发现并修复 6 项真实集成契约偏差，修复提交为 `aa2114f417ab39534750c7bcc06e73741e7080e0`。未回退 A 的预测事实、事务、worker、API、run_id 或 24 行契约。

## 合并轨迹

| 阶段 | 合并前 | 来源 | 合并提交 / 合并后 |
|---|---|---|---|
| C | `ed5fccdc3f22b5592ff83310fd9ea4ee72b010c9` | `521f18a9ad651dc1edcf0358a27cc78a35bf6944` | `549d5e5129c0393074cb239c45ae14a820953d29` |
| B | `549d5e5129c0393074cb239c45ae14a820953d29` | `4d1d87463dd4e45f8f01cb15ce958711f6e06099` | `ebc08b25626980f2b000c1dfa028f054442f9f42` |
| 集成契约修复 | `ebc08b25626980f2b000c1dfa028f054442f9f42` | C+B 实际 E2E | `aa2114f417ab39534750c7bcc06e73741e7080e0` |

`git merge-base --is-ancestor` 已确认 C SHA、B SHA 均为当前集成代码 SHA 的祖先；A SHA `3aa38348d5822f69c21dd8aee93a6ac0ade00001` 也保持在历史中。

## C 合并后定向回归

- A+C 后端组合：`293 passed, 33 skipped, 1 deselected`，无失败。
- 正式 Celery forecast：任务 `task_9c97f4b48e8b` 完成 `PENDING/ACCEPTED -> RUNNING -> SUCCESS`；run `run_20260822T151950727645Z_6be184a0a1` 为 `success`，结果 24 行、partial 0。
- 幂等复投：`task_6598dc89e0a6` 使用同一 idempotency key，回指同一 run，返回 `idempotent=true`，run/result/batch/snapshot 计数不变。
- 重启后 API 回读：run、24 results、两个 task、report、strategy、strategy reviews、24h 与 dashboard 全部 200；report/strategy/dashboard 均回指同一 run。
- 下游链：report `p5c_operation_decision_run_20260822T151950727645Z_6be184a0a1`；strategy `p5d_ef26b5b4289d4dbb7736d2d7` 已 submit/approve，review=2；历史/stale 发布被正确阻断。
- Provider：MiMo 普通文本、MiMo Vision、DeepSeek 复杂文本及受控 AnalysisPlan、用户明示 Kimi Premium 均完成真实调用；未发生意外 Premium，fallback 为 0。
- ChatBI：50/50 Golden；AnalysisPlan schema 50/50；LLM 任意 SQL 执行 0。
- 启动控制：status/logs/doctor 均返回 0，doctor `ok=true`，默认可见控制台 1；未停止既有 8000/5173。

## B+C 实际前后端联调

集成 E2E 首次暴露并关闭以下偏差：

1. B 上传附件未携带 C 冻结的 multipart `session_id`，实际请求返回 422；现已在上传与轮询中保持 session scope。
2. AI 请求构造器丢失 `premium_confirmed`、`model_provider` 和 `answer_style`；现只在用户明确选择 Premium 时确认升级。
3. 本地 `AUTH_REQUIRED=0` 时前端绕过真实 permission manifest；现仍加载 `/api/auth/me` 并按后端 capability 限制菜单、路由、Tab、卡片、按钮和请求。
4. 用户取消与 Provider 失败共用 error 语义；现取消明确为 `cancelled / 已停止生成`，超时和 Provider 失败仍为错误。
5. 业务来源区的中性更新时间/批次状态被误删；已恢复中性业务语义，仍不显示默认技术追溯块。
6. 权限矩阵的前端消费者行号在集成修复后漂移；已用仓库生成器重新生成 CSV/MD，未手工伪造。

实际附件覆盖 PNG、PDF、DOCX、XLSX、CSV、TXT：POST → parsing → ready → GET → 文件问答 → citation → DELETE → 删除后 410 完整通过；跨用户 404、跨 session 403、跨 tenant 由 C 冻结契约测试覆盖；无效图片解析为明确 424。浏览器实际完成文件选择、Ctrl+V、页面切换会话保持、上下文开关、取消与 Premium 明示；拖拽 handler 由前端事件测试覆盖。隔离 Provider 失败探针返回明确 503 `PROVIDER_UNAVAILABLE`，假成功为 0。

## 权限与 UI

- 实际四角色：系统管理员、运营/交易分析、复核/审核、模型/知识管理员；所有判定来自 `/api/auth/me` 与 `API_PERMISSION_MATRIX`，未按角色名猜测。
- 13 个代表 API 探针全部符合矩阵；5 个后端受控 403 符合预期；raw 403 可见 0，未知未授权请求 0，越权数据读取 0。
- 直接 URL：无权限页面均显示友好拒绝；reviewer 可审核报告但拒绝 ChatBI/附件，analyst 不显示系统设置，developer 的报告审核受控拒绝。
- 当前集成代码 SHA 上浏览器重跑 32 路由 × 1920×1080、1440×900、1366×768、1280×720，共 128/128 通过；Sticky Header 128/128、悬浮 AI 128/128、横向溢出 0、可见副标题 0、默认技术元数据块 0、console error 0、page error 0。

## 测试与已知环境矩阵

- 前端最终门禁：lint `10/10`、unit `26/26`、typecheck PASS、Vite build PASS（3682 modules）。
- 后端最终定向组合：`198 passed, 28 skipped, 1 deselected`，无失败。
- 较宽 31 文件组合曾得到 `312 passed, 33 skipped, 1 deselected, 6 failed`；6 项精确对应 `C_FULL_DIAGNOSTIC_FAILURE_MATRIX.md` 的 `DB-GUARD` 项，使用普通 pytest 时数据库按设计 fail-closed。未删除测试、未扩大 skip、未修改断言。
- C 冻结的 50 项诊断矩阵分类为 `DB-GUARD`、`ISOLATED-RUNNER`、`MODEL-ASSET`。它们不是本阶段 C 引入回归；最终 Full Regression 必须使用正确隔离 fixture 和准入模型资产重新执行，不能把本报告当作最终全量 PASS。

## 边界

- 未更新 main，未创建 Tag，未创建或删除 worktree，未修改普通根目录。
- 未激活生产模型，未切换 RAG production alias，未执行生产切流。
- 只关闭本阶段创建的专用 18080、15174–15177；既有 8000/5173 PID 保持运行。
- 本阶段结论仅允许进入 Final Full Regression；当前候选还不是 `FINAL_SHA`。


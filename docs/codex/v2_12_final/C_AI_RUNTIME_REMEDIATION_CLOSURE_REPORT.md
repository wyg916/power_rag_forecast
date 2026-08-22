# PROJECT1 v2.12.0 — C Remediation Closure Report

## 结论

- 任务：`PROJECT1_V2_12_C_AI_RUNTIME_REMEDIATION_CLOSURE`
- 工作树：`E:\智能运营分析项目_worktrees\project1_v2.12.0_ai_runtime_release`
- 分支：`codex/project1-v2.12.0-ai-runtime-release`
- 起始提交：`94602989f97168de9662efbbd721bac07f014b2c`
- 状态：`PASS`
- 集成就绪：`YES`

## 修复闭环

### 1. 附件生命周期与 B 后端契约

- 保持冻结的 `POST /api/ai/attachments`、`GET /api/ai/attachments/{id}`、`DELETE /api/ai/attachments/{id}`。
- 解析失败立即清除临时二进制、chunks 和 properties；TTL、主动删除与解析中取消使用同一个安全清理路径。
- 删除/取消为幂等终态；删除后 `attachment_ids` 复用返回 `ATTACHMENT_NOT_AVAILABLE`，不会继续进入模型上下文。
- 上传/删除写安全审计，只记录 attachment/session/media/status/size/error code，不记录文件正文、Prompt、磁盘路径或完整响应。
- API 响应仅包含冻结的受控元数据；JWT 身份对象重新生成 tenant/user scope。跨用户与跨租户均为不可枚举 404，跨会话为 403。
- PNG、JPG/JPEG、WEBP、PDF、DOCX、TXT、MD、XLSX、CSV 全部到达 `ready`；文件问答返回 attachment Citation，Prompt Injection 仍只作为不可信数据。

### 2. MiMo Vision

- OpenAI-compatible 适配器支持字符串和 multipart content，正确提取 `text/output_text` 部件，不再把部件数组转成 Python 字符串。
- 诊断结构覆盖 HTTP status、request ID、model、消息部件、图片 MIME、data/remote URL 类型、response keys、finish reason、usage、provider error；不保存正文。
- 真实调用：`mimo-v2.5`、PNG data URL、HTTP 200、非空 content，红/蓝可见证据识别 PASS。原 `empty_response` 阻塞关闭。
- 根因结论：本次真实响应的 content 类型为字符串，未触发 multipart 响应适配，因此上一轮空响应不能归因为 content parser；其可验证根因分类是“供应商瞬时空响应 + 旧探针缺少 HTTP/request/finish/usage 结构证据”。当前同模型、正确 PNG data URL 请求稳定返回有效内容，故不再是发布阻塞。

### 3. DeepSeek AnalysisPlan

- 根因结论：旧 Smoke 使用与真实 Catalog 不一致的示例 ID 和不完整的临时 schema，正式 Planner 同时没有声明 JSON response format/当前 Pydantic schema，形成 Smoke/Prompt/schema drift；修复后首轮又暴露趋势漏 group_by、市场条件漏 filter 的语义遗漏，已通过显式语义约束关闭。
- Planner 请求启用 `response_format=json_object`，Prompt 内提供当前 Pydantic JSON schema，并明确时间、粒度、分组、筛选和图表一致性。
- 仅执行一次确定性 JSON normalize：处理 fence/envelope、常见字段别名、单值列表、可安全归一的 null 列表和 enum 大小写；不扩展 dataset/field/metric/join 白名单。
- JSON/schema 失败或确定性 validator 失败时最多一次 repair；Provider fallback 仍最多一次，Kimi 不参与无感 fallback。
- 真实 DeepSeek 最终 6/6 PASS：单指标、时间范围、维度分组、DOM 筛选、非法字段非执行、无权限数据集以 `dataset_forbidden/metric_forbidden` 拒绝。
- 六次原始结构均为合法 object、无 Markdown fence、无 envelope、无 alias 漂移、无需 repair；LLM 原始 SQL 字段与执行均为 0。

### 4. ChatBI Catalog 与 Golden

- 复核现有 Catalog 已满足稳定 ID、业务名称、描述、源数据集/字段、aggregation/semantic rule、permission、version；无需新增迁移或放宽白名单。
- 当前 Catalog：13 metrics、21 dimensions、2 whitelist joins。
- 新增离线可重复门禁，冻结 Golden 50 为 50/50 PASS（超过最低 20 条），覆盖单指标、时间、维度、筛选、复合、多轮、非法、无权限、空数据、证据不足与歧义。
- 所有计划经 `AnalysisPlan -> Validator`，SQL 契约字段为 0；正式执行链仍为确定性 SQLAlchemy compiler。

### 5. 全量诊断归因

- 起始 SHA 新鲜复现：1010 passed、20 skipped、29 failed、21 errors，433.74 秒。
- 50 项逐项分类：29 项 `DB-GUARD`、8 项 `ISOLATED-RUNNER`、13 项 `MODEL-ASSET`。
- 全部在修改前已存在；本任务未删除测试、未扩大 skip、未修改 frontend/prediction_engine/model_ops，`C_INTRODUCED_REGRESSION=0`。
- 完整矩阵：`C_FULL_DIAGNOSTIC_FAILURE_MATRIX.md`。

## 验证

| 门禁 | 结果 |
|---|---|
| 综合 C/附件/RBAC/Provider/ChatBI/启动回归 | 156 passed / 5 isolated-only skipped |
| 附件 API 与核心生命周期 | 37 passed |
| ChatBI package 1–5 + closure | 52 passed / 5 isolated-only skipped |
| ChatBI 离线 Catalog/Golden | 50/50 PASS；raw SQL 0 |
| MiMo general / vision | PASS / PASS |
| DeepSeek real AnalysisPlan | 6/6 PASS；schema 6/6；repair 0；fallback 0 |
| Kimi explicit Premium | PASS；未确认拒绝 PASS；unexpected usage 0 |
| status / logs / doctor | 全部 exit 0；doctor `ok=true` |
| 默认可见控制台 | 1；silent 设计值 0 |
| Alembic | 唯一 `0022_chatbi_semantic_v1` |
| 权限矩阵 | 207 method-path / 191 unique path / 7 public / 200 protected |
| compileall / diff check / CI YAML | PASS |

## 运行与安全边界

- `status` 继续展示 branch/SHA/tag/PID/port/working directory/health/log path；日志位于 `logs/runtime/<timestamp>/`。
- 8000 PID 24144 与 5173 PID 12856 均为非本控制器来源；本任务仅只读检测，未停止、覆盖或 taskkill。
- 未连接正式数据库、未执行 migration/seed、未反序列化模型、未激活模型、未切 RAG alias、未修改 A/B/main、未创建 Tag。
- 真实 Provider 使用已有 Git-ignore 配置；API Key 未输出、未写证据、未提交。

## 回滚

- 对最终任务提交执行普通 `git revert <task-commit>`；无需 reset/clean/worktree 操作。
- 数据库无变更，无数据库回滚。
- 附件运行态数据位于 Git-ignore 的 user/tenant scope；删除和 TTL 已由幂等清理路径处理。

## Integration 依赖

1. Final Integration 合入 B 后，在同一最终 SHA 执行前端 typecheck/lint/test/build 与附件 UI 端到端联调。
2. Integration 统一处置正式 8000/5173 的进程归属；本 C 分支不终止未知进程。
3. 数据库依赖的 37 项测试使用 Day3 一次性隔离 Schema/受限角色运行器；T002 的 13 项由 A 提供准入模型资产后复验。

当前无 C 代码或真实 Provider 阻塞项。

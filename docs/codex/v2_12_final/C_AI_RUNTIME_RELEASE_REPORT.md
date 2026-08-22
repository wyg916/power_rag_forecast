# v2.12.0 并行任务 C：AI Runtime、附件、启动与工程质量发布报告

## 结论

- 任务：`PROJECT1_V2_12_C_AI_RUNTIME_ATTACHMENTS_STARTUP_QUALITY`
- 工作树：`E:\智能运营分析项目_worktrees\project1_v2.12.0_ai_runtime_release`
- 分支：`codex/project1-v2.12.0-ai-runtime-release`
- 起始提交：`3b6eb33df96ece08a60acce802d6ec249ec5a826`
- 本地实现与最小 CI 门禁：PASS。
- 真实 Provider 冒烟：PARTIAL。MiMo 文本与 Kimi Premium 成功；MiMo 视觉为空响应；DeepSeek 复杂文本成功，但 AnalysisPlan 未返回冻结契约要求的结构。
- 发布判定：`PARTIAL_REMOTE_PROVIDER_BLOCKED`。在 MiMo 视觉与 DeepSeek AnalysisPlan 真实调用复验通过前，`READY_FOR_INTEGRATION=NO`。

## 实现范围

1. 建立五个逻辑模型能力别名：`GENERAL_DEFAULT`、`VISION_DEFAULT`、`DATA_PLANNER`、`COMPLEX_REASONER`、`PREMIUM`。稳定模型 ID 由 registry 集中解析，兼容既有 Provider 模型配置；业务主链不再散落具体版本。
2. 路由固定为 MiMo 通用/视觉、DeepSeek ChatBI/复杂推理、Kimi 显式 Premium。Kimi 不参与静默 fallback；自动 fallback 最多一次。
3. ChatBI 保持“LLM 仅生成 AnalysisPlan → Semantic Catalog/RBAC/白名单/校验 → SQLAlchemy 确定性编译 → PostgreSQL → Result Dataset/数字验证 → 解释”边界，未增加 LLM 原始 SQL 执行路径。
4. 回答策略按意图动态选择 `direct_answer`、`data_analysis`、`rag_answer`、`file_qa`、`vision_analysis`、`action_advice`、`premium_deep_analysis`，移除 `professional_brief` 的机械固定标题。
5. 后端附件链支持 PNG、JPG/JPEG、WEBP、PDF、DOCX、TXT、MD、XLSX、CSV；执行 MIME/扩展名/大小、图片真实性、ZIP/宏/嵌入内容、压缩大小、页/行数、附件 ID 路径安全检查。
6. 附件按 tenant/user/session 隔离，具备 `uploading → parsing → ready|failed`、TTL、主动删除、文件 Citation、视觉输入和不可信内容包裹；不写入企业正式知识库。跨用户与跨租户采用不可枚举的 404，跨会话返回 403。
7. `page_context` 仅接受冻结字段并重新校验页面权限；`/api/security/me` 返回后端 capability manifest。权限矩阵已同步为 207 个方法路径、191 个唯一路径。
8. Trace/usage 记录 requested tier、逻辑别名、Provider、模型、路由原因、fallback、tokens、延迟、估算成本、附件、page context 和 trace_id；429、timeout、5xx、cancel、permission、unsupported、parse failure 具有独立错误语义。
9. 新增统一 `run_project.bat|ps1` 控制入口，支持 `start`、`start-debug`、`status`、`logs`、`stop`、`restart`、`doctor`。Web 与 Celery 日志集中到 `logs/runtime/<timestamp>/`；默认关闭大模型 RAG 预热，可由运维显式开启。
10. 新增最小 CI workflow：离线 AI/附件/权限/ChatBI 契约、单一 Alembic head、敏感文件门禁，以及在 B 分支脚本存在时执行前端 typecheck/lint/test/build。

## 安全与数据边界

- `RAW_SQL_EXECUTION_BY_LLM=0`；未新增任意 SQL 入口，未执行 migration、seed、模型激活或 RAG production alias 切换。
- Prompt Injection 仅作为附件不可信数据标记和包裹，模型系统消息明确禁止执行附件指令。
- CSV/XLSX 公式按文本中和；PDF 活动脚本、Launch、EmbeddedFile 和 Office 宏/嵌入脚本拒绝。
- API Key 未打印、未写报告、未提交；日志仅记录脱敏后的运行信息，不记录附件敏感全文。
- 未修改 `frontend/`、`prediction_engine/`、`model_ops/` 或 forecast 核心逻辑；未触碰 A/B/main、未创建 Tag。

## 验证结果

| 门禁 | 结果 | 证据摘要 |
|---|---|---|
| 最终合并 AI/附件/权限/ChatBI/RC 门禁 | PASS | 165 passed / 5 isolated-only skipped |
| AI/附件/ChatBI 最小 CI 子集 | PASS | 85 passed / 5 isolated-only skipped |
| Provider/权限/附件回归 | PASS | 90 passed |
| Endpoint/附件/Provider 定向 | PASS | 46 passed |
| 启动与附件控制契约 | PASS | 32 passed |
| Python compileall / diff check | PASS | 退出码 0 |
| Alembic head | PASS | 唯一 `0022_chatbi_semantic_v1` |
| 权限矩阵重生成检查 | PASS | 207 method-path / 191 path |
| 独立端口实际启动 | PASS | 18000/15173 + Celery 健康；start/status/stop/final status 均退出 0；最终无残留 |
| 正式端口保护 | PASS | 8000/5173 归属无法精确证明时启动拒绝，未 kill |
| 全量普通 pytest | ENVIRONMENT_BLOCKED | 1010 passed / 20 skipped；到 91% 时累计 29 failed + 21 errors 后按 50 上限停止，均归类为数据库守卫清空连接、isolated-only 或缺失非本任务模型资产 |

全量普通 pytest 的失败不计为任务相关代码 PASS；任务硬门禁由离线契约和受影响回归单独证明。未为消除环境失败伪造数据库数据或模型资产。

## 真实 Provider 冒烟

- MiMo 普通文本：初始最小调用为空响应；一次受控诊断扩大 token 上限后 PASS。
- MiMo 图片/截图：`REMOTE_PROVIDER_BLOCKED`，供应商返回空响应。
- DeepSeek 复杂文本：PASS，真实 tokens/latency 已采集。
- DeepSeek ChatBI/AnalysisPlan：`REMOTE_PROVIDER_BLOCKED`，供应商输出未通过冻结 AnalysisPlan schema；本地结构、校验、编译、无原始 SQL 契约 PASS。
- Kimi Premium：仅在 `requested_tier=premium` 且 `premium_confirmed=true` 时真实调用 PASS；未确认调用 0，静默 Premium 使用 0。
- 除两次明确标记的失败诊断外未重复调用；未输出 API Key。

## 回滚

- 代码：对本任务最终提交执行 `git revert <task-commit>`。
- 运行态：`run_project.ps1 stop` 只停止由状态、PID、创建时间和工作树来源证明为本控制器启动的服务；未知端口所有者拒绝停止。
- 附件：位于 Git ignore 的会话隔离存储，支持按附件主动删除和 TTL；未污染企业知识库。
- 数据库：本任务无 migration、seed、业务写入或模型状态变更，无数据库回滚动作。

## 集成依赖与阻塞

1. B 分支提供/确认前端 `typecheck`、`lint`、`test`、`build` scripts 后，Integration 运行 workflow 的前端 job。
2. Integration 统一确认正式 8000/5173 所有者；本任务未终止现有进程。
3. 复验 MiMo 视觉响应和 DeepSeek AnalysisPlan schema；未通过前真实 Provider 门禁保持 PARTIAL。
4. 若需要全量数据库回归，应使用仓库受限 isolated-schema runner，而不是绕过 pytest 数据库守卫。

## Remediation Closure 更新（2026-08-22）

后续任务 `PROJECT1_V2_12_C_AI_RUNTIME_REMEDIATION_CLOSURE` 已关闭本报告中的两项真实 Provider 阻塞：

- MiMo 普通文本与视觉均真实 PASS；视觉请求为 PNG data URL，HTTP 200、非空 content，并正确识别可见红/蓝证据。
- DeepSeek AnalysisPlan 真实 6/6 PASS，覆盖单指标、时间、维度、筛选、非法字段拒绝和无权限数据集拒绝；schema 6/6，repair 0，fallback 0，LLM 原始 SQL 0。
- Kimi 继续仅在显式 Premium 确认后调用，未确认请求被本地拒绝，意外 Premium 使用 0。
- 附件 POST/GET/DELETE、取消/失败/TTL 清理、删除不可复用、JWT user/tenant 隔离、文件 Citation 与 B 后端契约均 PASS。
- Semantic Catalog 为 13 metrics / 21 dimensions / 2 whitelist joins；冻结 Golden 50 为 50/50 PASS。
- 综合 C 门禁 156 passed / 5 isolated-only skipped；起始 SHA 全量 50 项失败已逐项归因，`C_INTRODUCED_REGRESSION=0`。

本报告原先的 `PARTIAL_REMOTE_PROVIDER_BLOCKED` 历史结论保留用于审计，但已由 `C_AI_RUNTIME_REMEDIATION_CLOSURE_REPORT.md` 的当前 `PASS / READY_FOR_INTEGRATION=YES` 判定取代。

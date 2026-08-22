# 项目一 v2.12.0 验收矩阵

## 1. 判定规则

- `PASS` 只表示本行列出的当前 SHA、当前命令和当前证据通过。
- A/B/C 的 PASS 是集成候选，不是最终版本 PASS。
- 最终 `LOCAL_FINAL_RC_PASS` 必须来自一个且仅一个 `FINAL_SHA`。
- 历史 v2.11.2 的 1119 后端 passed、230/230 前端契约和 32/32 路由仅作为回归下限，不作为 v2.12.0 的新鲜结果。
- 任一假成功、越权、跨租户召回、LLM 任意 SQL、静默 Premium、不可追溯来源或不可恢复改动均为硬失败。

## 2. Bootstrap 门禁

| 项目 | 标准 | 证据 |
|---|---|---|
| 基线 | path/branch/SHA/tag/clean 精确匹配；upstream 0/0 | Bootstrap 终端与外置备份 |
| 仓库备份 | 全 refs bundle 创建、verify PASS、SHA256 已记录 | 外置 E 盘时间戳备份 |
| 普通根目录 | tracked/staged diff、untracked 清单、逐文件副本和 SHA256 | 外置 E 盘时间戳备份 |
| 端口 | 8000/5173/6379/6333 的 PID、进程树和归属只读记录；未停止实例 | 端口盘点证据 |
| 契约与所有权 | 本目录 7 个种子文件已提交 | `INTEGRATION_SEED_SHA` |
| 并行环境 | A/B/C 同一 seed、clean、配置不跟踪、Python/Node/test discovery 可用 | worktree 验证摘要 |

## 3. A 核心 P0

| 验收域 | 最低标准 |
|---|---|
| 模型事实 | PostgreSQL 唯一可查询事实；model/version/hash/feature hash/schema/role/status 可追溯 |
| 输入契约 | 特征缺失/额外/顺序/type/timezone/schema hash 不一致 fail-closed |
| 真实任务 | 正式 forecast worker：ACCEPTED → RUNNING → SUCCESS |
| 结果 | 恰好 24 行；0 半成品；同 run 幂等；失败事务回滚 |
| 持久性 | 刷新和服务重启后可回读；旧批次共存 |
| 下游一致性 | dashboard/forecast/strategy/report 同 `run_id`、model、input batch、source |
| 禁止项 | fallback/Mock/固定值假成功=0；Active/RAG alias/生产切流=0 |
| 回归 | 相关后端测试无新增失败/无解释 skip；Alembic Head 唯一 |

## 4. B UI/RBAC/AI Shell

| 验收域 | 最低标准 |
|---|---|
| 路由与视口 | 32/32 路由；1920/1440/1366/1280 四视口；无不受控横向溢出 |
| 设计系统 | 统一 tokens、PageShell、StickyPageHeader、Toolbar、Card/Table/Status |
| 信息减法 | 业务副标题=0；默认业务视图技术元数据块=0；后端审计字段未删除 |
| 权限 | 4 类角色；无权限菜单/Tab/卡片/按钮不显示；已知无权限请求=0 |
| 错误体验 | 原始 403 权限代码堆叠=0；整页/局部权限状态友好；后端仍为安全边界 |
| AI Shell | 允许路由全覆盖；切页会话/草稿/附件/流状态不丢；小屏可用 |
| 多元输入 | 选择/拖拽/截图粘贴/浏览器 File 粘贴边界/删除/重试/取消明确 |
| 工程 | TypeScript、Vite、ESLint、最小 Vitest、浏览器 Console/Page/Request 门禁 |

## 5. C AI Runtime/Release

| 验收域 | 最低标准 |
|---|---|
| 路由 | 五逻辑别名；MiMo/DeepSeek/Kimi 规则正确；Premium 明示；最多一次受控 fallback |
| ChatBI | LLM 仅生成 `AnalysisPlan`；确定性校验与 SQLAlchemy 编译；任意 SQL=0 |
| 附件 | 图片/PDF/DOCX/TXT/MD/XLSX/CSV；会话临时作用域、TTL、隔离、状态和引用 |
| Trace | 请求、会话、运行、trace、provider/model、route、fallback、tokens、延迟、成本、引用齐全 |
| 失败语义 | 401/403、无证据、解析失败、429/timeout/5xx、取消均显式；假成功=0 |
| capability | 当前用户 route/action manifest 可供前端消费；后端逐接口 RBAC 不放松 |
| 启动 | 默认可见控制台 ≤1；start/debug/status/logs/stop/restart/doctor；不杀未知 PID |
| CI | 最小可重复门禁；不连接正式库、不使用真实密钥、不执行生产切换 |

## 6. Final Integration 同 SHA 门禁

| 域 | 硬门禁 |
|---|---|
| Git/版本 | clean、来源提交可追溯、无秘密/大文件、唯一 Alembic Head |
| 核心业务 | 预测 SUCCESS、24 行、幂等/回滚/重启回读、全链同 run |
| AI | 通用 10、NL2SQL 10、RAG 10、视觉 5、文件 8、Premium 5、异常 ≥6 类 |
| 安全 | 任意 SQL=0、越权召回=0、意外 Premium=0、假成功=0 |
| 权限 | 4 角色 × 32 路由；友好失败；跨租户=0 |
| UI | 32 路由 × 4 视口；悬浮助手、附件、粘贴、会话保持通过 |
| 工程 | 后端 passed 不低于 1119、0 failed/error；前端四门禁；契约不低于 230 |
| 运行 | 冷启动、幂等二次启动、受控停机、再启动、PID/路径/SHA 来源完整 |

生产 TLS、正式密钥托管、容量/灾备、外部审批、模型 Active、RAG production alias 与生产流量始终标记 `NOT_EXECUTED`，不得纳入本地 RC PASS。

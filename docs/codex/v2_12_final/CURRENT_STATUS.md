# 项目一 v2.12.0 当前状态

## Bootstrap 种子状态

| 字段 | 值 |
|---|---|
| Task | `PROJECT1_V2_12_MASTER_BOOTSTRAP_AND_PARALLEL_ORCHESTRATION` |
| Stage | `BOOTSTRAP_SEED` |
| Baseline check | PASS：path/branch/SHA/tag/clean 精确匹配；cached ahead/behind 0/0 |
| Baseline SHA | `736a39719613a9b14b5f9c94b83e727271764f98` |
| Baseline tag | `project1-v2.11.2-local-final-rc-20260816` |
| Backup | E 盘外置时间戳目录；bundle verify 与普通根目录逐文件哈希已执行 |
| Integration | `codex/project1-v2.12.0-final-integration` |
| Interface contract | FROZEN |
| File ownership | FROZEN |
| Business implementation | NOT_STARTED |
| Production go-live | NOT_EXECUTED |

本文件描述种子提交时的状态。精确 `INTEGRATION_SEED_SHA`、M2 worktree 创建结果、端口 PID 和最终 `PARALLEL_READY` 以同一 Bootstrap 对话的最终结构化输出与外置证据为准；这是为了避免在 Git commit 内容中自引用其自身 SHA。

## 已确认基线事实

- v2.11.2 后端历史权威回归：1119 passed、34 skipped、0 failed/error；仅作为 v2.12.0 回归下限。
- 预测任务生命周期已闭环，但真实预测业务仍因 PostgreSQL 可用模型事实缺口进入 FAILED；A 负责关闭。
- 历史 32/32 页面和四视口通过；B 必须在 v2.12.0 新鲜复验，不能复用历史 PASS。
- 模型 Active 晋升、RAG production alias、生产 TLS/密钥/容量/灾备/审批均不在 Bootstrap 范围。
- Bootstrap 不实现 A/B/C 业务内容，不关闭端口进程，不写数据库，不加载模型二进制。

## 端口只读事实

- `8000`：监听进程属于项目 Python 运行链，但 Win32 未直接暴露工作目录；不得仅凭端口复用为新 worktree 实例。
- `5173`：命令行指向冻结基线 worktree 的 Vite；Bootstrap 不停止。
- `6379`：Docker Desktop 转发，容器标签指向冻结基线 compose 的 Redis。
- `6333`：Docker Desktop 转发，容器标签指向历史 RAG integration worktree 与外置运行资产。

## 下一状态

只有三个任务 worktree 均满足路径/分支/HEAD/clean、配置未跟踪、Python/Node 可用和测试命令可识别，Bootstrap 才能在最终输出中给出 `PARALLEL_READY=YES`。之后应停止 Bootstrap，并分别在 A/B/C worktree 打开独立任务对话。

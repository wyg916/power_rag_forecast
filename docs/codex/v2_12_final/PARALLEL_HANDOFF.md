# 项目一 v2.12.0 并行任务交接

## 1. Bootstrap 结论

权威基线已通过路径、分支、HEAD、Tag、clean、cached ahead/behind 和 remote 核验。普通根目录用户改动已外置备份，端口只读盘点完成，冻结基线未修改。本目录定义的接口契约、文件所有权、环境方法和验收矩阵是 A/B/C 的共同输入。

精确 `INTEGRATION_SEED_SHA` 由 Bootstrap 最终输出提供。由于 commit 不能在自身内容中写入自身 SHA，任务分支必须用最终输出值和自身 `git rev-parse HEAD` 双重核验；不得猜测或改用基线 SHA。

## 2. 工作树

| 任务 | 分支 | 路径 |
|---|---|---|
| Integration | `codex/project1-v2.12.0-final-integration` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_final_integration` |
| A | `codex/project1-v2.12.0-core-p0` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_core_p0` |
| B | `codex/project1-v2.12.0-ui-rbac-ai-shell` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_ui_rbac_ai_shell` |
| C | `codex/project1-v2.12.0-ai-runtime-release` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_ai_runtime_release` |

## 3. 每个任务开工前

1. 读取 `AGENTS.md`、`PROJECT_BASELINE_SUMMARY.md`、`MASTER_ENGINEERING_RULES.md` 和对应任务文件。
2. 读取本目录全部 7 个冻结文件。
3. 输出 path/branch/HEAD/status；HEAD 必须等于 Bootstrap 最终输出的 `INTEGRATION_SEED_SHA`，工作树必须 clean。
4. 核对 `.env` 为 ignored/untracked，Python/Node 共享依赖可用；不得打印值。
5. 建立自己的 E 盘可恢复检查点和证据目录后再修改。

## 4. 任务摘要

### A

只关闭预测、模型事实、forecast worker 和核心业务事实链。必须产生真实 24 行 SUCCESS、幂等、失败回滚、重启回读和下游同 run 证据。禁止 frontend、AI runtime、启动脚本和 CI。

### B

只负责 `frontend/**`、前端 API client/type 和前端测试。实现全站设计系统、权限友好化、全局 AI 悬浮助手及附件交互，但不得用 Mock/静态成功替代后端缺口。凡涉及 UI 重构，必须先加载项目 `p6-ui-rebuild` 技能并完成其前置检查。

### C

负责后端 AI/ChatBI/model gateway、附件、RBAC capability、启动控制面、CI 和相关测试。落实五逻辑别名、三 Provider、Premium 明示、受控 fallback、AnalysisPlan、Trace/Citation 和显式失败。禁止 frontend 与预测引擎。

## 5. 端口与运行来源

- `5173` 当前命令行指向冻结基线 Vite；不停止、不作为新 worktree 来源证明。
- `8000` 当前是项目 Python/uvicorn 运行链，但工作目录未由 Win32 直接暴露；不作为新 worktree 来源证明。
- `6379` 为冻结基线 compose 的 Redis 容器映射。
- `6333` 为历史 RAG integration compose 与外置运行资产的 Qdrant 映射。

任务不得关闭或重启这些实例，除非后续用户在精确来源和影响说明后另行授权。需要测试时使用受控隔离端口或由 Final Integration 统一安排。

## 6. 提交与交付

- 小提交；最终 worktree clean。
- 禁止 merge/cherry-pick 其他任务、更新 main、创建正式 Tag、删除资产。
- 交付必须包含 base SHA、final SHA、改动文件、测试、回滚、阻塞和 `READY_FOR_INTEGRATION=YES|NO`。
- `READY_FOR_INTEGRATION=YES` 仍不代表 v2.12.0 PASS；Final Integration 是唯一合并和最终同 SHA 验收负责人。

## 7. Final Integration 入口条件

只有 A/B/C 都为 `READY_FOR_INTEGRATION=YES`、三个工作树 clean、所有改动均在 `FILE_OWNERSHIP.md` 范围、无秘密/异常大文件/未知生成物时才可开始。合并顺序固定为 A → C → B；任何冲突必须以冻结契约为准并重新跑受影响门禁。

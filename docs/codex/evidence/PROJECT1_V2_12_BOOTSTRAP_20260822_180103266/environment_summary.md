# 环境与端口摘要

## 端口来源（只读）

| 端口 | PID/容器 | 已证明来源 | Bootstrap 处理 |
|---|---|---|---|
| 8000 | PID 24144，父 PID 31176 | `uvicorn backend.app.main:app`；父可执行文件来自普通根目录共享 `.venv`；精确 worktree 工作目录不可由 Win32 证明 | 不停止，不复用 |
| 5173 | PID 12856 | Node/Vite 命令行明确指向冻结基线 `frontend` | 不停止，不复用 |
| 6379 | Docker Desktop 转发；`power-trading-ai-redis-1` | 容器 compose working_dir 指向冻结基线；running/healthy，PING=PONG | 只读健康验证 |
| 6333 | Docker Desktop 转发；`power-trading-ai-rag-r1-qdrant-1` | 容器 compose working_dir 指向历史 RAG integration；running，TCP 可达 | 只读连通验证 |

## 本地配置

- 普通根目录 `.env` 存在，Git ignored/untracked；只记录了文件 SHA256 和键名，不记录值。
- 外置数据库、Qdrant runtime、模型 profile 配置存在；只记录文件存在性和键名类别。
- 四个新 worktree 均安全同步 `.env`，目标 SHA256 与源一致，且 Git 状态保持 clean。
- Python `.venv`、前端 `node_modules` 与外置运行资产均位于 E 盘；不依赖冻结基线临时文件。

## Worktree 身份

| 角色 | 分支 | 路径 | HEAD | 状态 |
|---|---|---|---|---|
| Integration | `codex/project1-v2.12.0-final-integration` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_final_integration` | 种子后仅增加 Bootstrap 证据提交 | clean（提交后复核） |
| A | `codex/project1-v2.12.0-core-p0` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_core_p0` | `3b6eb33df96ece08a60acce802d6ec249ec5a826` | clean |
| B | `codex/project1-v2.12.0-ui-rbac-ai-shell` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_ui_rbac_ai_shell` | `3b6eb33df96ece08a60acce802d6ec249ec5a826` | clean |
| C | `codex/project1-v2.12.0-ai-runtime-release` | `E:\智能运营分析项目_worktrees\project1_v2.12.0_ai_runtime_release` | `3b6eb33df96ece08a60acce802d6ec249ec5a826` | clean |

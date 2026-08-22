# 项目一 v2.12.0 Worktree 环境设置

## 1. 环境原则

- 不在冻结基线 worktree 创建虚拟环境、安装依赖或写临时配置。
- 不自动联网安装，不修改系统级环境变量，不在 C 盘创建项目依赖。
- Python、Node 依赖优先复用 Git common worktree `E:\智能运营分析项目` 已批准的 E 盘资产。
- 敏感配置只复制到 Git 忽略文件或继续引用 E 盘外置受控配置；不得提交、打印值或写入证据。
- 每个 worktree 必须独立证明配置路径和依赖，不依赖冻结基线 `.codex_tmp`、output 或临时 PID 文件。

## 2. 已盘点依赖来源

| 能力 | 来源 | 使用方式 |
|---|---|---|
| Python | `E:\智能运营分析项目\.venv\Scripts\python.exe` | 启动脚本会从 Git common worktree 自动解析；任务命令可显式调用 |
| Node | `D:\DevTools\nodejs\node-v24.18.0-win-x64` | 使用已安装 Node/npm，不全局安装包 |
| 前端依赖 | `E:\智能运营分析项目\frontend\node_modules` | 每个新 worktree 的 `frontend/node_modules` 使用目录联接复用 |
| PostgreSQL | `localhost:5432/postgres` | 只使用获批本地配置；预检只读；变更任务另建检查点与回滚 |
| Redis | Docker `power-trading-ai-redis-1` / `127.0.0.1:6379` | 只在来源和健康可证明时由启动器复用；Bootstrap 不写队列 |
| Qdrant | Docker `power-trading-ai-rag-r1-qdrant-1` / `127.0.0.1:6333` | 使用 TLS + 只读 Key 的受控配置；不切 alias、不写生产集合 |
| 模型/RAG 资产 | `E:\智能运营分析项目_运行资产\...` | 只按任务授权读取；Bootstrap 不反序列化模型 |

## 3. 本地配置清单

下列只记录路径、存在性和键名类别；精确哈希在 Bootstrap 外置证据中。不得把值粘贴到文档或终端。

| 文件 | Git 状态 | 键名类别 | 同步策略 |
|---|---|---|---|
| `E:\智能运营分析项目\.env` | ignored/untracked | DB、Redis/Celery、LLM Provider、RAG、JWT | 安全复制为各新 worktree 根 `.env`；复制后 `git check-ignore` 必须 PASS |
| `E:\智能运营分析项目_本地配置\beta10d_day4_runtime.env` | Git 外 | `DATABASE_URL`、`SECURITY_DATABASE_URL` | 启动器按 Git common root 自动引用，不复制 |
| `E:\智能运营分析项目_运行资产\rag-r1\qdrant\secrets\runtime.env` | Git 外 | Qdrant root/port/image、admin/read-only key、release/collection | 启动器自动引用；不打印值，不提交 |
| `E:\智能运营分析项目_运行资产\rag-r1\qdrant\secrets\model-profile.env` | Git 外 | embedding/rerank/model/TLS/alias/profile | 启动器自动引用；不打印值，不提交 |
| `deploy/rag-r1/preproduction-profile.env` | Git tracked | 预生产非秘密参数 | 随 seed 正常存在，不另复制 |

`.env` 同步要求：源/目标 SHA256 必须一致；目标 `git ls-files --error-unmatch .env` 必须失败；`git check-ignore .env` 必须成功。任何失败立即停止，不得 `git add -f`。

## 4. 每个任务 worktree 的安全准备

```powershell
$sharedRoot = 'E:\智能运营分析项目'
$taskRoot = '<TASK_WORKTREE>'

Copy-Item -LiteralPath "$sharedRoot\.env" -Destination "$taskRoot\.env"
New-Item -ItemType Junction `
  -Path "$taskRoot\frontend\node_modules" `
  -Target "$sharedRoot\frontend\node_modules"

git -C $taskRoot check-ignore --quiet -- .env
git -C $taskRoot check-ignore --quiet -- frontend/node_modules
```

如果目标文件/目录已存在，禁止覆盖；先核对类型、SHA、归属和 Git 状态，无法证明时停止。上述 junction 只复用依赖，不复制或修改 `node_modules`。

## 5. 只读依赖验证

Python：

```powershell
E:\智能运营分析项目\.venv\Scripts\python.exe --version
E:\智能运营分析项目\.venv\Scripts\python.exe -c "import fastapi, sqlalchemy, celery, pytest; print('PYTHON_IMPORTS=PASS')"
```

Node：

```powershell
node --version
npm --version
node -e "require('./frontend/node_modules/vite/package.json'); console.log('NODE_DEPS=PASS')"
```

PostgreSQL/Redis/Qdrant：

- PostgreSQL 使用 `pg_isready` 或项目 `web_platform_launcher.py --preflight-only`；不得输出 DSN。
- Redis 只执行健康/PING，不发布任务、不清队列。
- Qdrant 使用 Docker health 或项目只读 probe；不得创建/删除 collection、snapshot、alias 或 point。
- 端口有监听不等于 worktree 环境可用；必须记录 PID/容器标签和来源。

## 6. 现有测试命令识别

每个 worktree 至少确认以下入口存在；Bootstrap 不跑业务全量测试：

- 后端：共享 Python 运行时执行 `python -m pytest`，配置由仓库 pytest 配置文件解析。
- 迁移：共享 Python 运行时执行 `python -m alembic heads`。
- 前端：`frontend/package.json` 的 `dev`、`build`、`preview`；基线未配置 lint/test，B/C 后续按所有权补齐。
- 前端 type/build：在 `frontend` 中运行 `npm run build`，使用 worktree 的目录联接依赖。
- 启动：`run_project.bat`、`run_web_platform.bat`；Bootstrap 只做入口识别和 preflight，不启动/停止现有服务。

## 7. 清理与回滚

- 不删除共享 `.venv`、`node_modules`、`.env`、外置配置、Docker volume、模型或 RAG 资产。
- 若需撤销本轮环境，只能在用户确认后逐个移除本轮明确创建的 `.env` 副本或目录联接；不得递归清理。
- Git 工作内容由本轮外置 bundle 和普通根目录 patch/untracked 副本恢复；数据库影响为 `none`。

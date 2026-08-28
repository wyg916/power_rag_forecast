# 智能运营分析项目

> 当前最新本地工作版本唯一入口：`E:\智能运营分析项目`，分支 `main`。请在该目录双击 `run_project.bat`；启动器会在 Web 健康后打开系统默认浏览器。历史目录 `E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807` 仅保留旧 RC，不包含当前主线的最新修改。

当前正式版本标签：`v2.12.1`；`main` 还包含标签后的已审批本地改进，实际启动提交以启动器输出的 Git SHA 为准。这是基于 FastAPI、React/Vite、PostgreSQL、Redis/Celery 和 Alembic 的智能电力运营分析与决策支持平台。

后台自动化可使用 `run_project.ps1 start -Silent`（不会打开浏览器）；维护与诊断分别使用 `run_project.bat menu`、`run_project.bat doctor`。

## 可复现运行基线

- Python：`3.11.x`
- Node.js：`>=18 <25`
- npm：`>=9 <12`
- PostgreSQL：应用目标为 PostgreSQL；当前本地工程约束使用 `localhost:5432/postgres`
- 前端容器构建基线：Node 18
- 最新 Alembic 版本：`0022_chatbi_semantic_v1`

依赖安装、配置生成、迁移、启动、健康检查和回滚步骤统一见 [README_DEPLOY.md](README_DEPLOY.md)。生产模式必须启用认证、使用随机 JWT/数据库密钥并完成受控管理员初始化；示例占位值不能直接用于部署。

## 最短本地验证

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic heads
cd frontend
npm ci
npm run build
```

不要提交 `.env`、`.env.docker`、数据库密码、API Key、模型二进制或本地构建产物。

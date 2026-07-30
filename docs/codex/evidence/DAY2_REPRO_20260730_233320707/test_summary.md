# Day 2 全新环境复现、迁移回放与配置闭环报告

## 结论

`PASS`

Day 2 的 20 项验收标准全部满足。项目可以从 Git 干净 clone，在不继承原目录未提交文件、原 `.venv`、原 `node_modules`、原 `dist` 或缓存的前提下完成依赖安装、配置生成、隔离迁移回放、后端启动、前端构建与只读核心验收。具备进入 Day 3 的工程准入条件，但本次未开始 Day 3。

## 1. 起止分支与提交

- Day 1 基线分支：`beta10d/day1-trusted-baseline`
- Day 1 基线 HEAD：`583a185ef089943bdb55a270e010e79cf1c3cfe3`
- Day 2 分支：`beta10d/day2-reproducible-environment`
- 运行验收候选 HEAD：`97dcd5091692710407f7b977b0713733fc1124bb`
- 初始只读门禁：分支、HEAD、干净工作树、Alembic 单 head `0016_strategy_runtime`、Day 1 报告可读，全部 PASS。

## 2. 检查点与验证目录

- 前置检查点：
  `E:\智能运营分析项目_备份\beta10d\20260730_233152624_DAY2_REPRO_PRE`
- 验证根目录：
  `E:\智能运营分析项目_验证\beta10d_day2_20260730_233320707`
- 后端/迁移 clone：`...\repo`
- 最终前端 clone：`...\repo_frontend2`
- 两个最终 clone 均 fast-forward 到运行验收候选 HEAD，`git status --porcelain` 为空。
- clone 后未继承 `.env`、`.env.docker`、`.venv`、`node_modules`、`dist` 或原目录缓存。

## 3. 环境

- Python：3.11.9，全新 `.venv`
- pip：26.2
- Node：v24.18.0
- npm：11.16.0
- Docker：26.0.0
- Docker Compose：v2.26.1-desktop.1
- PostgreSQL：18.4，`localhost:5432/postgres`
- Redis：`localhost:6379`

## 4. 配置模板修复

- `.env.example`：PostgreSQL 为主；MySQL 仅标记为遗留导入用途；数据库 fallback、LLM、自动拉取、RAG 和文件 fallback 默认关闭。
- `.env.docker.example`：所有敏感值为明显占位符；生产认证默认开启；管理员必须由受控流程初始化；LLM/RAG 默认关闭。
- 主 Compose：数据库密码改为必填，不再提供弱默认值；LLM/RAG/fallback 默认关闭。
- 企业 Compose：认证、JWT、管理员和数据库密码均 fail-closed；Redis 仅绑定本机；健康接口与 Celery app 路径修正。
- 前端：明确 Node `>=18 <25`、npm `>=9 <12`，lock 与 package 一致。
- 新增只读 `scripts/day2_repro_preflight.py`，覆盖运行时、配置、迁移静态审计、端口、Git 干净状态和可选数据库门禁。
- 生产弱 JWT/未初始化管理员配置退出码 1；随机强密钥与 `ADMIN_INITIALIZED=1` 配置退出码 0。
- 高置信敏感信息扫描：新增行 0 命中；未提交实际 `.env` 或真实密钥。

## 5. Docker Compose

- 主版示例环境：`docker compose ... config --quiet`，退出码 0。
- 企业版示例环境：`docker compose ... config --quiet`，退出码 0。
- 未启动完整 Compose：`8080`、`18000` 已被其他项目占用，按任务规则避免干扰外部服务。

## 6. 临时 Schema 与角色

预演：

- Schema：`beta10d_day2_20260731_000000`
- Role：`beta10d_day2_20260731_000000_role`

最终全新 clone 回放：

- Schema：`beta10d_day2_20260731_004000`
- Role：`beta10d_day2_20260731_004000_role`

两角色均为 NOLOGIN，且无 superuser、createdb、createrole、replication、bypassrls 权限；不能在 `public` 创建对象，不能写关键业务表。Schema owner 与角色精确匹配。

## 7. 迁移结果

- 静态审计 16 个迁移文件：均含 upgrade/downgrade；未发现 `public.` 硬编码、`DROP DATABASE`、系统目录写入或直接篡改 `alembic_version`。
- Alembic 仅允许安全标识符、非 `public`、受控前缀；支持独立 `version_table_schema` 和受限执行角色；目标 host/port/database/user 可 fail-closed 校验。
- 空 Schema → `0016_strategy_runtime`：PASS。
- `0016_strategy_runtime` → `0014_t003_run_transaction`：PASS。
- `0014_t003_run_transaction` → `0016_strategy_runtime`：PASS。
- `0014` 状态：58 表；0015/0016 新增的 4 张表、38 个 `strategy_advice` 字段、3 个索引及检查约束均已撤销。
- 两次 head：62 表、8 视图、47 序列、236 索引、451 约束。
- 两次 head 逻辑结构 SHA-256 均为：
  `3d7ad406d97637d4a60c791b66174db75f5076eb26f8ef4dad7e5928f9e9114b`
- 哈希契约使用表内相对列顺序、名称、类型、空值、默认值、约束、索引、视图和序列；排除 PostgreSQL drop/re-add 后无业务语义的绝对 `attnum` 间隙。
- 预演暴露并修复了 Alembic 隐式 SET 事务未提交问题；最终又发现并移除重复入口调用，相关回归 19 passed。

## 8. `public` 与业务数据保护

- Day 2 前 `public`：62 表、8 视图、47 序列、37 函数，Alembic `0016_strategy_runtime`。
- 前置与预演后完整结构/视图/序列/函数/版本/12 张关键表内容指纹全部一致。
- 最终回放角色无 `public` 写权限；最终回放后及临时对象清理后：
  - `public` 对象计数一致；
  - Alembic 版本一致；
  - 12 张关键表存在性与行数一致；
  - Day 2 临时 Schema/角色残留均为 0。
- 未对 `public` 执行迁移、downgrade、seed 或业务 DML。

## 9. 后端全新环境

- `requirements.txt` 全量安装成功。
- `pip check`：`No broken requirements found`。
- FastAPI、Alembic、SQLAlchemy、psycopg、Celery、Redis 核心导入通过。
- `compileall`：PASS。
- 全新 clone 定向非写入测试：22 passed、0 failed、0 skipped/deselected。
- 迁移与安全修复后主工作树定向回归：19 passed、0 failed。
- OpenAPI：3.1.0，179 paths，可生成、可通过运行中 `/openapi.json` 加载。
- Uvicorn `127.0.0.1:18080` 启动 PASS。
- `/health`、`/api/health`、`/api/db/health`：200。
- PostgreSQL 主库状态正常，fallback 未启用。
- Redis 状态可识别为 connected。
- 无活动 Celery Worker 时如实返回 `worker_count=0`、`active_workers=[]`。
- RAG 如实返回 `disabled`；DeepSeek 缺少 Key、Ollama 无模型均如实降级。
- 冒烟进程已停止，端口已释放。

## 10. 前端全新环境

- 从独立干净 clone 执行 `npm ci`：新增 140 packages，安装成功。
- `npm ls --depth=0`：退出码 0。
- Node 测试：7 passed、0 failed、0 skipped。
- TypeScript `--noEmit`：PASS。
- 正式 build：PASS，Vite 3675 modules，`dist` 由本次干净环境新生成。
- Preview `127.0.0.1:15173`：HTTP 200。
- 浏览器：页面标题正确；未登录状态明确显示用户名/密码登录页；console 0 error、0 warning。
- API 基础地址默认使用相对地址，由本地开发代理或部署反向代理承接，无旧端口硬编码。
- 冒烟进程已停止，端口已释放。

## 11. 测试统计

| 验证项 | passed | failed | skipped/deselected |
|---|---:|---:|---:|
| 全新 clone 后端定向测试 | 22 | 0 | 0 |
| 主工作树迁移/安全定向回归 | 19 | 0 | 0 |
| Node view-state | 7 | 0 | 0 |
| TypeScript | PASS | 0 | 0 |
| Vite build | PASS | 0 | 0 |
| 主/企业 Compose 解析 | 2 | 0 | 0 |
| 最终迁移 upgrade/downgrade/re-upgrade | 3 | 0 | 0 |
| 浏览器 console | 0 error | 0 blocking | 0 warning |

不同 Python 组存在用例重叠，不做虚假合计。

## 12. 提交

1. `18da943405750e259bb035b13af082c7c9b15b56` — `day2: isolate alembic schema replay`
2. `bbbe43a58e94cf4503280dd6948a765f5e8217c0` — `day2: close reproducible config defaults`
3. `2804716a2b4a10fca67b4ad5fa9dd8cf318bf1a7` — `docs: document clean environment reproduction`
4. `97dcd5091692710407f7b977b0713733fc1124bb` — `fix: run alembic environment once`
5. Day 2 证据与状态收口提交：见本报告所在最终 HEAD。

## 13. 已知问题与回滚

- `npm audit`：2 high、2 moderate、0 critical；未自动修改依赖树。
- 其余限制详见 `unresolved.md`。
- 代码按 `rollback.md` 中的提交逆序 `git revert`。
- 数据库无需恢复：`public` 未迁移/未写入，所有临时 Schema/角色均已精确清理。

## 14. 20 项验收

1. Day 1 基线一致：PASS
2. Day 2 独立分支：PASS
3. 外部干净 clone：PASS
4. clone 工作树干净：PASS
5. 配置完整且无真实密钥：PASS
6. 生产配置 fail-closed：PASS
7. Compose 示例可解析：PASS
8. 空 Schema 升级到 0016：PASS
9. 0016 → 0014 → 0016：PASS
10. 两次 head 结构一致：PASS
11. `public` 未越界：PASS
12. 临时对象清理：PASS
13. 全新 Python 安装：PASS
14. 后端启动与健康语义：PASS
15. 全新 Node 安装：PASS
16. 前端测试/TypeScript/build：PASS
17. 前端预览/登录态/控制台：PASS
18. 最终工作树干净：在收口提交后复核
19. 恢复与回滚方法：PASS
20. 未提前实施 Day 3：PASS

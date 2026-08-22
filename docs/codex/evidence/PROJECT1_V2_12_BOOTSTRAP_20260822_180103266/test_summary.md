# 验证摘要

## 基线与备份

- 冻结基线：路径、分支、SHA、Tag、clean、upstream ahead/behind `0 0` 全部 PASS。
- Git bundle：`git bundle verify` PASS；SHA256 为 `91fb5a5b6287f3831a92a7b334f104c2d19a48cfb4612270cf206da8168206e1`。
- 普通根目录：9 个 tracked 修改、0 个 staged 修改、674 个 untracked 文件已原样备份并逐文件校验；未 reset/clean/stash/覆盖。

## 种子与工作树

- `INTEGRATION_SEED_SHA=3b6eb33df96ece08a60acce802d6ec249ec5a826`。
- A/B/C 路径、分支、HEAD、clean：全部 PASS，HEAD 均等于种子 SHA。
- 每个新 worktree 的 `.env` 均与受控源 SHA256 一致、被 Git ignore 且不在 tracked files 中。
- 每个新 worktree 的 `frontend/node_modules` 均为指向 E 盘共享依赖的目录联接并被 Git ignore。

## 依赖与服务

| 项目 | A | B | C |
|---|---|---|---|
| Python 3.11.9 与项目模块导入 | PASS | PASS | PASS |
| pytest 8.4.2 命令识别 | PASS | PASS | PASS |
| Alembic head `0022_chatbi_semantic_v1` | PASS | PASS | PASS |
| Node v24.18.0 / npm 11.16.0 | PASS | PASS | PASS |
| Vite/TypeScript/React 依赖解析 | PASS | PASS | PASS |
| 前端 dev/build/preview 脚本识别 | PASS | PASS | PASS |
| 统一启动器只读预检 | PASS | PASS | PASS |
| 预检后工作树 clean | PASS | PASS | PASS |

- PostgreSQL：启动器验证本地双角色身份和迁移头，凭据隐藏，未写入数据。
- Redis：容器 running/healthy，`PING=PONG`，未写队列。
- Qdrant：容器 running，127.0.0.1:6333 TCP 可达；未创建、删除或切换 collection/alias。
- 冻结基线临时目录或 PID 文件：新 worktree 不依赖。

结论：`WORKTREE_ENV_READY=YES`，`PARALLEL_READY=YES`。

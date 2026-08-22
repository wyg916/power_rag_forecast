# 回滚与恢复

## 普通根目录恢复

- 外置备份：`E:\项目一_v2.12.0_备份\BOOTSTRAP_20260822_180103266`。
- Git 对象与 refs：使用已验证的 `repository_all_refs.bundle`。
- tracked 工作区：使用 binary/full-index unstaged patch；staged patch 单独保存。
- untracked 工作区：使用逐文件备份和 SHA256 清单按原相对路径人工核对恢复。
- 本轮没有改变普通根目录，因此正常情况下不需要执行恢复。

## 本轮 Bootstrap 撤销

- 在用户明确确认后，才可逐一移除本轮四个 worktree、对应分支、各 worktree `.env` 副本和 `frontend/node_modules` 目录联接。
- 禁止递归删除、`git clean`、`git reset --hard` 或批量移除历史 worktree/分支。
- 集成 Git 内容需要撤销时，在集成分支对本轮提交创建可审计 revert；不得重写冻结基线历史。

## 数据影响

- PostgreSQL：只读预检，无迁移/写入。
- Redis：仅 PING，无写入。
- Qdrant：仅容器/TCP 探测，无 point/collection/alias 写入。
- 模型与 RAG 资产：未反序列化、未激活、未切 production alias。

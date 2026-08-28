# 回滚

主项目合入后，使用 `git revert <main_integration_commit>` 创建可审计回滚提交。

合入前目标基线：`307e0b9730e8a58b713ca328975de5ffcc777cb8`。

本次无数据库、API、后端、RBAC、路由或业务数据变更，无需数据库回滚。

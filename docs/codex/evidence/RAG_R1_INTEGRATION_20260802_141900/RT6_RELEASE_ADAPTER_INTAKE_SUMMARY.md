# Runtime RT6 verified release adapter 接收证据

## 接收边界

- 来源提交：`40d7e4c14ae9f835a0ab2ff63195f8ab5d3dbe4d`。
- 接收 5 个文件，来源 `+841/-2`；含 verified release facts adapter、测试、release service 缝合与 RT6 原证据。
- 未接收分支 merge、M6 Compose/env、Alembic、Router 或真实存储配置。

## 顺序适配与验证

- 来源测试提前使用后续 M6 `strict_mode_enabled` 字段，首次结果 `20 passed, 6 failed`。
- 为保持 Runtime 先于 Qdrant/M6 的既定顺序，只删除 fixture 中该 1 行；adapter 实现不依赖该字段。
- 适配后 adapter/release 联合测试：`26 passed in 1.68s`。
- M6 接收后必须恢复 strict mode 字段并重跑联合回归；最终安全门禁不降低。
- PostgreSQL、Qdrant、模型和网络写入：0；正式发布/回滚：0。

## 回滚

使用普通 `git revert <RT6-integration-commit>`；无外部状态需要恢复。

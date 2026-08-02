# Runtime RT6A adapter 失败边界接收证据

- 来源提交：`c79671c82b2b2cd6deedc0f9cb136349fc3d0b1d`。
- 接收 5 个文件、`+246/-7`；只加固 release adapter、release service、测试与 RT6A 原证据。
- 覆盖不可用、已知冲突、未知异常脱敏、补偿失败、回滚 RTO 与 receipt/fact 不一致边界。
- adapter/release 联合测试：`40 passed in 1.39s`。
- `git diff --cached --check`：PASS；敏感扫描在提交前执行。
- PostgreSQL、Qdrant、模型和网络写入 0；正式发布/回滚 0。
- 回滚：普通 `git revert <RT6A-integration-commit>`；无外部状态需要恢复。

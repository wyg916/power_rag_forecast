# Runtime RT4 原子发布协议接收证据

## 接收边界

- 来源提交：`a51b21ab9438ae9d3e4b4deb794ba603cdbbb287`。
- 接收 3 个文件、净新增 823 行；含 release service、测试与 RT4 原证据。
- 未接收分支 merge、正式 Alembic revision、公共 Compose、Router 或真实存储配置。

## 验证与当前边界

- Candidate 验证、双存储准备、alias/current release 协调、失败补偿和旧 release 保留：`10 passed in 1.03s`。
- 测试仓储与 alias 为内存 fake；真实 PostgreSQL/Qdrant 发布尚未执行。
- PostgreSQL、Qdrant、模型和网络写入：0；Candidate/Active/生产切换：NO。

## 回滚

使用普通 `git revert <RT4-integration-commit>`；无外部状态需要恢复。

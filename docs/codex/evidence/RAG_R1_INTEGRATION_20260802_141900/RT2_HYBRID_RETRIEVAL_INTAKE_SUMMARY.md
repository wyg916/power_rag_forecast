# Runtime RT2 混合检索接收证据

## 接收边界

- 来源：`beeccbfedca9514f643f6c76a1f3ee60cb89f43f`、`edbee65497474c898ce582db00480d8fca6f3698`。
- 接收 7 个文件、净新增 910 行；含 release-aware hybrid core、Qdrant adapter、服务缝合、测试和 RT2 原证据。
- 未接收分支 merge、Qdrant Compose、Alembic、Router 或正式连接配置。

## 验证与当前边界

- 混合检索、tenant/release ACL、向量维度、payload 与 adapter 边界：`17 passed in 0.20s`。
- 测试客户端为 fake；当前环境无 `qdrant-client`，Qdrant 1.18.2 尚未启动。
- PostgreSQL、Qdrant、模型和网络写入：0；不存在可发布 Collection。

## 回滚

使用普通 `git revert <RT2-integration-commit>`；无外部状态需要恢复。

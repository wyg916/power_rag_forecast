# 数据库与运行资产影响

- PostgreSQL：零连接、零写入、零迁移。
- Qdrant：仅做本地端口和匿名健康探测；零数据读取验收、零写入、零 alias/release/snapshot 操作。
- 模型：只读 safetensors 准入检查；资源门禁在加载完成前停止；零量化、零导出、零覆盖。
- 公共配置与 Compose：未修改。
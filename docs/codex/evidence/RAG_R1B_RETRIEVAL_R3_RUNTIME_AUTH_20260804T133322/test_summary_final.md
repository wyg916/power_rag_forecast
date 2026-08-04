# R3 环境恢复与授权检查摘要

- Qdrant TCP `127.0.0.1:6333`：PASS。
- Qdrant 1.18.2 TLS/HTTP、strict、无 Key 拒绝、只读 Key 读允许/写拒绝、1024 维探针：PASS；专用探针 Collection 已清理。
- Candidate：`RAG-R1` / `rag_chunks_RAG-R1` / 8,339 points / 22 payload indexes / BGE 1024：PASS。
- PostgreSQL release 一致性、`candidate`、`is_current=false`：PASS；验证事务只读，写入 0。
- PostgreSQL 最小权限 Secret 注入：未执行；当前配置身份为 `postgres` 超级用户，新角色创建未获安全门禁授权。
- Qdrant Git 外只读配置注入：PASS；Admin Key 与数据库 Secret 未注入。
- 50 题冻结：40 开发 + 10 隐藏，manifest 与三份 artifact SHA-256 复算一致。
- 63fc9fc：未 cherry-pick；主控接收 NO；来源 live NOT EXECUTED；P95 NOT PROVEN。
- controller@c622754 独立 live50：质量门禁不退化，cold miss P95 11,372.354ms、warm hit P95 6,149.715ms，均 FAIL。
- 任务 16 定向测试：39 passed in 1.58s。
- JSON/schema、40/10 分区、固定字段与 4 个冻结文件 SHA-256：PASS。
- 敏感信息扫描：0 finding；63fc question_id/答案硬编码与 critical 降级扫描：0 finding；`git diff --check` PASS。
- snapshot、alias、release、发布变更：0。

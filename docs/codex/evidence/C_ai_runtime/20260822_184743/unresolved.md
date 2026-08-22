# Unresolved

1. `MIMO_VISION=REMOTE_BLOCKED`：真实图片请求返回空响应。
2. DeepSeek 真实 AnalysisPlan 输出未通过冻结 schema；本地 Planner/Validator/Compiler 契约 PASS。
3. Integration 需接收 B 分支前端 scripts 并统一确认正式 8000/5173 所有者。
4. 全量数据库回归必须由受限 isolated-schema runner 执行；普通 pytest 会按设计清空 DATABASE_URL。

# RAG-R1B 定向测试摘要

- 治理集严格校验：PASS。
  - Retrieval：50 题、唯一 ID 50、critical 15。
  - AI：100 题、唯一 ID/question_id/question 各 100、critical 30。
  - 审核包：Retrieval 25+25；AI 25+25+25+25；critical 单独 30。
  - approval：150 题均为 pending，未声明正式黄金集 PASS。
- 定向 pytest：`18 passed in 0.68s`。
- 脚本与测试内存语法编译：PASS。
- 严格 JSON、重复键、源文件 SHA-256、审核包顺序及并集校验：PASS。
- 字符完整性：候选集及审核 JSON 中 ASCII 问号占位与 U+FFFD 均为 0。
- `git diff --check`：PASS。
- 修改白名单：PASS，恰好 20 个提交文件。
- question_id 答案硬编码扫描：PASS；评测脚本不含 P5B/R1-RET 题号分支。
- 敏感信息扫描：PASS，未发现私钥、真实 Bearer/token、云访问密钥或含密码数据库 URL。
- 有效代码新增门禁：脚本新增 842 行，新增测试 157 行，合计 999 行；未超过 1000 行。
- 未执行真实候选环境 AI 100/检索复跑：该操作需要数据库、模型/Qdrant 或工作树外运行资产，超出本任务授权；因此沿用并明确标记既有正式指标，不能据本次单测声明质量门槛 PASS。

# 测试摘要

- 定向回归第一次：71 passed，0.94s。
- 定向回归幂等复跑：71 passed，0.88s。
- reranker 压缩后专项：4 passed；并发加载、版本缓存键、8/8/1 批处理、幂等预热均覆盖。
- acceptance guard 合约验证：逐题 cache/embed、拒绝写端点、range 操作符保留、四象限完整门禁、`ec78c569…` Git 对象基线与 evaluator protocol 身份绑定、结果/ACL 退化拒绝均 PASS。
- Python 编译：Candidate 验收器与 3 个新增 performance 脚本通过。
- 白名单扫描：PASS。
- 敏感信息扫描：PASS。
- `git diff --check`：PASS（仅 Git 的 LF/CRLF 提示，不是 diff 错误）。
- 新增有效行：1000；修改/新增业务与测试文件 12 个，均未越过停止线。
- 正式 Candidate 50 题验收：BLOCKED，Qdrant `127.0.0.1:6333` 不可达；未生成虚假 PASS。

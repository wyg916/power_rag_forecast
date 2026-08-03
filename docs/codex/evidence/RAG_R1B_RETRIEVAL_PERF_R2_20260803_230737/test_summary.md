# 测试摘要

- 最终定向回归第1次：74 passed，0 failed。
- 最终定向回归第2次：74 passed，0 failed。
- 覆盖：混合检索、运行时契约、Qdrant transport/store、Candidate 验收、legacy bypass、reranker 单例/预热/批处理/精确重复输入去重。
- 新增边界：A/B/A raw-score 映射、ACL/Citation/身份字段保留、score-count mismatch fail-closed。
- 标准库语义探针：PASS。
- Python 语法编译：PASS。
- JSON 证据解析：PASS。
- 白名单扫描：PASS。
- 敏感值与外部敏感路径扫描：PASS。
- git diff --check：PASS。
- 正式50题 live：未执行，不声明 PASS。
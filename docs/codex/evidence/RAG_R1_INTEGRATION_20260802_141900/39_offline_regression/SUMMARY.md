# RAG-R1 离线回归与发布前收口

## 结论

- 可执行代码、迁移、安全契约、数据库隔离、前端构建和浏览器回归：PASS。
- RAG-R1 正式发布验收：NOT PASS / BLOCKED。
- 发布决定：`publish_allowed=false`；未创建 snapshot、未切换 alias、未晋升 Published、未切换生产。

## 修复

- PostgreSQL 模型误差查询改用原生 interval 表达式，移除 MySQL `DATE_SUB`。
- 非法数据集字段在数据库不可用前优先返回 400，避免被 503 掩盖。
- 旧 RAG 测试显式声明 legacy profile；企业 Qdrant 安全契约测试补齐 TLS、只读、密钥、版本和镜像摘要环境。
- 数据库测试只在 Day 3 隔离运行器执行；普通回归以明确原因 skip，不再隐式连接本地数据库。
- T002 和电价数据改为显式 Git 外资产根目录；真实外置资产另行跑通。
- 知识库 API 测试对齐 Analyst 读、Reviewer 写权限；权限矩阵重生成至 201 method/path、188 unique、7 public、194 protected。
- 策略迁移头更新至 `0018_rag_enterprise_r1`；无报告事实时 AI 保持空证据并明确不可用，不伪造 citation。

## 验证

- 全仓普通回归：836 passed、94 skipped、0 failed，348.20s；JUnit：`full_pytest.xml`。
- RAG 企业专项：377 passed、8 skipped；静态 Day3/Day4/T002/T004/T005：84 passed、28 skipped。
- Day3 数据访问隔离：21 passed，`public_match=true`，清理 PASS，残留 0。
- 业务数据库隔离：最终 79 passed，`public_match=true`，清理 PASS，残留 0；之前的启动器、SQL 方言和旧迁移头失败均保留为审计证据。
- Git 外 T002 正式资产：26 passed；Git 外电价资产：5 passed。
- TypeScript + Vite：PASS，3,675 modules，build 5m03s。
- 浏览器：AI 助手和知识库在 1920/1672/1440/1366/1180 非全屏共 10 组合，页面横向溢出 0、可见元素越界 0。

## 发布阻断

严格预检再次确认 83/83 终态、45 documents、24 isolations、14 duplicates、0 damaged、8,339 chunks、Candidate SHA 一致；但以下 RAG-R1 独立人工标注输入均不存在：

- OCR/VLM：30 页人工金标缺失。
- 检索：50 条黄金问题集缺失。
- AI：100 题（含 30 critical）黄金集缺失。

因此 CER、表格 F1、Recall@3/5、MRR、AI 准确率、grounding、幻觉数字和正式 P95 均不得执行或引用旧 Phase 5 资产代替。Candidate 与 Corpus 基础门禁虽通过，正式质量门禁仍为 BLOCKED。

## 安全提醒

终态只读探针首次使用原生驱动读取 SQLAlchemy 风格连接串时，驱动异常文本曾把受限数据库连接串写入当前任务工具日志。该连接串未写入仓库、提交或本证据目录，后续探针也已改为仅输出异常类型；但应把对应本地受限登录凭据视为已暴露并在下一次运行前轮换。凭据轮换完成前不得发布。

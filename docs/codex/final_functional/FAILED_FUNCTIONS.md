# 失败功能清单

## 最终结果

- FAIL：0。
- UNKNOWN：0。
- RELEASE_BLOCKING：0。
- Disabled-by-design：98，均在 `INTERACTIVE_ELEMENT_MATRIX.csv` 中逐项登记，主要为权限、未选中记录、运行中防重入和未经批准的治理动作。

## 已关闭缺陷

1. 企业 RAG 浏览器隔离启动曾被本地配置覆盖为非候选运行模式，导致 `enterprise_rag_runtime_unavailable`。已固定加载 Git 控制的预生产候选契约，并验证只读 Key、无 admin key、无 alias、无文件 fallback。
2. 完整的“指定日期 + 日前电价均值 + 按市场分组”问题曾被 LLM 错误规划为澄清。已新增稳定意图路由及服务端已注册 AnalysisPlan 归一化；最终真实浏览器查询 PASS。
3. 非隔离专项曾出现 6 个缺业务事实失败；相同用例在受控 PostgreSQL 隔离链路 114/114 PASS，确认是运行上下文误用，不是发布功能缺陷。

## 非阻塞观察

- 全仓诊断快照为 1019 passed / 39 skipped / 50 failed / 32 errors；其中 6 个 AI 失败已在当前隔离复跑关闭，其余为既有 `LEGACY_OUT_OF_SCOPE` 或缺少受限数据库、历史模型/资产的 `EXTERNAL_ENVIRONMENT` 分类。当前发布矩阵、隔离验收和浏览器正常路径均通过；未修改历史测试口径来改善数字。
- 390×844 移动视口不是本次规定门禁，存在桌面工作台横向溢出观察；四个规定桌面视口全部 PASS，且 UI 冻结条件下未重排版。
- 未执行生产切换、RAG production alias、模型 Active 晋升或外部发布。


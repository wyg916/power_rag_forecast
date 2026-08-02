# RAG-RT6 RT4 到 M5 发布适配器证据

## 范围与检查点

- 起始 HEAD：`ab8df2568485d59f987c817bb39bd96dcccbaf7c`。
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_194302_RAG_RT6_PRE`。
- 无冲突合并本地主线 `0ee5c617a49278e33a5ab772b02de4c501d982ae`，合并 HEAD 为 `afa5da414eee1e4801a8d0a65ecea18541488de7`。
- 本提交限制为 RT4 发布运行时、M5 适配器、核心测试和本证据，共 5 文件。

## 实现结果

- RT4 ReleaseRecord 增加 manifest SHA-256；preflight 在任何 control-plane/store 写入前拒绝无效 hash。
- 适配器显式转换 ReleaseOperation、ReleaseRecord、ReleaseFact 为严格 ReleaseContract。
- 成功返回前复核 tenant、release、状态、current release、alias、smoke、最终操作事实、manifest、Embedding 和全部 gates。
- 完成事实绑定本次 run/trace；失败、补偿异常、RTO 超时和未知结果只返回 unavailable。
- 已知状态冲突保持 conflict；未知底层 reason 归一化，不回显异常细节。
- 默认生产应用装配未修改，仍为 unavailable。

## 验证与规模

- 核心适配器、RT4、RT5、M5 定向回归：`50 passed in 0.92s`。
- 拆包后本提交新增不超过 850 行；剩余篡改与异常形态测试进入独立 RT6A。
- Python compileall 与 `git diff --check`：PASS。

## 外部影响与回滚

- 仅使用 Fake store/control-plane/cache；未连接 PostgreSQL、Qdrant、缓存、队列、模型或网络。
- 未修改正式 release、alias、Collection、配置、Compose 或 Alembic。
- 回滚使用 `git revert <RAG-RT6-commit>`；没有外部状态需要恢复。

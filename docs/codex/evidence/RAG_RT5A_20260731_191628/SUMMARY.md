# RAG-RT5A 并发幂等语义修复证据

## 范围与检查点

- 基线：`834ef45e6ca2c154da39a24a2bde50ecbd815d3f`。
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_191357_RAG_RT5A_PRE`。
- 仅修复 RT5 原子创建的并发幂等返回语义，并补充纯 Fake 竞态测试。

## 修复结果

- ingestion/release 原子 Store 返回值显式区分 `created` 与 `existing`。
- `created=true` 仍强制 Draft/Candidate 的 run/trace 匹配本次请求。
- `created=false` 返回同 tenant、同 key、同 hash 的稳定原事实，不把合法竞态误报 unavailable。
- 同 key 异 hash 在预读命中或原子写竞态中均保持 conflict。
- 同 hash 竞态不会重复创建 immutable content、Draft fact 或 Candidate release，也不会伪造新 run/trace。
- 异常原子返回类型或非布尔 `created` 标志继续 fail-closed。

## Publisher 接线边界

- `ReleasePublisherPort` 当前只是 M5 应用编排到发布流程的注入协议。
- 后续数据库适配器必须把 RT4 `ReleaseOperation` 及其持久化事实明确转换为严格 `ReleaseContract`。
- 本包没有实现该数据库适配器，也不宣称 RT4 已完成具体生产接线；默认生产依赖仍为 unavailable。

## 验证与外部影响

- RT5A、M5 API、RT4 发布定向回归：`43 passed in 1.55s`。
- 全部 RAG enterprise 专项回归：`160 passed in 5.32s`。
- 未连接或写入真实文件、PostgreSQL、Qdrant、队列、缓存、模型或网络。
- 回滚使用 `git revert <RAG-RT5A-commit>`；没有外部状态需要恢复。

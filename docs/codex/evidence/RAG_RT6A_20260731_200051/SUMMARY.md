# RAG-RT6A 发布适配器边界验证证据

## 范围与检查点

- 基线：`40d7e4c14ae9f835a0ab2ff63195f8ab5d3dbe4d`。
- 检查点：`E:\智能运营分析项目_worktrees\checkpoints\20260731_195919_RAG_RT6A_PRE`。
- 本包补充共享基础 Record 门禁、rollback 前置门禁及篡改与故障注入测试。

## 验证边界

- 未知底层 reason 统一为稳定 `unknown`，不回显内部异常文本。
- 非法 release identifier 在访问 runtime/fact 前拒绝。
- RT4 manifest 与 M5 seed 不一致、成功 gate 携带失败 reason 均 unavailable。
- 缺失 Trace、跨租户 Record、缺失操作事实、Trace 事实写入失败均 fail-closed。
- 最终操作事实 `alias_after`、持久化 details 形态及时钟异常均不能产生成功 DTO。
- smoke 后 alias 再漂移会被最终一致性复核拦截。
- validate/publish/rollback 复用 tenant、identity、manifest、profile、gate、snapshot 基础门禁。
- rollback 的 target/previous 任一事实损坏均在 alias、PG、事实和缓存写入前失败。
- 适配器对 target、current、previous Record 执行相同基础门禁和部署 profile 比对。
- 默认生产应用依赖保持 unavailable。

## 验证与规模

- RT6/RT6A、RT4、RT5、M5 定向回归：`64 passed in 0.90s`。
- 全部 RAG enterprise 专项回归：`210 passed in 5.06s`。
- 本包 5 文件、246 行新增，低于独立任务包上限。

## 外部影响与回滚

- 仅使用 Fake store/control-plane/cache；真实数据库、Qdrant、缓存、队列、模型和网络访问均为 0。
- 回滚使用 `git revert <RAG-RT6A-commit>`；没有外部状态需要恢复。

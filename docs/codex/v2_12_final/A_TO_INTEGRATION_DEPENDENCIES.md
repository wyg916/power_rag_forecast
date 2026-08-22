# A 到最终集成的依赖

## 非阻塞集成检查

1. 集成启动 forecast worker 时继续使用唯一 nodename，并在接受首个请求前完成 Celery queue health 预热。本轮专用 queue 的 health 前两次未收到回复、第三次成功；随后公开 API 首次提交即正常进入 Celery。不得用关闭 queue health 或回退本地线程规避该检查。
2. 合入后保留 PostgreSQL Active 模型事实中的绝对 `artifact_path` 可读性；handler 可由该事实定位共享输入和隔离运行时，也仍支持 `POWER_TRADING_ASSET_ROOT` 显式只读配置。不得复制 artifact 到 worktree 形成第二套模型事实。
3. 保留历史来源语义与 `stale_strategy_cannot_publish` 护栏；该本地样本只用于可追溯业务链和审计，不代表当前实时预测或生产动作。

## C 所有权依赖

ChatBI 的 metric、dimension、relationship/join catalog 及至少 20 个核心业务 Golden 问题语义验收属于 C 工作流。A 未修改 ChatBI Catalog 或 AI Runtime；最终集成负责人应引用 C 的交付结果完成该门禁。

## 越界修改

无。A 未修改 frontend、AI Runtime、Provider Router、附件 Runtime、启动脚本、CI、main 或 B/C 分支，也未合并 B/C。

# 预测中心三页面 UI 集成准备证据

状态：`APPROVED_FOR_INTEGRATION`，不是最终 `PASS`。

用户已针对候选 `7090de4f76a4df228f7b98e9203b205c5aeba0fd` 与三页截图明确确认视觉通过。该候选已在独立集成分支叠加到当时最新 Release `b4cfdd06dc9fb63ebbc66565531f9a5c40f4b589`，并完成视觉、交互、API、只读 PostgreSQL、构建和一键启动复验。

本目录只证明隔离集成可用。真正 Release 分支和用户最初指定的最终 worktree 尚未切换；原因及下一步见 `FINAL_PATH_GATE.md`。

## 证据索引

- `BASELINE_AND_PROVENANCE.md`：候选、Release、合并与文件来源。
- `VISUAL_ACCEPTANCE.md`：三页同视口矩阵与截图。
- `FUNCTIONAL_ACCEPTANCE.md`：可见控件及七态验收。
- `BUILD_TEST_RUNTIME.md`：类型、build、测试、双启动和进程来源。
- `DATA_AND_SECURITY.md`：API/数据库一致性、权限与零写入。
- `USER_CONFIRMATION.md`：用户确认记录。
- `FINAL_PATH_GATE.md`：最终路径冲突、待授权动作与回滚。

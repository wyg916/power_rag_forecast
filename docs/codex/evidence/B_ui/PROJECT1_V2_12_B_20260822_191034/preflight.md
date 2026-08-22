# PROJECT1 v2.12.0 B 前置检查点

- 时间：2026-08-22 19:10:34 +08:00
- worktree：`E:\智能运营分析项目_worktrees\project1_v2.12.0_ui_rbac_ai_shell`
- 分支：`codex/project1-v2.12.0-ui-rbac-ai-shell`
- HEAD：`3b6eb33df96ece08a60acce802d6ec249ec5a826`
- Git 状态：clean
- 暂存差异：0
- 未暂存差异：0
- 未跟踪文件：0
- frontend tracked files：97
- 数据库影响：无；本任务禁止修改数据库、迁移和后端。

## 关键文件 SHA256

```text
F901EB1ADE5E74C682604426A3AABEBD83CF4ACCBC108636F453BCD99A0A2BFE  frontend/package.json
9765F34E326E5856F61803A6E116D8A0DAF8D0F4B9DB588B350C1268FE95CC7A  frontend/src/app/App.tsx
6869ABB7B7624AAAD9AB86FD606225E150CAFB4040CACA7F4A9839CB0022EEA9  frontend/src/app/router.tsx
D77F1DFD1DD44DFF28089E80BF9DE32A90EEB8C2530EE5E25C8FBF78F654B2F4  frontend/src/context/AuthContext.tsx
A61DD89D1DDBE635EE2493202C9A46BE09F5A5A0C43F492C00BD5ACD4514C257  frontend/src/services/assistantApi.ts
75FC5DFC3FDA3B700EAE7CE3A1D46697CD54A679D8A57A5CC508714686E0EBA8  frontend/src/pages/assistant/AssistantPage.tsx
81A6A726DE91E332BB42B8D12D1B21843A42FAF819A3AAB342ACAE8E5D1590B2  docs/codex/v2_12_final/INTERFACE_CONTRACT.md
D6CAB8EF1C5549B513E975F42B6C31900449D9F4EEA6340C8D9C03A3211B4F00  docs/codex/security/API_PERMISSION_MATRIX.csv
```

## 基线验证

- `npm run build`：PASS（Vite 5.4.21，3675 modules）
- `node --test tests/*.test.mjs`：PASS（11/11）
- ESLint/Vitest：当前 package 与 node_modules 未提供；任务内补离线可重复门禁脚本，不联网安装。

## 回滚

业务代码修改前的完整状态等于上述 HEAD。完成提交后可使用 `git revert <final_commit>` 创建可审计回滚提交；禁止 reset/clean。若仅需恢复单个文件，使用本检查点 SHA256 对照并从起始提交 `3b6eb33d...` 提取对应文件内容，执行前需确认目标文件。

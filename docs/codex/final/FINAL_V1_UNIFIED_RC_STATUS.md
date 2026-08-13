# FINAL V1 UNIFIED RC STATUS

## 冻结结论

- `FINAL_V1_UNIFIED_RC = PASS`
- `PROJECT_ENGINEERING_COMPLETE = PASS`
- `FULL_UI_FUNCTIONAL_ACCEPTANCE = PASS`
- `LOCAL_PREPRODUCTION_RC = PASS`
- `PRODUCTION_GO_LIVE = NOT_EXECUTED`

## 唯一 Release

- Branch：`release/beta10d-agent-rc-20260807`
- Functional Acceptance SHA：`3a5ee83adbe7b791aac9826d83d9f9f886a5ded1`
- Release 最终 SHA：本状态登记文件所在提交；仅比 Functional Acceptance SHA 多最终状态/证据登记。
- 收敛方式：`git merge --ff-only codex/final-functional-acceptance-20260812`
- 收敛前 ancestry：Release `fefb72f6c56e387a10bd2a4d798813593f1f2334` 为 Functional Acceptance SHA 的完整祖先；merge-base 与 Release 相同；ahead/behind 为 `0/21`；无 Release 侧独有提交。
- 收敛后 Functional Acceptance 分支与 Release ahead/behind：`0/0`。
- 原 Day7 Tag 未修改；`functional-acceptance-rc-20260813` annotated tag 也保持未修改，并继续 peel 到 `3a5ee83adbe7b791aac9826d83d9f9f886a5ded1`。

## 最小最终门禁

| 门禁 | 结果 |
|---|---|
| Git clean / diff check | PASS；状态登记提交前 clean，`git diff --check` 无输出；提交后复核见证据目录 |
| Alembic unique head | PASS；唯一 `0022_chatbi_semantic_v1` |
| AI Assistant 三模型 + AUTO | PASS；Kimi、MiMo、DeepSeek 各 9/9；AUTO 浏览器实际路由到 DeepSeek V4-Flash |
| ChatBI Golden 50 | PASS；50/50，所有适用维度 100% |
| RAG | PASS；专项 58/58；正式集合 8,339 points；TLS/只读 key/1024 维/strict PASS；持久写入 0；production alias 未切换 |
| Memory | PASS；live 9/9；cross-user/cross-tenant、TTL、Archive、Soft Delete、Outbox 与删除证明覆盖 |
| Security / RBAC | PASS；128/128；隔离 public 指纹一致，临时 Schema/role 残留 0 |
| Frontend build | PASS；TypeScript + Vite，3,675 modules |
| Browser 关键页 | PASS；登录、首页、AI、ChatBI、RAG、知识库、报告、任务、设置；关键页溢出/禁词/错误态 0 |
| Network | PASS；51/51 为 HTTP 200，Unexpected 4xx/5xx = 0 |
| Console | PASS；应用 Console Error = 0 |
| `run_project.bat` | PASS；在同一 Release SHA 上最终连续两次退出 0，第二次继续幂等复用所有健康服务 |

## 过程诊断保留

- 一次组合诊断为 243 passed / 4 skipped / 4 failed：3 项旧 RAG 单测仍假设非空 alias，与当前 preproduction candidate 空 alias 契约冲突；1 项旧前端源码字符串断言要求 `task:manage` 位于页面文件中。未修改旧测试、业务代码或当前安全契约；RAG 当前专项、运行态探针与 Security/RBAC 专项均独立全绿。
- Memory 首轮 live test 因旧 `DAY4_TARGET_SCHEMA` 变量未映射而 8/9；映射到隔离守卫发布的同一临时 Schema 后 9/9，未修改测试文件。
- `run_project.bat` 初始第二次运行遇到 Vite 刚监听但 HTTP 尚未 ready 的瞬时竞态，按失败保留；同一进程稳定返回 200 后，重新开始的连续两次完整运行均退出 0。

## 不变量与边界

- Golden Set blob 与收敛前 Release 完全一致，未修改。
- 业务代码、UI 布局、模型状态均未因最终状态登记改变。
- 未推送远端、未进入生产、未切 production alias、未激活 Candidate 模型。
- 本结论只授权正式冻结本地 V1 预发布 RC，不构成生产上线授权。

## 证据

- 项目盘任务检查点：`E:\智能运营分析项目\.codex_tmp\release-governance-20260813\20260813_044500_FINAL_V1_UNIFIED_RC_PRE`
- 当前最小门禁原始证据：`E:\智能运营分析项目\.codex_tmp\release-governance-20260813\gates`
- 浏览器运行日志：`E:\智能运营分析项目\.codex_tmp\release-governance-20260813\browser\runtime`
- 最终可提交证据摘要：`docs/codex/evidence/FINAL_V1_UNIFIED_RC_20260813/`

# 分支与 Worktree 索引

## 唯一最终 Release

- `E:\智能运营分析项目_worktrees\release_beta10d_agent_rc_20260807`
- `release/beta10d-agent-rc-20260807`
- 本轮起点 `adac8ec`；最终值由最终标签解析。

## 已吸收的历史实现

- 首页：`codex/p6-home-dashboard-readability-20260813` / `e98010f`
- 数据中心：`codex/ui-data-center-overview-quality-catalog-20260813` / `a35ee265`
- 预测中心：`codex/ui-forecast-center-fidelity-20260814` / `7090de4`
- 报告中心：`codex/ui-report-center-cards-20260814` / `db0d9e1`
- AI/Memory/RAG/ChatBI 历史包已由 Release 既有提交链吸收，不再作为启动入口。

## 历史失败/检查点

`beta10d/day6-business-loop`、`day6a`、`day6b`、`day6c`、`day7-final-acceptance`、`day8-execution`、`rag-r1-final-integration` 等保留历史 NOT PASS/FAIL 语义，不删除、不改写。

## UI 候选

`codex/p6-home-dashboard-*`、`codex/ui-data-center-*`、`codex/ui-forecast-center-*`、`codex/ui-report-center-*` 仅用于历史对照；最终事实以 Release 为准。

## 独立证据/开发分支

`codex/rag-enterprise-ingestion`、`codex/rag-enterprise-runtime`、`beta10d/rag-r1b-*`、`hotfix/ai-assistant-runtime-providers-20260812` 等继续保留，不作为最终入口。

## 受保护普通仓库

`E:\智能运营分析项目` 当前分支 `codex/report-center-v2-ui`，含用户未提交首页文件、文档与 Git 外运行资产。本轮开始和结束均只读复核，未清理、覆盖、恢复、提交或推送其中内容。

本轮未创建额外临时分支/worktree，也未删除任何历史分支/worktree。

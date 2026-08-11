# FINAL ROLLBACK GUIDE

## 适用边界

本指南只覆盖本地 Day7 冻结提交。Day7 未执行远端推送、生产部署、模型激活、RAG alias 切换或公共业务数据写入，因此不存在生产数据回退动作。

## Git 回退

1. 核对当前分支为 `release/beta10d-agent-rc-20260807`，保存 `git status --short --branch` 与当前提交。
2. 最终冻结点由本地 annotated tag `day7-final-unified-rc-20260811` 指向；Day7 起点为 `67208a496065aec08360b685d851ab8ce3bbb946`。
3. 如需撤销 Day7，优先在新分支对最终提交执行非破坏性的 `git revert <final-sha>`；不得使用 `git reset --hard` 或 `git clean`。
4. 回退后重跑唯一 Alembic head、前端 build、Browser smoke、Security、数据库指纹与双启动。

## 数据库与迁移

- 正式 head：`0022_chatbi_semantic_v1`；正常回退路径为 `0022→0021`，恢复为 `0021→0022`。
- 迁移只能使用独立 migration identity；普通 runtime identity 不得执行 DDL。
- 执行前后保存 public 指纹、对象数量和 Alembic current/head；确认临时 Schema/role 残留 0。
- Day7 未新增 migration、未写公共业务表。若仅回退前端兼容修复，不需要数据库变更。
- 任何无法解释的结构/数据差异立即停止，不做全表 UPDATE/DELETE。

## RAG、模型与 Memory

- RAG 保持 `RAG-R1 rolled_back / is_current=false`，current/production alias 为空。回退时不得创建或切换 alias；只复核正式 collection、snapshot 与 release 状态。
- Active model 保持 `model_20260620_063015`；Day7 无模型状态变化，不应执行模型回退或反序列化未知二进制。
- Enterprise Memory 与 ChatBI 使用既有 0020/0021/0022 schema；Day7 public 记录为 0，无数据恢复动作。

## 运行时回退验收

完成任何回退后，至少执行：Alembic unique head、数据库 100 次只读、Golden 50、Memory、RAG、Security、frontend build、Browser smoke、`run_project.bat` 连续两次和 Git clean。任何发布阻断或未分类失败出现时，回退不视为完成。

## 证据

- PRE/恢复清单：`backups/phase3/20260811_204531905_DAY7_FINAL_PRE`
- Day7 evidence：`docs/codex/evidence/DAY7_FINAL_ACCEPTANCE_20260811_204531905`
- 精确 Final SHA：`final_sha_manifest.json`

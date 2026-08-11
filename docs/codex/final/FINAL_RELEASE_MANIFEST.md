# FINAL RELEASE MANIFEST

## Git 与构建身份

| 项目 | 冻结值 |
|---|---|
| Branch | `release/beta10d-agent-rc-20260807` |
| Starting SHA | `67208a496065aec08360b685d851ab8ce3bbb946` |
| Final SHA | 本文件所在 Git 提交；精确值见 `final_sha_manifest.json` 与本地 tag `day7-final-unified-rc-20260811` |
| Alembic head | `0022_chatbi_semantic_v1`（唯一） |
| Frontend build | Vite 3675 modules |
| `run_project.bat` | 最终 SHA 连续两次 PASS |
| Remote push | 0 |

## 数据库

- 目标：本地 PostgreSQL `localhost:5432/postgres`。
- Public structure SHA-256：`c1f0ae1e8dabd61b5e2d9a24ff0652211cf24387ba6a1320b35aa4272fcd9785`。
- 对象：87 tables / 8 views / 47 sequences / 38 routines / 324 indexes / 922 constraints。
- 100 次关键读：稳定且无写副作用。
- Day7 public 业务写入：0。
- 最终测试用户/session/memory/ChatBI plan/Day7 trace/Day7 audit/临时 Schema/临时 role：均 0。
- 三条 2026-07 历史 test-named trace 与十三条 2026-08 历史验收审计保留为 `LEGACY_OUT_OF_SCOPE_IMMUTABLE_AUDIT_HISTORY`，未篡改历史。

## 模型、RAG、Memory、ChatBI

- Active model：`model_20260620_063015`，feature version `features_140db8af25f9`，artifact SHA-256 `f6689b533cb8fc94e18ac53a399e9bac5a4f6fb4c4df354c701182fe23c70f59`；Day7 未激活或反序列化新模型。
- RAG：Release `RAG-R1` 保持 `rolled_back / is_current=false`；正式 collection `rag_chunks_RAG-R1` 为 8339 points、1024 dimension、strict；snapshot 存在；current/production alias 为空；Day7 Qdrant 写入 0。
- Enterprise Memory：复用 0020/0021 唯一实现；Identity/Record/Version/Relation/Usage/Admission/Semantic/Episodic/TTL/Decay/Archive/Legal Hold/Delete/Outbox/Proof 均通过；Day7 public memory 写入 0。
- ChatBI：Catalog `chatbi-v1.0.0`，13 metrics / 21 dimensions / 2 whitelist joins；Golden canonical SHA-256 `5b884dbb41be415a11ad278e61f6adce07e08ed44a4a407f3d6b1e47a65838b7`；Golden 内容未改。

## 交付物

- `docs/codex/final/FINAL_RC_STATUS.md`
- `docs/codex/final/FINAL_RELEASE_MANIFEST.md`
- `docs/codex/final/FINAL_ACCEPTANCE_REPORT.md`
- `docs/codex/final/FINAL_EXTERNAL_GATES.md`
- `docs/codex/final/FINAL_ROLLBACK_GUIDE.md`
- `docs/codex/TASK_STATUS.md`
- `docs/codex/evidence/DAY7_FINAL_ACCEPTANCE_20260811_204531905`

该 Manifest 仅代表本地预发布等效 RC，不是生产发布授权。

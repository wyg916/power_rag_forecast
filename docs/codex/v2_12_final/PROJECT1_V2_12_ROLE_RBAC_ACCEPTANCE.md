# PROJECT1 v2.12.0 Role / RBAC Acceptance

## 冻结口径

权限由真实 capability/permission manifest 与 `docs/codex/security/API_PERMISSION_MATRIX.csv` 决定；菜单、route、Tab、card、button 和 API 请求不得根据角色名称猜测。后端授权是最终边界，前端隐藏只负责避免无效操作和裸 403。

## Round 1 结果

| 验收项 | 结果 |
|---|---|
| 四类角色 manifest | PASS |
| allowed/denied browser cases | 20/20 PASS |
| 菜单与 route gate | PASS |
| Tab/card/button gate | PASS |
| RAW 403 可见 | 0 |
| known unauthorized requests | 0 |
| unauthorized data access | 0 |
| browser console/page errors | 0 |
| 附件 cross-user/cross-tenant | 0 |
| 非法审计/事实表写入 | 拒绝，PASS |

覆盖角色：系统管理员、运营/交易分析、复核/审核、模型/知识管理员。角色能力来自实时权限 manifest，证据中不保存 JWT、密钥或完整 DSN。

## 数据库安全边界

runtime role 仅取得合法运行链所需的最小权限。`audit_logs_id_seq` 的序列权限修复不包含表级扩权、schema owner、数据库 owner、superuser、CREATEDB、CREATEROLE 或 BYPASSRLS；非法与越权写入继续被拒绝。

## 证据

- `round1_role_permission_manifests_4a108ce.json`
- `round1_role_rbac_browser_4a108ce.json`
- `round1_security_contracts_44e048d_v2.xml`
- `acl_acceptance_48087e8.json`
- `acl_forecast_tables_minimal_acceptance.json`

以上均位于仓库外 Round 1 证据目录。Round 2 将在 `FINAL_PRE_RELEASE_SHA` 上重新执行同 SHA RBAC 门禁。

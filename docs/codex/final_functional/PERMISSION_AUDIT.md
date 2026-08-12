# Permission Audit

## 身份矩阵

| 身份 | Tenant / Workspace | 结果 |
|---|---|---|
| Admin A | default / default | 设置、用户、任务、AI 会话等授权路径 PASS |
| Analyst A | default / default | Knowledge、Report、Model、Task 可读；Settings/User 受控 403 |
| Viewer A | default / default | Knowledge、Report 可读；Model/Task/Settings/User/AI/ChatBI 受控 403 |
| Admin B | tenant B / workspace B | 仅看到本租户数据；与 Tenant A 的 Session/Document 交集均为空 |
| Anonymous | 无 | 设置接口受控 401 |

## 安全结论

- Cross-user leakage：0。
- Cross-tenant leakage：0。
- Unauthorized disclosure：0。
- 跨租户文档精确读取：404。
- Memory、RAG、ChatBI、Report、Model、Task、Settings 均由 API 权限与服务端身份约束；前端隐藏不是授权边界。
- Prompt Injection、任意 SQL、白名单 Join、敏感字段与日志脱敏均由现有 Security / ChatBI / RAG 矩阵覆盖。

证据：`api_functional_audit_rc4.json`、`browser_permission_audit_rc.json`、`memory_chatbi_isolated_merged_final_rerun.json`、`chatbi_golden_50.json`。


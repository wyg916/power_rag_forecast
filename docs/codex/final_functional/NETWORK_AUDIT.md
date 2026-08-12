# Network Audit

## 最终正常路径

- 最终最新代码浏览器阶段共记录 115 个后端请求。
- 2xx：115；Unexpected 4xx：0；Unexpected 5xx：0；Unhandled Timeout：0。
- ChatBI、企业 RAG、登录、32 路由 API 和任务稳定性复核均包含在最终运行中。
- 预期权限拒绝不计入 Unexpected：匿名读取设置 401；Viewer/Analyst 对未授权 Model、Task、Settings、User、AI、ChatBI 返回受控 403；跨租户文档读取返回 404。

## 失败语义

离线 Provider、无权限、空数据、错误参数和不可用依赖均保留明确失败状态；未发现接口失败后返回静态成功结果或前端补数。网络正常路径不含 4xx/5xx。

## 证据

- `browser_runtime_release_final/api.stdout.log`
- `browser_release_final_ai.json`
- `browser_release_final_routes.json`
- `api_functional_audit_rc4.json`
- `browser_permission_audit_rc.json`


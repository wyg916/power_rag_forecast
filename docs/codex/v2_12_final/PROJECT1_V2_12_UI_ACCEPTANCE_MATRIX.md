# PROJECT1 v2.12.0 UI Acceptance Matrix

## Round 1 汇总

- 正式业务路由：`32/32 PASS`
- Viewport：`1280x720`、`1366x768`、`1440x900`、`1920x1080`
- 路由 × viewport：`128/128 PASS`
- 四类真实角色：PASS
- 页面副标题可见计数：`0`
- 默认技术元数据块计数：`0`
- RAW 403 可见计数：`0`
- 已知未授权请求计数：`0`
- 未授权数据访问：`0`
- 横向溢出：`0`
- console error/warning：`0/0`
- page error：`0`
- unexpected request failure：`0`

## 组件级覆盖

| 范围 | 结果 | 判定口径 |
|---|---|---|
| 菜单与 route | PASS | capability manifest；禁止按角色名称猜测 |
| Tab/card/button | PASS | 不授权则不展示或禁用；后端仍独立拒绝 |
| filter/search | PASS | 真实 API 状态；无固定值假成功 |
| Sticky Header/table | PASS | 四 viewport 无遮挡/溢出 |
| modal/drawer | PASS | 可打开、关闭、焦点与滚动正常 |
| AI floating launcher | PASS | 页面切换可见、会话保留、context 更新 |
| Loading/Empty/Error/Unauthorized | PASS | 不用 fallback 伪装成功 |

## 证据和限制

权威证据为 `round1_ui_browser_matrix_4a108ce.json` 与 `round1_role_rbac_browser_4a108ce.json`。Round 1 最终 SHA 相对该浏览器证据 SHA 的差异仅为 `scripts/runtime_control.py` 与 `tests/test_runtime_control.py`，没有前端、权限 manifest 或浏览器契约变化。

本矩阵仅代表本地 RC 浏览器验收，不代表生产网络、TLS 或容量验收。

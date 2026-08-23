# PROJECT1 v2.12.0 Permission Matrix Drift Closure Evidence

## 判定

- 起始失败候选：`dfd9ebe958762aa30792b8681521f5dd67aa4e22`
- 权限矩阵修复：`c1e33b3e500874497276a8d0ffff1119d5fcee2a`
- 真源：`scripts/day3_generate_permission_matrix.py` 从 FastAPI runtime route dependency、`required_permission()` 和 `ROLE_PERMISSIONS` 生成 CSV/Markdown；CSV 同时是运行时中间件读取的机器可读策略快照。
- 影响范围：仅四个 GET 路由的 `Current Guard` 从 `settings:write` 同步为 `settings:read`；所有 POST/PUT 写路由继续使用 `settings:write`。
- 数据库影响：无业务或 public 数据/结构变化；完整后端测试在一次性受限 schema/role 中执行，public 前后签名一致且临时对象残留为 0。

## 零成本门禁

| 门禁 | 结果 |
|---|---|
| generator reproducibility | PASS；207 method+path、191 path、7 public、200 protected |
| Python API security / settings guards / role mapping | PASS；54 passed |
| Frontend permission policy | PASS；4 passed |
| Backend Full（提交前） | PASS；1207 collected、1173 passed、34 skipped、0 failed、0 errors |
| Matrix drift | 0 |
| Write-route permission regression | 0 |

## 仓库外原始证据

根目录：`E:\项目一_v2.12.0_备份\PERMISSION_MATRIX_DRIFT_20260823_144740484`

```text
4C6BDB457AEF2D219A69613C6F0A0F6A645BE3C3F08C9FB91BC4E66572E35B91  targeted_permission_pytest.xml
8C5FB92ABD3B17682B421FC535B23AA3D1C2CFB2F8670D99CAF64B5B39A81578  targeted_frontend_permission.tap
D4C71EC9BB367A62F306B63BC14110DAA38CC5C7350380415753015B6B981598  precommit_backend_full.xml
9CE1B9B7A0F1105DDB6CC4EC4DFA3AD5F8FD83B98499124AC3C9237EA6DF6EE5  precommit_backend_full_guard.json
```

本文件只记录进入新 SAME-SHA Full Regression 的前置闭环，不把不同 SHA 的结果冒充最终发布 PASS。

# M5 fail-closed 服务缝合最小接收证据

## 接收边界

- 来源参考：`948700f27ca1e3a3922d65a9236f5560c3910ac0` 中的 `knowledge_enterprise_service.py`。
- 按用户规则不接收同提交的主线 knowledge Router、权限矩阵、生成脚本和 API 测试。
- 新增 1 个 fail-closed 服务缝合模块与 1 个定向测试文件；数据库实现尚未安装时唯一状态为 unavailable。

## 目的与副作用

- 该最小公共 seam 是 RT5 应用编排的显式依赖，不能用 fallback 或动态替身绕过。
- PostgreSQL、Qdrant、Router、模型和网络写入：0；正式 API 暴露：0。
- 定向 seam 测试：`9 passed in 0.47s`；敏感扫描在提交门禁中记录。

## 回滚

使用普通 `git revert <M5-seam-integration-commit>`；无外部状态需要恢复。

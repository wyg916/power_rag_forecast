# RAG-R1 Qdrant 私有部署基础

- 结果：静态部署门禁 `PASS`；实际 Qdrant 启动 `PENDING`。
- 镜像契约：`qdrant/qdrant:v1.18.2@sha256:<required>`，禁止 `latest` 和未固定 digest。
- 网络：只映射 `127.0.0.1:6333`，不暴露 gRPC 6334。
- 安全：TLS、strict mode、Admin/Read-only Key 分离；backend/worker 仅接收 Read-only Key。
- 激活：独立文件 `deploy/rag-r1/docker-compose.qdrant.yml`，必须显式使用 `rag-r1` profile；没有修改公共 `docker-compose.yml`。
- 数据：真实运行根必须在 E 盘、仓库外；storage/snapshots/tls 分目录。
- 发布器：当前叠加层不暴露尚未完成的 publisher 命令，避免伪能力；后续由可验证的发布适配器包接入。
- 验证：部署、安全、runtime、release 相关 58 passed。
- 本机：Docker Desktop 引擎可用；Qdrant 1.18.2 镜像未缓存，尚未发起外网拉取。
- Fail-closed 证据：`preflight_static.json` 明确报告 digest/key 缺失且不输出 Secret。

## 回滚

执行 `git revert <本包提交>`；本包未创建容器、卷、Qdrant Collection 或 E 盘运行资产。

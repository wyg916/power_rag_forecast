# FastAPI 后端

本目录是“售电交易 AI 辅助决策平台”的本地 Web 后端。后端不重写现有预测模型，而是复用项目根目录的 Python 服务、结果文件、MySQL 表和模型运维能力。

启动：

```powershell
cd E:\智能运营分析项目
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

接口文档：

- http://127.0.0.1:8000/docs

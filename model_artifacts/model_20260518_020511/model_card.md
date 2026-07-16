# 模型版本说明

- 模型版本：model_20260518_020511
- 特征版本：features_0eac6d42fec0
- 基础模型：线性回归
- 高峰专项模型：Peak_RandomForest
- 尖峰分类器：Spike_HGB_Classifier
- 融合参数 alpha：0.0
- 高峰 floor：0.0

## 用途

用于 PJM/DOM 日前电价未来 24 小时预测，并增强高峰与尖峰风险时段的拟合能力。

## 适用范围

适用于当前项目主表字段、特征工程版本和训练窗口。预测阶段必须使用 `feature_cols.json` 中相同的特征列顺序。

## 已知限制

该 artifact 仍来自 v4_fix1 兼容训练流程；阶段三将进一步接入 model_registry、prediction_tracking、真实值回填和候选模型上线控制。

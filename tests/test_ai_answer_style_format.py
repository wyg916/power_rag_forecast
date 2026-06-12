from __future__ import annotations

from backend.app.ai_assistant.service import apply_answer_style_contract


BASE_ANSWER = "晚高峰价格可能会高，因为用电需求集中抬升，供给侧如果不够宽松，价格容易被放大。运营上要重点关注高峰小时价格和负荷变化。"


def test_professional_brief_has_short_structure() -> None:
    answer = apply_answer_style_contract(BASE_ANSWER, "professional_brief", "risk_reason", "为什么晚高峰价格可能会高？")

    assert "结论" in answer
    assert "主要原因" in answer
    assert "建议" in answer
    assert "###" not in answer
    assert "**" not in answer
    assert max(len(part) for part in answer.split("\n\n")) < 220


def test_professional_deep_has_layered_structure() -> None:
    answer = apply_answer_style_contract(
        "模型误差变大不一定马上重训，需要先确认样本量、数据新鲜度、特征漂移和业务场景是否变化。还要检查真实值回填是否充分。",
        "professional_deep",
        "model_error_status",
        "模型误差变大一定要重训吗？",
    )

    assert "结论" in answer
    assert "关键原因" in answer
    assert "建议关注" in answer
    assert "风险边界" in answer


def test_business_advice_has_action_sections_and_boundary() -> None:
    answer = apply_answer_style_contract(
        "峰谷价差变大说明价格波动扩大，既可能带来套利空间，也会增加高峰暴露风险。需要复核合同覆盖和高峰时段预测。",
        "business_advice",
        "trading_risk_summary",
        "峰谷价差变大说明什么？",
    )

    assert "核心判断" in answer
    assert "建议动作" in answer
    assert "重点监控指标" in answer
    assert "边界说明" in answer
    assert "不等同于交易指令或调度指令" in answer


def test_report_style_has_report_sections() -> None:
    answer = apply_answer_style_contract(
        "明天电价风险需要重点关注晚高峰。负荷、天气和现货市场偏差可能放大价格波动。",
        "report_style",
        "trading_risk_summary",
        "用日报风格总结明天电价风险",
    )

    assert "摘要" in answer
    assert "风险判断" in answer
    assert "原因分析" in answer
    assert "建议动作" in answer

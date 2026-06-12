from __future__ import annotations

from typing import Any


def _money(value: Any) -> str:
    try:
        return f"{float(value):.2f} USD/MWh"
    except Exception:
        return "-"


def _evidence(name: str, value: Any, source: str, field: str | None = None) -> dict[str, Any]:
    item = {"name": name, "value": value, "source": source}
    if field:
        item["field"] = field
    return item


def _tool(results: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((item for item in results if item.get("tool") == name), {})


def _question_subject(question: str, entities: dict[str, object]) -> str:
    text = question or ""
    if "最低" in text or "低价" in text:
        return "lowest"
    if "峰谷" in text or "价差" in text:
        return "spread"
    if "均价" in text or "平均" in text:
        return "avg"
    return str(entities.get("subject") or "highest")


def _related(intent: str) -> list[dict[str, Any]]:
    page_map = {
        "forecast_overview": ("查看预测分析", "forecast"),
        "forecast_extreme": ("查看预测分析", "forecast"),
        "risk_hours": ("查看异常解释", "anomaly"),
        "hour_explain": ("查看预测明细", "forecast"),
        "factor_analysis": ("查看策略建议", "strategy"),
        "weather_analysis": ("查看数据接入", "data"),
        "load_analysis": ("查看数据接入", "data"),
        "renewable_analysis": ("查看数据接入", "data"),
        "strategy_advice": ("查看策略建议", "strategy"),
        "storage_advice": ("查看策略建议", "strategy"),
        "model_status": ("查看模型监控", "models"),
        "report_summary": ("打开报告中心", "report"),
        "data_status": ("查看数据接入", "data"),
    }
    label, page = page_map.get(intent, ("查看首页驾驶舱", "dashboard"))
    return [{"label": label, "action": "open_page", "params": {"page": page}}]


def build_answer(
    question: str,
    intent: str,
    entities: dict[str, object],
    tool_results: list[dict[str, Any]],
    user_role: str = "trader",
    scenario: str = "power_trading",
    answer_style: str = "analysis",
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    answer = ""

    if intent == "forecast_overview":
        data = _tool(tool_results, "get_prediction_overview")
        overview = data.get("overview") or {}
        if not overview.get("available"):
            return _insufficient(overview.get("message") or data.get("message"))
        messages = overview.get("messages") or []
        prefix = ("注意：" + "；".join(messages) + "\n\n") if messages else ""
        factors = overview.get("main_factors") or []
        focus = overview.get("focus_periods") or []
        answer = (
            f"{prefix}结论：当前系统最新预测窗口为 {overview.get('forecast_start')} 至 {overview.get('forecast_end')}，"
            f"{overview.get('market')} 市场预测均价约 {_money(overview.get('avg_price_pred'))}，"
            f"最高价约 {_money(overview.get('peak_price_pred'))}，风险等级为 {overview.get('risk_level') or '-'}。\n\n"
            f"数据依据：最高价时段为 {overview.get('peak_hour') or '-'}，最低价时段为 {overview.get('valley_hour') or '-'}，"
            f"峰谷价差约 {_money(overview.get('peak_valley_spread'))}，模型置信参考值为 {overview.get('model_confidence') or '-'}。\n\n"
            f"原因分析：{'；'.join(factors) if factors else '当前系统未返回明确影响因素。'}\n\n"
            f"风险提示：建议重点关注 {('、'.join(focus) if focus else '暂无显著高风险')} 时段。交易建议仅作为辅助分析参考，仍需结合实时市场和合同敞口复核。"
        )
        evidence.extend(
            [
                _evidence("预测市场", overview.get("market"), "get_prediction_overview", "market"),
                _evidence("预测均价", _money(overview.get("avg_price_pred")), "get_prediction_overview", "avg_price_pred"),
                _evidence("风险等级", overview.get("risk_level"), "get_prediction_overview", "risk_level"),
            ]
        )

    elif intent == "forecast_extreme":
        data = _tool(tool_results, "get_forecast_extremes")
        if data.get("empty"):
            return _insufficient(data.get("message"))
        subject = _question_subject(question, entities)
        if subject == "lowest":
            answer = (
                f"结论：当前预测窗口内最低电价出现在 {data.get('min_price_hour')}，约 {_money(data.get('min_price'))}。\n\n"
                f"依据：该价格低于 24 小时均价 {_money(data.get('avg_price'))}，P25 低价阈值约 {_money(data.get('p25'))}，"
                f"全天峰谷价差约 {_money(data.get('peak_valley_spread'))}。\n\n"
                "建议：可把该小时作为低成本采购、可调负荷转移或储能充电候选窗口；执行前仍需复核合同约束、负荷计划和实时市场变化。"
            )
            evidence.append(_evidence("最低价小时", data.get("min_price_hour"), "get_forecast_extremes", "min_price_hour"))
            evidence.append(_evidence("最低预测电价", _money(data.get("min_price")), "get_forecast_extremes", "min_price"))
        elif subject == "spread":
            answer = (
                f"结论：未来 24 小时峰谷价差约 {_money(data.get('peak_valley_spread'))}，价格弹性较明显。\n\n"
                f"依据：最高价在 {data.get('max_price_hour')}，约 {_money(data.get('max_price'))}；最低价在 {data.get('min_price_hour')}，约 {_money(data.get('min_price'))}；"
                f"均价约 {_money(data.get('avg_price'))}。\n\n"
                "建议：高价窗口重点复核售电敞口，低价窗口评估采购或充电安排，中间时段按常规跟踪，不建议仅凭价差做自动化交易决策。"
            )
            evidence.append(_evidence("峰谷价差", _money(data.get("peak_valley_spread")), "get_forecast_extremes", "peak_valley_spread"))
        else:
            answer = (
                f"结论：当前预测窗口内最高电价出现在 {data.get('max_price_hour')}，约 {_money(data.get('max_price'))}。\n\n"
                f"依据：该价格高于 24 小时均价 {_money(data.get('avg_price'))}，P75 高价阈值约 {_money(data.get('p75'))}，"
                f"全天峰谷价差约 {_money(data.get('peak_valley_spread'))}。\n\n"
                "建议：把该小时作为重点盯盘窗口，先复核售电侧敞口、预测负荷和尖峰概率，再决定是否调整交易计划或储能放电安排。"
            )
            evidence.append(_evidence("最高价小时", data.get("max_price_hour"), "get_forecast_extremes", "max_price_hour"))
            evidence.append(_evidence("最高预测电价", _money(data.get("max_price")), "get_forecast_extremes", "max_price"))

    elif intent == "risk_hours":
        data = _tool(tool_results, "get_high_risk_hours")
        if data.get("empty"):
            return _insufficient(data.get("message"))
        items = data.get("items") or []
        if not items:
            return _insufficient("当前未识别到风险时段。")
        lines = [
            f"- {item.get('hour')}：{_money(item.get('predicted_price'))}，风险 {item.get('risk_level') or '-'}，原因：{'；'.join(item.get('reasons') or [])}"
            for item in items[:5]
        ]
        answer = (
            f"结论：当前最需要关注的风险窗口有 {len(items[:5])} 个，优先看 {items[0].get('hour')}。\n\n"
            "依据：\n" + "\n".join(lines) + "\n\n"
            "建议：这些小时适合进入交易员人工复核清单，重点核对敞口、负荷偏差和尖峰概率，不宜直接自动执行交易动作。"
        )
        evidence.extend(_evidence(f"风险时段 {i+1}", item.get("hour"), "get_high_risk_hours", "hour") for i, item in enumerate(items[:5]))

    elif intent == "hour_explain":
        detail = _tool(tool_results, "get_hour_detail")
        risk = _tool(tool_results, "build_hour_risk_evidence")
        if detail.get("empty"):
            return _insufficient(detail.get("message"))
        reasons = risk.get("reasons") or detail.get("reasons") or []
        reason_text = "；".join(reasons) if reasons else "该小时未触发显著高价、尖峰或高负荷规则。"
        risk_level_text = str(detail.get("risk_level") or "-")
        prob_value = float(detail.get("spike_risk_prob") or 0)
        asserted_high = any(key in question for key in ["风险高", "高风险", "为什么高", "为何高"])
        is_system_high = risk_level_text.lower() in {"high", "高", "高风险"} or prob_value >= 0.5
        conclusion = (
            f"按当前数据看，{detail.get('hour')} 并不是系统标记的高风险小时，但它仍可从价格分位或高峰属性上解释关注原因。"
            if asserted_high and not is_system_high
            else f"{detail.get('hour')} 的风险判断主要看价格分位、尖峰概率和是否处于高峰小时。"
        )
        answer = (
            f"结论：{conclusion} 当前预测电价为 {_money(detail.get('predicted_price'))}，风险标签为 {risk_level_text}。\n\n"
            f"依据：{reason_text} 同时，24 小时均价约 {_money(detail.get('avg_price'))}，P75 阈值约 {_money(detail.get('p75'))}，尖峰概率为 {prob_value:.2%}。\n\n"
            f"建议：{risk.get('recommendation') or '建议谨慎复核该小时交易计划。'}"
        )
        evidence.extend(
            [
                _evidence("目标小时", detail.get("hour"), "get_hour_detail", "hour"),
                _evidence("预测电价", _money(detail.get("predicted_price")), "get_hour_detail", "predicted_price"),
                _evidence("尖峰概率", f"{float(detail.get('spike_risk_prob') or 0):.2%}", "get_hour_detail", "spike_risk_prob"),
            ]
        )

    elif intent == "storage_advice":
        data = _tool(tool_results, "get_storage_advice")
        if data.get("empty"):
            return _insufficient(data.get("message"))
        charge = data.get("charge_windows") or []
        discharge = data.get("discharge_windows") or []
        charge_text = "、".join(f"{x.get('hour')}({_money(x.get('price'))})" for x in charge) or "暂无明显低价充电窗口"
        discharge_text = "、".join(f"{x.get('hour')}({_money(x.get('price'))})" for x in discharge) or "暂无明显高价放电窗口"
        spread = float(data.get("peak_valley_spread") or 0)
        answer = (
            f"结论：当前储能可以按“低价充电、高价放电”做候选安排，峰谷价差约 {_money(spread)}。\n\n"
            f"依据：推荐充电候选窗口：{charge_text}；推荐放电候选窗口：{discharge_text}。\n\n"
            "建议：若实际设备允许，先核对 SOC、容量、充放电效率和并网约束；若价差低于设备损耗与交易成本，不建议机械执行套利。"
        )
        evidence.extend(_evidence("放电候选窗口", x.get("hour"), "get_storage_advice", "discharge_windows") for x in discharge)
        evidence.extend(_evidence("充电候选窗口", x.get("hour"), "get_storage_advice", "charge_windows") for x in charge)

    elif intent == "factor_analysis":
        overview = (_tool(tool_results, "get_prediction_overview").get("overview") or {})
        load_data = _tool(tool_results, "get_load_forecast")
        weather = _tool(tool_results, "get_weather_forecast")
        renewable = _tool(tool_results, "get_renewable_forecast")
        model_data = _tool(tool_results, "get_model_explain")
        knowledge = _tool(tool_results, "search_knowledge").get("items") or []
        if not overview.get("available"):
            return _insufficient(overview.get("message") or "预测结果不可用。")
        messages = overview.get("messages") or []
        factors = list(overview.get("main_factors") or [])
        if load_data.get("available") and load_data.get("max_load") is not None:
            factors.append(f"负荷预测最高约 {float(load_data.get('max_load') or 0):.0f}，高负荷时段通常会推升边际供给成本")
        if weather.get("available") and weather.get("avg_temperature") is not None:
            factors.append(f"天气温度均值约 {float(weather.get('avg_temperature') or 0):.1f}，可能通过制冷/采暖负荷影响电价")
        if not renewable.get("available"):
            factors.append("当前系统未接入新能源出力预测，不能量化风光出力对本次预测的贡献")
        if model_data.get("feature_importance"):
            top = model_data["feature_importance"][0]
            factors.append(f"模型特征重要性显示 {top.get('feature')} 对预测影响靠前")
        if knowledge:
            factors.append("知识库规则提示：" + knowledge[0].get("content", "")[:120])
        answer = (
            f"{('注意：' + '；'.join(messages) + chr(10) + chr(10)) if messages else ''}"
            f"结论：当前预测结果的主要影响因素可以归纳为负荷、历史价格惯性、天气口径、尖峰风险和模型关键特征。当前风险等级为 {overview.get('risk_level') or '-'}。\n\n"
            f"数据依据：预测均价约 {_money(overview.get('avg_price_pred'))}，最高价约 {_money(overview.get('peak_price_pred'))}，重点时段包括 {'、'.join(overview.get('focus_periods') or []) or '-'}。\n\n"
            "原因分析：" + "；".join(factors[:6]) + "。\n\n"
            "风险提示：这些因素只能说明当前预测的业务逻辑，不代表确定涨跌。若用于交易决策，应继续跟踪实时负荷、机组约束、天气变化和最新日前市场报价。"
        )
        evidence.append(_evidence("预测均价", _money(overview.get("avg_price_pred")), "get_prediction_overview", "avg_price_pred"))
        evidence.append(_evidence("影响因素", "；".join(factors[:4]), "stage1_tools", "main_factors"))

    elif intent == "load_analysis":
        load_data = _tool(tool_results, "get_load_forecast")
        knowledge = _tool(tool_results, "search_knowledge").get("items") or []
        message = load_data.get("message") or ""
        load_text = (
            f"当前负荷预测均值约 {float(load_data.get('avg_load') or 0):.0f}，最高约 {float(load_data.get('max_load') or 0):.0f}。"
            if load_data.get("available") and load_data.get("avg_load") is not None
            else "当前系统未查询到可量化的负荷预测。"
        )
        kb = knowledge[0].get("content") if knowledge else "负荷升高通常意味着用电需求增加，若可用低成本机组不足，市场需要调用更高成本机组，从而抬升边际出清价格。"
        answer = (
            f"{('注意：' + message + chr(10) + chr(10)) if message else ''}"
            f"结论：负荷偏高可能推高电价，但影响大小取决于供给余量、机组报价、输电约束和新能源出力。\n\n"
            f"数据依据：{load_text}\n\n"
            f"原因分析：{kb}\n\n"
            "建议关注：晚高峰负荷、温度变化、实时负荷偏差和高价机组被调用的可能性。"
        )
        evidence.append(_evidence("负荷预测", load_text, "get_load_forecast"))
        if knowledge:
            evidence.append(_evidence("知识库", knowledge[0].get("title"), knowledge[0].get("source")))

    elif intent == "weather_analysis":
        weather = _tool(tool_results, "get_weather_forecast")
        knowledge = _tool(tool_results, "search_knowledge").get("items") or []
        requested_date = entities.get("date") or weather.get("date") or "-"
        message = weather.get("message") or ""
        if weather.get("available"):
            temp_bits = []
            if weather.get("avg_temperature") is not None:
                temp_bits.append(f"平均气温约 {float(weather.get('avg_temperature') or 0):.1f}")
            if weather.get("max_temperature") is not None:
                temp_bits.append(f"最高约 {float(weather.get('max_temperature') or 0):.1f}")
            if weather.get("min_temperature") is not None:
                temp_bits.append(f"最低约 {float(weather.get('min_temperature') or 0):.1f}")
            weather_text = "，".join(temp_bits) if temp_bits else "当前天气数据没有可计算的温度字段"
            answer = (
                f"{('注意：' + message + chr(10) + chr(10)) if message else ''}"
                f"结论：{weather.get('city') or '默认天气点'} 在 {requested_date} 的天气数据口径为：{weather_text}。\n\n"
                f"数据依据：天气数据来自系统已接入的数据源，当前返回日期为 {weather.get('date') or '-'}，匹配请求日期：{'是' if weather.get('date_matched') else '否'}。\n\n"
                "建议关注：如果你只是问天气，本回答不展开电价判断；如果要分析天气对电价的影响，可以继续问“天气会怎么影响明天电价”。"
            )
            evidence.append(_evidence("天气城市/点位", weather.get("city"), "get_weather_forecast", "city"))
            evidence.append(_evidence("天气温度", weather_text, "get_weather_forecast", "temperature"))
        else:
            answer = (
                f"结论：当前系统未查询到可用天气数据。\n\n"
                f"依据：{weather.get('message') or '天气工具没有返回有效数据。'}\n\n"
                "建议：先检查数据接入中心的天气数据源，或运行数据刷新任务后再查询。"
            )
            evidence.append(_evidence("天气数据状态", weather.get("message") or "不可用", "get_weather_forecast"))
        if knowledge:
            evidence.append(_evidence("知识库", knowledge[0].get("title"), knowledge[0].get("source")))

    elif intent == "renewable_analysis":
        renewable = _tool(tool_results, "get_renewable_forecast")
        knowledge = _tool(tool_results, "search_knowledge").get("items") or []
        kb = knowledge[0].get("content") if knowledge else "新能源出力下降会减少低边际成本电源供给，若负荷维持高位，系统可能需要调用更高成本机组，电价上行风险会增加。"
        answer = (
            f"结论：当前系统未查询到新能源出力预测数据，以下仅为通用分析。\n\n"
            f"数据依据：{renewable.get('message') or '新能源工具未返回可用数据。'}\n\n"
            f"原因分析：{kb}\n\n"
            "风险提示：如果风电或光伏出力下降同时叠加晚高峰高负荷，日前和实时价格都可能出现更强波动；需要结合实际新能源预测和机组约束再判断。"
        )
        evidence.append(_evidence("新能源数据状态", renewable.get("message"), "get_renewable_forecast"))
        if knowledge:
            evidence.append(_evidence("知识库", knowledge[0].get("title"), knowledge[0].get("source")))

    elif intent == "strategy_advice":
        data = _tool(tool_results, "get_trading_advice")
        if data.get("empty"):
            return _insufficient(data.get("message"))
        risk_windows = data.get("risk_windows") or []
        risk_text = "、".join(item.get("hour", "-") for item in risk_windows[:5]) or "暂无显著高风险小时"
        answer = (
            f"结论：今天交易建议按高价窗口、低价窗口和风险复核窗口三类处理。{data.get('summary')}\n\n"
            f"依据：高价窗口为 {data.get('high_price_window', {}).get('hour')}，低价窗口为 {data.get('low_price_window', {}).get('hour')}，风险复核窗口包括 {risk_text}。\n\n"
            "建议：高价窗口重点复核售电敞口和尖峰风险，低价窗口评估低成本采购或储能充电；风险窗口保留人工判断，避免把预测结果当作确定交易指令。"
        )
        evidence.append(_evidence("高价窗口", data.get("high_price_window", {}).get("hour"), "get_trading_advice"))
        evidence.append(_evidence("低价窗口", data.get("low_price_window", {}).get("hour"), "get_trading_advice"))

    elif intent == "model_status":
        data = _tool(tool_results, "get_model_error_summary")
        explain = _tool(tool_results, "get_model_explain")
        active = data.get("active_model") or {}
        rows = data.get("error_rows") or []
        confidence = explain.get("model_confidence")
        importance = explain.get("feature_importance") or []
        top_features = "、".join(str(item.get("feature")) for item in importance[:3]) or "暂无特征重要性明细"
        confidence_text = f"{float(confidence):.2f}" if confidence is not None else "暂无"
        if rows:
            row = rows[0]
            answer = (
                f"结论：最近有真实值回填的模型是 {row.get('model_version') or active.get('model_version') or '-'}，近 30 天样本数 {row.get('sample_count') or 0}，MAE 约 {float(row.get('mae') or 0):.2f}，RMSE 约 {float(row.get('rmse') or 0):.2f}。\n\n"
                f"依据：当前 Active 模型为 {active.get('model_version') or '-'}，状态 {active.get('status') or '-'}，模型置信参考值 {confidence_text}，关键特征包括 {top_features}。\n\n"
                "建议：如果误差连续多日抬升，且集中在早晚高峰或尖峰时段，再启动重训或候选模型对比；样本不足时不要把单日波动误判为模型退化。预测结果适合做辅助研判，不应作为确定交易指令。"
            )
            evidence.append(_evidence("模型 MAE", f"{float(row.get('mae') or 0):.2f}", "get_model_error_summary", "mae"))
            evidence.append(_evidence("模型置信参考值", confidence_text, "get_model_explain", "model_confidence"))
        else:
            answer = (
                f"结论：当前真实值回填样本不足，不能严谨判断模型误差是否变大。Active 模型为 {active.get('model_version') or '-'}。\n\n"
                f"依据：prediction_tracking 暂未返回近 30 天有效误差样本；模型置信参考值 {confidence_text}，关键特征包括 {top_features}。\n\n"
                "建议：先补齐真实电价回填，再观察近 7 天和近 30 天 MAE/RMSE 趋势；在样本不足时只能把当前结果作为辅助判断。"
            )
            evidence.append(_evidence("Active 模型", active.get("model_version") or "-", "get_model_error_summary", "active_model"))
            evidence.append(_evidence("模型解释", top_features, "get_model_explain", "feature_importance"))

    elif intent == "report_summary":
        data = _tool(tool_results, "get_report_summary")
        summary = data.get("summary") or {}
        core = summary.get("executive_summary") or summary.get("management_summary") or "当前报告没有可读摘要。"
        risk_level = summary.get("risk_level") or "-"
        publish_tip = "报告可作为审核草稿使用，发布前建议人工复核风险时段和交易建议。" if data.get("available") else "当前报告文件未生成，建议先点击报告中心生成日报。"
        answer = (
            f"结论：最新报告状态为 {'已生成' if data.get('available') else '未生成'}，风险等级为 {risk_level}。\n\n"
            f"依据：{core}\n\n"
            f"建议：{publish_tip}"
        )
        evidence.append(_evidence("报告 ID", data.get("report_id") or "-", "get_report_summary", "report_id"))
        evidence.append(_evidence("报告状态", "已生成" if data.get("available") else "未生成", "get_report_summary", "available"))

    elif intent == "data_status":
        data = _tool(tool_results, "get_data_status")
        sources = data.get("sources") or []
        abnormal = [item for item in sources if item.get("status") != "正常"]
        normal_count = len(sources) - len(abnormal)
        abnormal_text = "、".join(item.get("name", "-") for item in abnormal[:5]) or "暂无明显异常"
        answer = (
            f"结论：当前数据源共 {len(sources)} 项，其中 {normal_count} 项正常，异常或需检查项为：{abnormal_text}。\n\n"
            "依据：数据接入状态来自数据库表状态或本地兜底文件，只展示官网/采集源，不暴露本地路径。\n\n"
            "建议：如果预测或报告结果异常，先复核最新时间、行数和缺失值，再运行数据刷新任务。"
        )
        evidence.extend(_evidence(item.get("name", "-"), item.get("status", "-"), "get_data_status", "status") for item in sources[:6])

    elif intent == "compare_history":
        data = _tool(tool_results, "compare_with_yesterday")
        current = data.get("current") or {}
        answer = (
            "结论：当前 Web 侧没有加载可严谨对比的昨日预测窗口，因此不能直接给出同比/环比结论。\n\n"
            f"依据：当前窗口最高价 {current.get('max_price_hour')}（{_money(current.get('max_price'))}），最低价 {current.get('min_price_hour')}（{_money(current.get('min_price'))}），峰谷价差 {_money(current.get('peak_valley_spread'))}。\n\n"
            "建议：若要做历史对比，需要补充昨日同口径预测或真实价格窗口，再比较均价、峰谷价差和高风险小时数量。"
        )
        evidence.append(_evidence("当前预测窗口", current.get("run_id") or "-", "compare_with_yesterday"))

    else:
        extremes = _tool(tool_results, "get_forecast_extremes")
        risks = _tool(tool_results, "get_high_risk_hours")
        advice = _tool(tool_results, "get_trading_advice")
        if extremes.get("empty"):
            return _insufficient(extremes.get("message"))
        risk_hours = "、".join(item.get("hour", "-") for item in (risks.get("items") or [])[:5]) or "暂无显著高风险小时"
        answer = (
            f"结论：未来 24 小时均价约 {_money(extremes.get('avg_price'))}，最高价在 {extremes.get('max_price_hour')}，最低价在 {extremes.get('min_price_hour')}。\n\n"
            f"依据：峰谷价差约 {_money(extremes.get('peak_valley_spread'))}，重点风险窗口包括 {risk_hours}。\n\n"
            f"建议：{advice.get('summary') or '按高价、低价、风险三类窗口复核交易计划。'}"
        )
        evidence.append(_evidence("最高价小时", extremes.get("max_price_hour"), "get_forecast_extremes"))
        evidence.append(_evidence("风险窗口", risk_hours, "get_high_risk_hours"))

    return {"answer": answer, "evidence": evidence, "related_actions": _related(intent)}


def _insufficient(message: Any) -> dict[str, Any]:
    return {
        "answer": f"结论：当前数据不足，无法判断。\n\n依据：{message or '工具没有返回可用数据。'}\n\n建议：先检查预测结果、数据接入状态或重新运行今日分析后再提问。",
        "evidence": [],
        "related_actions": [{"label": "查看数据接入", "action": "open_page", "params": {"page": "data"}}],
    }

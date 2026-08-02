from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from .config import project_config, project_paths
from .data_access import database_engine, jsonable, load_latest_forecast, price_column, query_dataframe, records, report_status


def _write_local_json(name: str, payload: Any) -> None:
    paths = project_paths()
    paths.current_dir.mkdir(parents=True, exist_ok=True)
    (paths.current_dir / name).write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _insert_rows(table_name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    engine = database_engine()
    if engine is None:
        return
    try:
        from database_utils import apply_database_migrations

        apply_database_migrations(project_config())
        pd.DataFrame(rows).to_sql(table_name, engine, if_exists="append", index=False, chunksize=200, method="multi")
    except Exception:
        return


def _forecast_frame(run_id: str = "latest") -> tuple[dict[str, Any], pd.DataFrame]:
    from .source_contract import attach_source_meta, resolve_forecast_source

    run, rows, meta = resolve_forecast_source(run_id)
    payload = attach_source_meta(
        {
            "available": bool(rows),
            "run_id": run.get("run_id"),
            "records": rows,
        },
        meta,
    )
    df = pd.DataFrame(rows)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    return payload, df


def generate_strategy_advice(run_id: str = "latest", persist: bool = True) -> dict[str, Any]:
    from .source_contract import SourceType, attach_source_meta, source_meta

    forecast, df = _forecast_frame(run_id)
    run_id = str(forecast.get("run_id") or run_id)
    if df.empty:
        return attach_source_meta(
            {"run_id": forecast.get("run_id"), "available": False, "items": [], "message": "当前数据不足，无法生成策略建议。"},
            source_meta(
                SourceType.UNAVAILABLE,
                "strategy",
                run_id=forecast.get("run_id"),
                unavailable_reason=(forecast.get("meta") or {}).get("unavailable_reason") or "forecast_unavailable",
                evidence=list((forecast.get("meta") or {}).get("evidence") or []),
            ),
        )

    pcol = price_column(df)
    if not pcol:
        return attach_source_meta(
            {"run_id": run_id, "available": False, "items": [], "message": "预测结果缺少电价字段。"},
            source_meta(SourceType.UNAVAILABLE, "strategy", run_id=run_id, unavailable_reason="price_field_missing"),
        )
    prices = pd.to_numeric(df[pcol], errors="coerce")
    p25 = float(prices.quantile(0.25))
    p75 = float(prices.quantile(0.75))
    spread = float(prices.max() - prices.min())
    prob = pd.to_numeric(df.get("spike_risk_prob", df.get("尖峰风险概率", 0)), errors="coerce").fillna(0)
    load = pd.to_numeric(df.get("forecast_load", pd.Series([None] * len(df))), errors="coerce")
    load_q75 = float(load.quantile(0.75)) if load.notna().any() else None

    items: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        price = float(prices.loc[idx]) if pd.notna(prices.loc[idx]) else None
        if price is None:
            continue
        hour = row.get("datetime")
        hour_text = pd.to_datetime(hour).strftime("%Y-%m-%d %H:%M") if pd.notna(hour) else ""
        risk_prob = float(prob.loc[idx]) if idx in prob.index else 0.0
        forecast_load = float(load.loc[idx]) if idx in load.index and pd.notna(load.loc[idx]) else None
        is_peak = int(row.get("is_peak_hour") or 0) == 1

        def append(scenario: str, risk_level: str, advice_type: str, text_value: str, must_watch: bool) -> None:
            evidence = {
                "target_hour": hour_text,
                "predicted_price": price,
                "p25": p25,
                "p75": p75,
                "spike_risk_probability": risk_prob,
                "forecast_load": forecast_load,
                "is_peak_hour": is_peak,
                "peak_valley_spread": spread,
            }
            items.append(
                {
                    "run_id": run_id,
                    "scenario": scenario,
                    "target_hour": hour_text,
                    "risk_level": risk_level,
                    "advice_type": advice_type,
                    "advice_text": text_value,
                    "evidence": evidence,
                    "category": "交易必看" if must_watch else "扩展参考",
                    "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
                }
            )

        if price >= p75:
            append("售电", "high" if risk_prob >= 0.5 else "medium", "高价提醒", f"{hour_text} 预测电价处于未来 24 小时高位，建议重点复核交易敞口。", True)
        if price <= p25:
            append("售电", "low", "低价窗口", f"{hour_text} 属于低价窗口，可作为低成本采购或负荷引导参考。", False)
        if risk_prob >= 0.5:
            append("售电", "high", "人工复核", f"{hour_text} 尖峰风险概率较高，建议人工复核预测、负荷和交易计划。", True)
        if is_peak and forecast_load is not None and load_q75 is not None and forecast_load >= load_q75:
            append("售电", "medium", "晚高峰/高负荷提醒", f"{hour_text} 为高峰且预测负荷偏高，建议关注购电成本和敞口风险。", True)

    low_hours = df.loc[prices.nsmallest(min(3, len(df))).index]
    high_hours = df.loc[prices.nlargest(min(3, len(df))).index]
    for _, row in low_hours.iterrows():
        hour_text = pd.to_datetime(row.get("datetime")).strftime("%Y-%m-%d %H:%M") if pd.notna(row.get("datetime")) else ""
        items.append(
            {
                "run_id": run_id,
                "scenario": "储能",
                "target_hour": hour_text,
                "risk_level": "low",
                "advice_type": "推荐充电时段",
                "advice_text": f"{hour_text} 预测价格相对较低，可作为储能充电参考窗口。",
                "evidence": {"target_hour": hour_text, "predicted_price": row.get(pcol), "peak_valley_spread": spread},
                "category": "扩展参考",
                "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            }
        )
    for _, row in high_hours.iterrows():
        hour_text = pd.to_datetime(row.get("datetime")).strftime("%Y-%m-%d %H:%M") if pd.notna(row.get("datetime")) else ""
        items.append(
            {
                "run_id": run_id,
                "scenario": "储能",
                "target_hour": hour_text,
                "risk_level": "high",
                "advice_type": "推荐放电时段",
                "advice_text": f"{hour_text} 预测价格处于高位，可作为储能放电或收益窗口参考。",
                "evidence": {"target_hour": hour_text, "predicted_price": row.get(pcol), "peak_valley_spread": spread},
                "category": "扩展参考",
                "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            }
        )

    unique: list[dict[str, Any]] = []
    seen = set()
    for item in items:
        key = (item["scenario"], item["target_hour"], item["advice_type"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    if persist:
        db_rows = []
        for item in unique:
            row = dict(item)
            row["evidence_json"] = json.dumps(jsonable(row.pop("evidence")), ensure_ascii=False)
            row.pop("category", None)
            db_rows.append(row)
        _insert_rows("strategy_advice", db_rows)
        _write_local_json("strategy_advice_latest.json", {"run_id": run_id, "items": unique})
    base_meta = forecast.get("meta") or {}
    return attach_source_meta(
        {
            "run_id": run_id,
            "available": bool(unique),
            "items": jsonable(unique),
            "thresholds": {"p25": p25, "p75": p75, "spread": spread},
        },
        source_meta(
            SourceType.DERIVED,
            "strategy",
            run_id=run_id,
            generated_at=base_meta.get("generated_at"),
            model_version=base_meta.get("model_version"),
            feature_version=base_meta.get("feature_version"),
            schema_hash=base_meta.get("schema_hash"),
            is_stale=bool(base_meta.get("is_stale")),
            stale_reason=base_meta.get("stale_reason"),
            evidence=list(base_meta.get("evidence") or []) + [{"derivation": "strategy_advice", "persisted": persist}],
        ),
    )


def generate_anomaly_explanations(run_id: str = "latest", persist: bool = True) -> dict[str, Any]:
    from .source_contract import SourceType, attach_source_meta, source_meta

    forecast, df = _forecast_frame(run_id)
    run_id = str(forecast.get("run_id") or run_id)
    if df.empty:
        return attach_source_meta(
            {"run_id": forecast.get("run_id"), "available": False, "items": [], "message": "当前数据不足，无法生成异常解释。"},
            source_meta(
                SourceType.UNAVAILABLE,
                "strategy",
                run_id=forecast.get("run_id"),
                unavailable_reason=(forecast.get("meta") or {}).get("unavailable_reason") or "forecast_unavailable",
            ),
        )
    pcol = price_column(df)
    if not pcol:
        return {"run_id": run_id, "items": [], "message": "预测结果缺少电价字段。"}
    price = pd.to_numeric(df[pcol], errors="coerce")
    p75 = float(price.quantile(0.75))
    prob = pd.to_numeric(df.get("spike_risk_prob", df.get("尖峰风险概率", 0)), errors="coerce").fillna(0)
    load = pd.to_numeric(df.get("forecast_load", pd.Series([None] * len(df))), errors="coerce")
    load_q75 = float(load.quantile(0.75)) if load.notna().any() else None
    items: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        reasons = []
        risk = "low"
        p = float(price.loc[idx]) if pd.notna(price.loc[idx]) else None
        if p is None:
            continue
        risk_prob = float(prob.loc[idx]) if idx in prob.index else 0.0
        forecast_load = float(load.loc[idx]) if idx in load.index and pd.notna(load.loc[idx]) else None
        if p >= p75:
            reasons.append("预测电价高于未来 24 小时 P75 阈值")
            risk = "medium"
        if risk_prob >= 0.5:
            reasons.append("尖峰风险概率较高")
            risk = "high"
        if int(row.get("is_peak_hour") or 0) == 1:
            reasons.append("目标时段处于高峰小时")
        if forecast_load is not None and load_q75 is not None and forecast_load >= load_q75:
            reasons.append("预测负荷处于较高水平")
        if not reasons:
            continue
        hour_text = pd.to_datetime(row.get("datetime")).strftime("%Y-%m-%d %H:%M") if pd.notna(row.get("datetime")) else ""
        evidence = {
            "predicted_price": p,
            "p75": p75,
            "spike_risk_probability": risk_prob,
            "forecast_load": forecast_load,
            "is_peak_hour": row.get("is_peak_hour"),
        }
        items.append(
            {
                "run_id": run_id,
                "target_hour": hour_text,
                "anomaly_type": "高价/尖峰/高峰负荷" if risk == "high" else "价格偏高",
                "risk_level": risk,
                "explanation": "；".join(reasons) + "。",
                "recommendation": "建议交易员重点复核该时段交易计划，并结合实时市场变化谨慎调整。" if risk == "high" else "建议关注该时段价格波动，并纳入日报风险说明。",
                "evidence": evidence,
                "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
            }
        )
    if persist:
        db_rows = []
        for item in items:
            row = dict(item)
            row["evidence_json"] = json.dumps(jsonable(row.pop("evidence")), ensure_ascii=False)
            db_rows.append(row)
        _insert_rows("anomaly_explanations", db_rows)
        _write_local_json("anomaly_explanations_latest.json", {"run_id": run_id, "items": items})
    base_meta = forecast.get("meta") or {}
    return attach_source_meta(
        {"run_id": run_id, "available": bool(items), "items": jsonable(items)},
        source_meta(
            SourceType.DERIVED,
            "strategy",
            run_id=run_id,
            generated_at=base_meta.get("generated_at"),
            model_version=base_meta.get("model_version"),
            feature_version=base_meta.get("feature_version"),
            schema_hash=base_meta.get("schema_hash"),
            is_stale=bool(base_meta.get("is_stale")),
            stale_reason=base_meta.get("stale_reason"),
            evidence=list(base_meta.get("evidence") or []) + [{"derivation": "anomaly_explanation", "persisted": persist}],
        ),
    )


def answer_chat(
    question: str,
    session_id: str | None = None,
    run_id: str = "latest",
    market: str | None = None,
    date: str | None = None,
    page_context: dict[str, Any] | None = None,
    scenario: str = "power_trading",
    user_role: str = "trader",
    answer_style: str = "analysis",
    model_provider: str = "auto",
    debug: bool = False,
    retrieval_context: Any = None,
    enterprise_store: Any = None,
    enterprise_unavailable_reason: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    from .ai.assistant_service import answer_chat as answer_chat_v2

    return answer_chat_v2(
        question=question,
        session_id=session_id,
        run_id=run_id,
        market=market,
        date=date,
        page_context=page_context,
        scenario=scenario,
        user_role=user_role,
        answer_style=answer_style,
        model_provider=model_provider,
        debug=debug,
        retrieval_context=retrieval_context,
        enterprise_store=enterprise_store,
        enterprise_unavailable_reason=enterprise_unavailable_reason,
        trace_id=trace_id,
    )

    session_id = session_id or "chat_" + uuid.uuid4().hex[:12]
    forecast = load_latest_forecast()
    df = pd.DataFrame(forecast.get("records") or [])
    pcol = price_column(df) if not df.empty else None
    evidence: list[dict[str, Any]] = []
    answer = "当前数据不足，无法回答该问题。"
    normalized = question.strip().lower()

    if not df.empty and pcol:
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        prices = pd.to_numeric(df[pcol], errors="coerce")
        max_row = df.loc[prices.idxmax()]
        min_row = df.loc[prices.idxmin()]
        high_risk = df[df.get("risk_level", pd.Series(index=df.index, dtype=str)).astype(str).str.lower().isin(["high", "高", "高风险"])]
        p25 = float(prices.quantile(0.25))
        p75 = float(prices.quantile(0.75))
        avg_price = float(prices.mean())
        spread = float(prices.max() - prices.min())

        def hour_text(row) -> str:
            return pd.to_datetime(row.get("datetime")).strftime("%Y-%m-%d %H:%M") if pd.notna(row.get("datetime")) else "-"

        def money(value: Any) -> str:
            try:
                return f"{float(value):.2f} USD/MWh"
            except Exception:
                return "-"

        high_text = "、".join(pd.to_datetime(high_risk["datetime"], errors="coerce").dt.strftime("%H:%M").dropna().head(6).tolist()) if not high_risk.empty and "datetime" in high_risk.columns else "暂无高风险标记"

        if any(key in normalized for key in ["最高", "高价", "风险高", "什么时候电价最高"]):
            answer = (
                f"我先给结论：未来 24 小时里，最高预测电价出现在 {hour_text(max_row)}，价格约 {money(max_row[pcol])}。\\n\\n"
                f"从交易视角看，这个时段不仅高于当前 24 小时均价 {money(avg_price)}，也已经进入高价分位区间（P75 约 {money(p75)}）。"
                f"当前标记风险等级为 {max_row.get('risk_level', '未标记')}，峰谷价差约 {money(spread)}，说明当天价格弹性比较明显。\\n\\n"
                "建议你把这个小时作为重点复核窗口：先确认售电侧敞口和负荷预测，再结合实时市场、机组/输电约束与已有合同仓位决定是否调整交易计划。"
                "如果只是日常监控，这个小时应进入日报和人工复核清单；如果有储能或可调负荷，则可同步评估放电或削峰收益。"
            )
            evidence.append({"type": "forecast", "field": pcol, "target_hour": hour_text(max_row), "value": float(max_row[pcol])})
        elif any(key in normalized for key in ["最低", "低价", "采购", "充电"]):
            answer = (
                f"最低价窗口在 {hour_text(min_row)}，预测价格约 {money(min_row[pcol])}。\\n\\n"
                f"这个价格低于 24 小时均价 {money(avg_price)}，也低于低价分位阈值 P25（约 {money(p25)}），更适合做低成本采购、储能充电或负荷转移参考。\\n\\n"
                "操作上建议分两步看：第一，确认该小时是否与业务负荷、合同约束和调度需求匹配；第二，比较相邻低价小时，避免只盯单点最低价而忽略连续低价区间。"
                "如果用于储能，优先关注充电窗口和后续高价放电窗口之间的价差是否足以覆盖损耗与约束成本。"
            )
            evidence.append({"type": "forecast", "field": pcol, "target_hour": hour_text(min_row), "value": float(min_row[pcol])})
        elif any(key in normalized for key in ["储能", "放电"]):
            strategy = generate_strategy_advice(run_id=run_id, persist=False)
            storage = [x for x in strategy.get("items", []) if x.get("scenario") == "储能"]
            if storage:
                charge = [x for x in storage if "充电" in str(x.get("advice_type", ""))][:3]
                discharge = [x for x in storage if "放电" in str(x.get("advice_type", ""))][:3]
                answer = (
                    "可以。按当前预测，储能策略的核心是“低价充电、高价放电”，但要把设备约束和交易规则一起纳入。\\n\\n"
                    "推荐充电窗口："
                    + ("；".join(x["advice_text"] for x in charge) if charge else "当前没有明显低价充电窗口")
                    + "\\n\\n推荐放电窗口："
                    + ("；".join(x["advice_text"] for x in discharge) if discharge else "当前没有明显高价放电窗口")
                    + "\\n\\n我的建议是：先用这些时段做候选窗口，再核对 SOC、充放电效率、容量约束和是否存在高风险尖峰。"
                    "如果高价窗口同时伴随尖峰概率上升，交易侧要保留人工复核，不要直接自动执行。"
                )
                evidence.extend({"type": "strategy", "target_hour": x["target_hour"], "value": x["advice_type"]} for x in storage[:4])
        elif any(key in normalized for key in ["为什么", "原因", "解释", "异常", "高峰", "早晚"]):
            anomaly = generate_anomaly_explanations(run_id=run_id, persist=False)
            items = anomaly.get("items", [])[:4]
            if items:
                answer = (
                    "从当前预测看，异常或高风险主要来自价格分位、尖峰概率和高峰负荷几个因素叠加。\\n\\n"
                    + "\\n".join(f"- {item.get('target_hour')}：{item.get('explanation')}建议：{item.get('recommendation')}" for item in items)
                    + "\\n\\n这类解释不是单纯看价格高低，而是把预测价、P75 阈值、尖峰概率、是否高峰小时和负荷水平放在一起判断。"
                    "因此更适合作为交易员复核顺序，而不是直接替代人工决策。"
                )
                evidence.extend({"type": "anomaly", "target_hour": x.get("target_hour"), "risk_level": x.get("risk_level")} for x in items)
        elif any(key in normalized for key in ["误差", "模型"]):
            model_errors = query_dataframe(
                """
                SELECT model_version, COUNT(*) AS sample_count, AVG(abs_error) AS mae, MAX(created_at) AS latest_record
                FROM prediction_tracking
                WHERE actual_price IS NOT NULL
                GROUP BY model_version
                ORDER BY latest_record DESC
                LIMIT 5
                """
            )
            if not model_errors.empty:
                row = model_errors.iloc[0]
                answer = (
                    f"最近有真实值回填的模型是 {row.get('model_version')}，当前可用样本数 {int(row.get('sample_count') or 0)}，"
                    f"平均绝对误差约 {float(row.get('mae') or 0):.2f}。\\n\\n"
                    "专业上我会这样判断：如果样本数还偏少，先不要把短期波动解读成模型退化；如果连续多天 MAE/RMSE 抬升，且高峰或尖峰时段误差更明显，就需要启动候选模型对比或重训。\\n\\n"
                    "建议你重点看三件事：误差是否连续扩大、误差是否集中在早晚高峰、当前 Active 模型是否仍优于候选模型。"
                )
                evidence.append({"type": "model_error", "model_version": row.get("model_version"), "mae": float(row.get("mae") or 0)})
            else:
                answer = "目前真实值回填样本不足，不能严谨判断模型误差是否变大。更稳妥的做法是先补齐 prediction_tracking 的真实电价回填，再看近 7 天和近 30 天误差趋势。"
        elif any(key in normalized for key in ["日报", "报告", "总结"]):
            report = report_status()
            summary = report.get("summary") or {}
            core = summary.get("executive_summary") or summary.get("management_summary") or "当前报告摘要字段不足。"
            answer = (
                f"当前最新 AI 报告状态为 {'可下载' if report.get('available') else '未生成'}。\\n\\n"
                f"核心摘要：{core}\\n\\n"
                "如果面向非技术人员，建议重点展示三层信息：第一，明天价格总体方向；第二，哪些小时需要交易员重点盯盘；第三，是否需要调整采购、售电或储能策略。"
                "对外发布前建议先走报告中心的审核动作，避免把预测不确定性当成确定交易指令。"
            )
            evidence.append({"type": "report", "report_id": report.get("report_id"), "available": report.get("available")})
        else:
            answer = (
                "我按当前正式预测先给一个综合判断。\\n\\n"
                f"未来 24 小时均价约 {money(avg_price)}，最高价 {money(prices.max())}，最低价 {money(prices.min())}，峰谷价差约 {money(spread)}。"
                f"高风险时段：{high_text}。\\n\\n"
                "交易上可以按“高价窗口、低价窗口、风险窗口”三类处理：高价窗口复核敞口和售电收益，低价窗口评估采购或储能充电，风险窗口保留人工复核。"
                "你的问题如果涉及具体时段、储能、模型误差或日报，我可以继续按对应数据展开到小时级。"
            )
            evidence.append({"type": "forecast_summary", "rows": len(df), "max_price": float(prices.max()), "min_price": float(prices.min())})

    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    engine = database_engine()
    if engine is not None:
        try:
            from database_utils import apply_database_migrations

            apply_database_migrations(project_config())
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO ai_chat_sessions (session_id, user_id, title, created_at, updated_at)
                        VALUES (:session_id, 'web_user', :title, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    {"session_id": session_id, "title": question[:80]},
                )
                for role, content, ev in [
                    ("user", question, []),
                    ("assistant", answer, evidence),
                ]:
                    conn.execute(
                        text(
                            """
                            INSERT INTO ai_chat_messages (session_id, role, content, evidence_json, created_at)
                            VALUES (:session_id, :role, :content, :evidence_json, CURRENT_TIMESTAMP)
                            """
                        ),
                        {"session_id": session_id, "role": role, "content": content, "evidence_json": json.dumps(jsonable(ev), ensure_ascii=False)},
                    )
        except Exception:
            pass

    return {"session_id": session_id, "answer": answer, "evidence": jsonable(evidence), "created_at": now}


def generate_ai_insights() -> dict[str, Any]:
    forecast = load_latest_forecast()
    df = pd.DataFrame(forecast.get("records") or [])
    summary = forecast.get("summary") or {}
    pcol = price_column(df) if not df.empty else None
    strategy = generate_strategy_advice(persist=False)
    anomaly = generate_anomaly_explanations(persist=False)
    report = report_status()
    model_errors = query_dataframe(
        """
        SELECT model_version, COUNT(*) AS sample_count, AVG(abs_error) AS mae, MAX(created_at) AS latest_record
        FROM prediction_tracking
        WHERE actual_price IS NOT NULL
        GROUP BY model_version
        ORDER BY latest_record DESC
        LIMIT 1
        """
    )

    max_hour = summary.get("max_hour") or "-"
    min_hour = summary.get("min_hour") or "-"
    max_price = summary.get("max_price")
    min_price = summary.get("min_price")
    spread = summary.get("peak_valley_spread")
    focus_hours = summary.get("focus_hours") or []
    strategy_items = strategy.get("items") or []
    anomaly_items = anomaly.get("items") or []
    high_strategy = [item for item in strategy_items if item.get("category") == "交易必看"]

    if forecast.get("available") and pcol:
        forecast_text = (
            f"AI 解读：未来 24 小时最高价在 {max_hour}，最低价在 {min_hour}，"
            f"峰谷价差约 {float(spread or 0):.2f}。"
            f"若交易计划包含高价时段，应优先复核敞口、负荷和尖峰风险。"
        )
    else:
        forecast_text = "AI 解读：当前缺少正式预测结果，建议先运行快速预测或今日分析后再做交易研判。"

    if high_strategy:
        strategy_text = "AI 解读：" + "；".join(item.get("advice_text", "") for item in high_strategy[:3])
    else:
        strategy_text = "AI 解读：当前没有强制交易关注项，可按常规节奏跟踪价格、负荷和风险等级变化。"

    if anomaly_items:
        anomaly_text = "AI 解读：" + "；".join(
            f"{item.get('target_hour')} {item.get('explanation')}" for item in anomaly_items[:3]
        )
    else:
        anomaly_text = "AI 解读：当前未识别到显著高价、尖峰或高负荷叠加异常。"

    if not model_errors.empty:
        row = model_errors.iloc[0]
        model_text = (
            f"AI 解读：最新真实值回填模型为 {row.get('model_version')}，"
            f"样本数 {int(row.get('sample_count') or 0)}，MAE 约 {float(row.get('mae') or 0):.2f}。"
            "建议将误差趋势与 Active 模型版本一起观察。"
        )
    else:
        model_text = "AI 解读：当前真实值回填样本不足，模型效果监控以 Active 模型登记信息为主。"

    sections = {
        "dashboard": {
            "title": "AI 今日研判",
            "content": forecast_text,
            "evidence": [{"max_price": max_price, "min_price": min_price, "focus_hours": focus_hours}],
        },
        "data": {
            "title": "AI 数据接入解读",
            "content": "AI 解读：当前数据源按 PJM 价格、PJM 负荷、NOAA 天气和项目特征工程主表组织；建议优先关注最新时间、缺失值和行数变化。",
            "evidence": [{"source_count": 6}],
        },
        "forecast": {
            "title": "AI 预测解读",
            "content": forecast_text,
            "evidence": [{"max_hour": max_hour, "min_hour": min_hour, "spread": spread}],
        },
        "strategy": {
            "title": "AI 策略解读",
            "content": strategy_text,
            "evidence": [{"strategy_count": len(strategy_items), "must_watch_count": len(high_strategy)}],
        },
        "anomaly": {
            "title": "AI 异常解读",
            "content": anomaly_text,
            "evidence": [{"anomaly_count": len(anomaly_items)}],
        },
        "report": {
            "title": "AI 报告解读",
            "content": f"AI 解读：最新报告当前{'可下载' if report.get('available') else '未生成'}，发布前建议完成通过、驳回或发布审核动作。",
            "evidence": [{"report_id": report.get("report_id"), "available": report.get("available")}],
        },
        "models": {
            "title": "AI 模型监控解读",
            "content": model_text,
            "evidence": records(model_errors),
        },
        "tasks": {
            "title": "AI 任务调度解读",
            "content": "AI 解读：任务中心建议把日常刷新预测、健康检查和模型运维拆成独立定时任务，便于失败定位和人工干预。",
            "evidence": [{"recommended_modes": ["refresh_fast_forecast", "health_check", "model_ops_daily"]}],
        },
    }
    return {"generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"), "sections": jsonable(sections)}


def list_chat_sessions() -> list[dict[str, Any]]:
    df = query_dataframe("SELECT session_id, user_id, title, created_at, updated_at FROM ai_chat_sessions ORDER BY updated_at DESC LIMIT 50")
    return records(df)


def get_chat_session(session_id: str) -> dict[str, Any]:
    messages = query_dataframe(
        "SELECT role, content, evidence_json, created_at FROM ai_chat_messages WHERE session_id = :session_id ORDER BY created_at ASC, id ASC",
        {"session_id": session_id},
    )
    return {"session_id": session_id, "messages": records(messages)}


def _report_review_columns() -> set[str]:
    engine = database_engine()
    if engine is None:
        return set()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'report_reviews'
                    """
                )
            ).mappings().all()
        return {str(row.get("column_name")) for row in rows}
    except Exception:
        return set()


def save_report_review(report_id: str, status: str, reviewer: str, comment: str) -> dict[str, Any]:
    report = report_status(report_id)
    columns = _report_review_columns()
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    row = {
        "report_id": report_id,
        "reviewer": reviewer,
        "created_at": now,
    }
    if "run_id" in columns:
        row["run_id"] = report.get("run_id") or report_id
    if "status" in columns:
        row["status"] = status
    if "action" in columns:
        row["action"] = status
    if "review_comment" in columns:
        row["review_comment"] = comment
    if "comment" in columns:
        row["comment"] = comment
    if "version" in columns:
        row["version"] = 1
    if "updated_at" in columns:
        row["updated_at"] = now
    if "metadata_json" in columns:
        row["metadata_json"] = {"source": "ui_report_review"}
    _insert_rows("report_reviews", [row])
    local_path = project_paths().current_dir / "web_report_reviews.json"
    current = []
    if local_path.exists():
        try:
            current = json.loads(local_path.read_text(encoding="utf-8"))
        except Exception:
            current = []
    current.append(row)
    _write_local_json("web_report_reviews.json", current)
    return row


def list_report_reviews(report_id: str) -> list[dict[str, Any]]:
    columns = _report_review_columns()
    if columns:
        run_id_expr = "run_id" if "run_id" in columns else "NULL AS run_id"
        status_expr = "status" if "status" in columns else ("action AS status" if "action" in columns else "NULL AS status")
        comment_expr = "review_comment" if "review_comment" in columns else ("comment AS review_comment" if "comment" in columns else "NULL AS review_comment")
        version_expr = "version" if "version" in columns else "NULL AS version"
        updated_expr = "updated_at" if "updated_at" in columns else "created_at AS updated_at"
        order_expr = "updated_at" if "updated_at" in columns else "created_at"
        df = query_dataframe(
            f"""
            SELECT report_id, {run_id_expr}, {status_expr}, reviewer,
                   {comment_expr}, {version_expr}, created_at, {updated_expr}
            FROM report_reviews
            WHERE report_id = :report_id
            ORDER BY {order_expr} DESC
            """,
            {"report_id": report_id},
        )
    else:
        df = query_dataframe(
            "SELECT report_id, run_id, status, reviewer, review_comment, version, created_at, updated_at FROM report_reviews WHERE report_id = :report_id ORDER BY updated_at DESC",
            {"report_id": report_id},
        )
    if not df.empty:
        return records(df)
    local = project_paths().current_dir / "web_report_reviews.json"
    if local.exists():
        try:
            rows = json.loads(local.read_text(encoding="utf-8"))
            return [row for row in rows if row.get("report_id") == report_id]
        except Exception:
            return []
    return []

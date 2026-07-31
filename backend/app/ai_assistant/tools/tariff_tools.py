from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from ...config import PROJECT_ROOT
from ...data_access import jsonable, query_dataframe


DATA_DIR = PROJECT_ROOT / "electricity_tariff_output" / "02_processed_data"
POLICY_DIR = PROJECT_ROOT / "electricity_tariff_output" / "04_knowledge_base_tariff_policy"
COMMON_PROVINCES = [
    "北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省",
    "上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省", "山东省", "河南省",
    "湖北省", "湖南省", "广东省", "广西壮族自治区", "海南省", "重庆市", "四川省",
    "贵州省", "云南省", "西藏自治区", "陕西省", "甘肃省", "青海省", "宁夏回族自治区", "新疆维吾尔自治区",
]
_TARIFF_TABLE_QUERIES = {
    "pv_tariff_rules": ("pv_tariff_rules.csv", "SELECT * FROM pv_tariff_rules LIMIT 5000"),
    "pv_station_tariff_check": ("pv_station_tariff_check.csv", "SELECT * FROM pv_station_tariff_check LIMIT 5000"),
    "pv_policy_files": ("pv_policy_files.csv", "SELECT * FROM pv_policy_files LIMIT 5000"),
    "market_power_price_rules": ("market_power_price_rules.csv", "SELECT * FROM market_power_price_rules LIMIT 5000"),
    "southern_grid_tax_rules": ("southern_grid_tax_rules.csv", "SELECT * FROM southern_grid_tax_rules LIMIT 5000"),
}


def _read_table(table_name: str, file_name: str) -> tuple[pd.DataFrame, str]:
    registered = _TARIFF_TABLE_QUERIES.get(table_name)
    if registered is None or registered[0] != file_name:
        return pd.DataFrame(), "unregistered_dataset"
    db_df = query_dataframe(registered[1])
    if not db_df.empty:
        return db_df, f"database:{table_name}"
    path = DATA_DIR / file_name
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, encoding="utf-8-sig"), str(path)
    return pd.DataFrame(), str(path)


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        text = str(value).replace(",", "").strip()
        return float(text) if text else None
    except Exception:
        return None


def _date(value: Any) -> date | None:
    dt = pd.to_datetime(value, errors="coerce")
    return dt.date() if pd.notna(dt) else None


def _parse_business_month(question: str) -> str:
    match = re.search(r"(20\d{2})\D{0,3}([01]?\d)", question)
    if match:
        return f"{match.group(1)}{int(match.group(2)):02d}"
    return ""


def _parse_grid_date(question: str) -> str:
    match = re.search(r"(20\d{2})\D{0,2}([01]?\d)\D{0,2}([0-3]?\d)", question)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(20\d{2})\D{0,2}([01]?\d)\s*(?:月|/|-)", question)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-15"
    match = re.search(r"(20\d{2})\s*年?", question)
    if match:
        return f"{match.group(1)}-06-30"
    return ""


def _tokens(text: str) -> list[str]:
    terms = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", text or "")
    expanded: list[str] = []
    for term in terms:
        expanded.append(term)
        if re.fullmatch(r"[\u4e00-\u9fa5]{4,}", term):
            expanded.extend(term[idx : idx + 2] for idx in range(0, len(term) - 1))
    return list(dict.fromkeys(expanded))


def _candidate_regions(question: str) -> tuple[str, str, str]:
    province = ""
    for value in COMMON_PROVINCES:
        short = value.rstrip("省市自治区壮族回族维吾尔")
        if value in question or (len(short) >= 2 and short in question):
            province = value
            break
    tariff_df, _ = _read_table("pv_tariff_rules", "pv_tariff_rules.csv")
    station_df, _ = _read_table("pv_station_tariff_check", "pv_station_tariff_check.csv")
    city = ""
    for source_df in [tariff_df, station_df]:
        if source_df.empty:
            continue
        for value in source_df.get("province", pd.Series(dtype=object)).dropna().astype(str).unique():
            short = value.rstrip("省市自治区壮族回族维吾尔")
            if value and (value in question or (len(short) >= 2 and short in question)):
                province = value
                break
        for value in source_df.get("city", pd.Series(dtype=object)).dropna().astype(str).unique():
            short = value.rstrip("市区县")
            if value and (value in question or (len(short) >= 2 and short in question)):
                city = value
                break
        if province and city:
            break
    district = ""
    tax_df, _ = _read_table("southern_grid_tax_rules", "southern_grid_tax_rules.csv")
    if not tax_df.empty:
        for value in tax_df.get("district", pd.Series(dtype=object)).dropna().astype(str).unique():
            short = value.rstrip("市区县")
            if value and (value in question or (len(short) >= 2 and short in question)):
                district = value
                break
    return province, city, district


def query_pv_tariff(province: str = "", city: str = "", grid_date: str = "", question: str = "", **_: Any) -> dict[str, Any]:
    df, source = _read_table("pv_tariff_rules", "pv_tariff_rules.csv")
    if df.empty:
        return {"tool": "query_pv_tariff", "available": False, "message": "未找到光伏电价规则数据。"}
    inferred_province, inferred_city, _ = _candidate_regions(question)
    province = province or inferred_province
    city = city or inferred_city
    grid_date = grid_date or _parse_grid_date(question)
    target_date = _date(grid_date)

    work = df.copy()
    if province and "province" in work.columns:
        work = work[work["province"].astype(str).str.contains(province.replace("省", ""), na=False)]
    if city and "city" in work.columns:
        matched_city = work[work["city"].astype(str).str.contains(city.replace("市", ""), na=False)]
        if not matched_city.empty:
            work = matched_city
    if target_date and {"start_date", "end_date"}.issubset(work.columns):
        starts = pd.to_datetime(work["start_date"], errors="coerce").dt.date
        ends = pd.to_datetime(work["end_date"], errors="coerce").dt.date
        matched_date = work[(starts.isna() | (starts <= target_date)) & (ends.isna() | (ends >= target_date))]
        if not matched_date.empty:
            work = matched_date
    if work.empty:
        return {"tool": "query_pv_tariff", "available": False, "message": "未匹配到对应地区和并网日期的电价规则。", "source": source}

    row = work.iloc[0].to_dict()
    result = {
        "tool": "query_pv_tariff",
        "available": True,
        "province": row.get("province"),
        "city": row.get("city"),
        "grid_date": str(target_date or grid_date or ""),
        "start_date": str(_date(row.get("start_date")) or ""),
        "end_date": str(_date(row.get("end_date")) or ""),
        "on_grid_price": _float(row.get("on_grid_price")),
        "subsidy_price": _float(row.get("subsidy_price")),
        "subsidy_years": _float(row.get("subsidy_years")),
        "total_price": _float(row.get("total_price")),
        "remark": row.get("remark"),
        "source": source,
        "evidence": [{"source": source, "fields": ["province", "city", "start_date", "end_date", "on_grid_price", "subsidy_price", "total_price"]}],
    }
    return jsonable(result)


def check_station_tariff(station_id: str = "", question: str = "", **_: Any) -> dict[str, Any]:
    df, source = _read_table("pv_station_tariff_check", "pv_station_tariff_check.csv")
    if df.empty:
        return {"tool": "check_station_tariff", "available": False, "message": "未找到电站电价核对数据。"}
    if not station_id:
        match = re.search(r"\d{8,}", question)
        station_id = match.group(0) if match else ""
    work = df.copy()
    if station_id and "station_id" in work.columns:
        work = work[work["station_id"].astype(str).str.contains(station_id, na=False)]
    if work.empty:
        return {"tool": "check_station_tariff", "available": False, "message": "未匹配到该电站的核对记录。", "source": source}
    row = work.iloc[0].to_dict()
    return jsonable(
        {
            "tool": "check_station_tariff",
            "available": True,
            "station_id": _text(row.get("station_id")),
            "province": row.get("province"),
            "city": row.get("city"),
            "district": row.get("district") or row.get("区"),
            "grid_date": str(_date(row.get("grid_date") or row.get("grid_connect_date")) or ""),
            "system_price": _float(row.get("system_price") or row.get("system_power_price")),
            "grid_price": _float(row.get("grid_price") or row.get("power_bureau_price")),
            "national_subsidy": _float(row.get("national_subsidy") or row.get("供电局国补")),
            "provincial_subsidy": _float(row.get("provincial_subsidy") or row.get("供电局省补")),
            "difference_flag": row.get("difference_flag") or row.get("是否已纠正（系统或国电局达成一致）"),
            "remark": row.get("remark") or row.get("explanation") or row.get("difference"),
            "source": source,
            "evidence": [{"source": source, "station_id": _text(row.get("station_id"))}],
        }
    )


def search_tariff_policy(keyword: str = "", question: str = "", top_k: int = 5, **_: Any) -> dict[str, Any]:
    df, source = _read_table("pv_policy_files", "pv_policy_files.csv")
    query = (keyword or question or "").strip()
    results: list[dict[str, Any]] = []
    if not df.empty:
        for _, row in df.iterrows():
            raw = row.to_dict()
            haystack = " ".join(_text(raw.get(col)) for col in ["title", "doc_title", "doc_number", "summary", "related_clauses"])
            score = sum(1 for token in _tokens(query) if token in haystack)
            if score > 0 or not query:
                results.append(
                    {
                        "title": raw.get("title") or raw.get("doc_title"),
                        "doc_number": raw.get("doc_number"),
                        "publish_date": str(_date(raw.get("publish_date")) or raw.get("publish_date") or ""),
                        "summary": raw.get("summary") or raw.get("related_clauses"),
                        "score": score,
                        "source": source,
                    }
                )
    if POLICY_DIR.exists():
        for path in sorted(POLICY_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            score = sum(1 for token in _tokens(query) if token in text)
            if score > 0:
                results.append({"title": path.stem, "summary": text[:320], "score": score, "source": str(path)})
    results.sort(key=lambda item: item.get("score", 0), reverse=True)
    return jsonable(
        {
            "tool": "search_tariff_policy",
            "available": bool(results),
            "keyword": query,
            "items": results[:top_k],
            "evidence": [{"source": item.get("source"), "title": item.get("title")} for item in results[:top_k]],
        }
    )


def query_market_power_price(business_month: str = "", province: str = "", question: str = "", **_: Any) -> dict[str, Any]:
    df, source = _read_table("market_power_price_rules", "market_power_price_rules.csv")
    if df.empty:
        return {"tool": "query_market_power_price", "available": False, "message": "未找到市电价格规则。"}
    inferred_province, _, _ = _candidate_regions(question)
    business_month = business_month or _parse_business_month(question)
    province = province or inferred_province
    work = df.copy()
    if business_month and "business_month" in work.columns:
        work = work[work["business_month"].astype(str).str.startswith(business_month)]
    if province and "province" in work.columns:
        matched = work[work["province"].astype(str).str.contains(province.replace("省", ""), na=False)]
        if not matched.empty:
            work = matched
    if work.empty:
        return {"tool": "query_market_power_price", "available": False, "message": "未匹配到该月份或地区的市电价格规则。", "source": source}
    row = work.iloc[0].to_dict()
    return jsonable(
        {
            "tool": "query_market_power_price",
            "available": True,
            "business_month": row.get("business_month"),
            "province": row.get("province"),
            "power_price": _float(row.get("power_price") or row.get("market_electricity_price") or row.get("desulfurized_coal_price")),
            "auxiliary_cost": _float(row.get("auxiliary_cost") or row.get("辅助分摊费用")),
            "total_price": _float(row.get("total_price") or row.get("comprehensive_price")),
            "remark": row.get("remark") or row.get("备注") or row.get("grid_period"),
            "source": source,
            "evidence": [{"source": source, "fields": ["business_month", "province", "total_price"]}],
        }
    )


def query_southern_grid_tax_rule(province: str = "", city: str = "", district: str = "", question: str = "", **_: Any) -> dict[str, Any]:
    df, source = _read_table("southern_grid_tax_rules", "southern_grid_tax_rules.csv")
    if df.empty:
        return {"tool": "query_southern_grid_tax_rule", "available": False, "message": "未找到南网税率规则。"}
    inferred_province, inferred_city, inferred_district = _candidate_regions(question)
    province = province or inferred_province
    city = city or inferred_city
    district = district or inferred_district
    work = df.copy()
    for column, value, suffix in [("province", province, "省"), ("city", city, "市"), ("district", district, "区县")]:
        if value and column in work.columns:
            matched = work[work[column].astype(str).str.contains(value.rstrip(suffix), na=False)]
            if not matched.empty:
                work = matched
    if work.empty:
        return {"tool": "query_southern_grid_tax_rule", "available": False, "message": "未匹配到南网税率规则。", "source": source}
    row = work.iloc[0].to_dict()
    return jsonable(
        {
            "tool": "query_southern_grid_tax_rule",
            "available": True,
            "province": row.get("province"),
            "city": row.get("city"),
            "district": row.get("district"),
            "deduction_rate": _float(row.get("deduction_rate") or row.get("（暂不准）税率") or row.get("vat_rate")),
            "payment_formula": row.get("payment_formula") or row.get("回款金额公式"),
            "tax_remark": row.get("tax_remark") or row.get("is_substitute_withholding") or row.get("withholding_entity"),
            "source": source,
            "evidence": [{"source": source, "fields": ["province", "city", "district", "deduction_rate", "payment_formula"]}],
        }
    )

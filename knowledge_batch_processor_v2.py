# -*- coding: utf-8 -*-
"""
版本：v2_download_fix
说明：本版本拆分为单独文件下载，避免压缩包无法下载时无法使用。

knowledge_batch_processor.py

用途：
    批量处理“智能运营分析项目/知识库”中的多格式资料，统一提取为 Markdown，
    并切分为可用于 RAG / AI 助手检索的 chunks.jsonl。

默认输入：
    <项目根目录>\知识库

默认输出：
    <项目根目录>\knowledge_pipeline

支持格式：
    pdf, docx, doc, xlsx, xls, wps, et, html, htm, txt, md
    其中 doc/xls/wps/et 优先调用 LibreOffice 转换为 docx/xlsx 后处理。

运行示例：
    python knowledge_batch_processor.py

    python knowledge_batch_processor.py --input "知识库" --output "knowledge_pipeline"

    python knowledge_batch_processor.py --dry-run

    python knowledge_batch_processor.py --resume

依赖：
    pip install -r requirements.txt

说明：
    1. 本脚本不修改原始文件。
    2. WPS/ET/DOC/XLS 转换依赖 LibreOffice，如果电脑未安装，会记录到 failed_files.csv。
    3. 扫描版 PDF 暂不 OCR，只记录失败，避免误识别。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = str(PROJECT_ROOT / "知识库")
DEFAULT_OUTPUT_DIR = str(PROJECT_ROOT / "knowledge_pipeline")

SUPPORTED_EXTS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".wps", ".et",
    ".html", ".htm", ".txt", ".md"
}

TEXT_EXTS = {".txt", ".md"}
HTML_EXTS = {".html", ".htm"}
WORD_EXTS = {".docx"}
EXCEL_EXTS = {".xlsx"}
CONVERT_WORD_EXTS = {".doc", ".wps"}
CONVERT_EXCEL_EXTS = {".xls", ".et"}

CATEGORY_RULES: Dict[str, List[str]] = {
    "电力市场规则": [
        "市场规则", "运营规则", "基本规则", "交易规则", "实施细则",
        "市场监管", "市场管理", "电力市场"
    ],
    "电力现货交易": [
        "现货", "日前市场", "实时市场", "出清", "节点电价",
        "边际电价", "LMP", "分时电价", "结算试运行"
    ],
    "绿证交易": [
        "绿证", "绿色电力证书", "绿色电力交易", "可再生能源电力证书"
    ],
    "新能源政策": [
        "新能源", "风电", "光伏", "可再生能源", "消纳", "并网",
        "新能源项目", "分布式光伏"
    ],
    "电价政策": [
        "电价", "峰谷", "尖峰", "分时", "输配电价", "代理购电",
        "上网电价", "目录电价"
    ],
    "电网代理购电": [
        "代理购电", "电网企业代理", "购电价格", "代理用户"
    ],
    "项目申报与建设": [
        "项目申报", "项目建设", "建设方案", "开发建设", "竞配",
        "申报表", "备案", "实施方案"
    ],
    "交易策略": [
        "交易策略", "套利", "峰谷价差", "储能", "充放电",
        "中长期交易", "合同电量", "偏差考核"
    ],
    "市场机制解释": [
        "PJM", "DOM", "LMP", "容量市场", "辅助服务", "阻塞",
        "拥塞", "边际损耗", "价格形成机制"
    ],
}

KEYWORD_POOL = [
    "电力市场", "现货市场", "日前市场", "实时市场", "中长期交易", "辅助服务",
    "节点电价", "LMP", "PJM", "DOM", "绿证", "新能源", "风电", "光伏",
    "储能", "峰谷价差", "尖峰电价", "分时电价", "代理购电", "输配电价",
    "负荷预测", "天气", "温度", "价格预测", "模型误差", "MAE", "RMSE",
    "出清", "结算", "交易规则", "实施细则", "市场监管", "容量市场",
    "拥塞", "边际损耗", "偏差考核", "申报", "建设方案", "交易策略"
]


@dataclass
class ProcessResult:
    source_file: str
    source_path: str
    file_type: str
    status: str
    category: str = "其他"
    title: str = ""
    markdown_path: str = ""
    chunks_count: int = 0
    message: str = ""


@dataclass
class FailedFile:
    source_file: str
    source_path: str
    file_type: str
    failed_reason: str
    suggested_action: str


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore"))


def ensure_dirs(output_dir: Path) -> Dict[str, Path]:
    dirs = {
        "base": output_dir,
        "converted": output_dir / "converted",
        "converted_docx": output_dir / "converted" / "docx",
        "converted_xlsx": output_dir / "converted" / "xlsx",
        "markdown": output_dir / "markdown",
        "chunks": output_dir / "chunks",
        "output": output_dir / "output",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        name = "untitled"
    return name[:max_len]


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def load_processed_sources(chunks_jsonl: Path) -> set:
    processed = set()
    if not chunks_jsonl.exists():
        return processed
    with chunks_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                if item.get("source_path"):
                    processed.add(item["source_path"])
            except Exception:
                continue
    return processed


def find_soffice() -> Optional[str]:
    """
    查找 LibreOffice 的 soffice 可执行文件。
    """
    candidates = [
        shutil.which("soffice"),
        shutil.which("soffice.exe"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def convert_with_libreoffice(src: Path, out_dir: Path, target_ext: str, timeout: int = 120) -> Optional[Path]:
    """
    使用 LibreOffice headless 转换文件。
    target_ext 示例：docx、xlsx、pdf
    """
    soffice = find_soffice()
    if not soffice:
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        target_ext,
        "--outdir",
        str(out_dir),
        str(src),
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            shell=False,
        )
        expected = out_dir / (src.stem + "." + target_ext)
        if expected.exists() and expected.stat().st_size > 0:
            return expected

        # 部分文件名可能被 LibreOffice 清洗，兜底查找最近的同后缀文件
        candidates = sorted(out_dir.glob(f"*.{target_ext}"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            latest = candidates[0]
            if latest.stat().st_mtime >= src.stat().st_mtime - 10:
                return latest

        return None
    except Exception:
        return None


def read_text_by_encoding(path: Path) -> str:
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312", "big5", "latin1"]
    raw = path.read_bytes()
    for enc in encodings:
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", errors="ignore")


def extract_pdf_text(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise RuntimeError("缺少 PyMuPDF，请先 pip install pymupdf") from e

    texts = []
    doc = fitz.open(str(path))
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        if text.strip():
            texts.append(f"\n\n## 第 {i} 页\n\n{text}")
    doc.close()
    return "\n".join(texts)


def extract_docx_text(path: Path) -> str:
    try:
        import docx
    except Exception as e:
        raise RuntimeError("缺少 python-docx，请先 pip install python-docx") from e

    document = docx.Document(str(path))
    parts: List[str] = []

    for p in document.paragraphs:
        t = p.text.strip()
        if t:
            parts.append(t)

    # 提取表格
    for table_idx, table in enumerate(document.tables, start=1):
        rows = []
        for row in table.rows:
            vals = [cell.text.replace("\n", " ").strip() for cell in row.cells]
            if any(vals):
                rows.append(vals)
        if rows:
            parts.append(f"\n\n### 表格 {table_idx}\n")
            parts.append(table_to_markdown(rows))

    return "\n\n".join(parts)


def table_to_markdown(rows: List[List[str]], max_cols: int = 20, max_cell_len: int = 120) -> str:
    if not rows:
        return ""
    max_width = max(len(r) for r in rows)
    max_width = min(max_width, max_cols)

    normalized = []
    for r in rows:
        rr = []
        for c in r[:max_width]:
            c = "" if c is None else str(c)
            c = c.replace("|", "｜").replace("\n", " ").strip()
            if len(c) > max_cell_len:
                c = c[:max_cell_len] + "..."
            rr.append(c)
        rr += [""] * (max_width - len(rr))
        normalized.append(rr)

    header = normalized[0]
    lines = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * max_width) + " |")
    for r in normalized[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def extract_xlsx_text(path: Path) -> str:
    try:
        import openpyxl
    except Exception as e:
        raise RuntimeError("缺少 openpyxl，请先 pip install openpyxl") from e

    wb = openpyxl.load_workbook(str(path), data_only=False, read_only=True)
    parts: List[str] = []

    for sheet in wb.worksheets:
        parts.append(f"\n\n## Sheet：{sheet.title}\n")

        rows = []
        max_row = sheet.max_row or 0
        max_col = sheet.max_column or 0

        # 防止超大空表拖慢处理
        for row in sheet.iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True):
            vals = []
            for v in row:
                if v is None:
                    vals.append("")
                else:
                    vals.append(str(v).strip())
            if any(vals):
                rows.append(vals)

        if rows:
            # 很大的 sheet 分段输出，避免单个 markdown 表太长
            batch_size = 80
            for start in range(0, len(rows), batch_size):
                sub = rows[start:start + batch_size]
                parts.append(f"\n### 行 {start + 1} - {start + len(sub)}\n")
                parts.append(table_to_markdown(sub))
        else:
            parts.append("空表或未读取到有效内容。")

    try:
        wb.close()
    except Exception:
        pass

    return "\n\n".join(parts)


def extract_html_text(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup
    except Exception as e:
        raise RuntimeError("缺少 beautifulsoup4，请先 pip install beautifulsoup4") from e

    html = read_text_by_encoding(path)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body = soup.body or soup
    text = body.get_text("\n", strip=True)
    if title:
        return f"{title}\n\n{text}"
    return text


def extract_unknown_text(path: Path) -> str:
    """
    异常后缀文件兜底：
    尝试作为文本或 HTML 读取。
    """
    text = read_text_by_encoding(path)
    if "<html" in text[:1000].lower() or "<!doctype html" in text[:1000].lower():
        # 临时写成 html 字符串解析
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            return soup.get_text("\n", strip=True)
        except Exception:
            return text
    return text


def clean_text(text: str) -> str:
    if not text:
        return ""

    # 统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 去除常见不可见字符，但保留中文、英文、数字、符号
    text = text.replace("\ufeff", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    # 修复过多空格和制表
    text = re.sub(r"[ \t]+", " ", text)

    # 去除每行首尾空白
    lines = [line.strip() for line in text.split("\n")]

    # 去除重复页眉页脚：对很短且重复频繁的行做清理
    line_counter = Counter([l for l in lines if 0 < len(l) <= 40])
    cleaned_lines = []
    total_lines = max(len(lines), 1)
    for l in lines:
        # 页码类
        if re.fullmatch(r"[-—]*\s*\d+\s*[-—]*", l):
            continue
        # 重复频率过高的短行，可能是页眉页脚
        if l and len(l) <= 40 and line_counter[l] >= 5 and line_counter[l] / total_lines > 0.03:
            continue
        cleaned_lines.append(l)

    text = "\n".join(cleaned_lines)

    # 压缩多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 清理明显乱码片段，不激进删除中文政策文本
    text = re.sub(r"[□■�]{2,}", "", text)

    return text.strip()


def guess_title(file_path: Path, text: str) -> str:
    # 优先文件名去后缀
    name = file_path.stem
    name = re.sub(r"\.pdf$|\.docx$|\.xlsx$|\.wps$|\.et$", "", name, flags=re.I)
    name = re.sub(r"[-_]?downloadfile.*", "", name, flags=re.I)
    name = re.sub(r"W020\d+|P020\d+|\.pdf|\.docx|\.xlsx", "", name, flags=re.I)
    name = sanitize_filename(name, 100)

    # 如果正文第一行像标题，也可补充
    first_lines = [l.strip("# ").strip() for l in text.splitlines() if 5 <= len(l.strip()) <= 80]
    if first_lines:
        first = first_lines[0]
        if any(k in first for k in ["通知", "规则", "细则", "办法", "方案", "意见", "手册"]):
            return sanitize_filename(first, 100)

    return name or "未命名文件"


def classify_document(file_name: str, text: str) -> str:
    sample = (file_name + "\n" + text[:5000]).lower()
    scores = {}
    for cat, kws in CATEGORY_RULES.items():
        score = 0
        for kw in kws:
            if kw.lower() in sample:
                score += 1
        scores[cat] = score
    best_cat, best_score = max(scores.items(), key=lambda x: x[1])
    return best_cat if best_score > 0 else "其他"


def extract_keywords(file_name: str, text: str, max_keywords: int = 8) -> List[str]:
    sample = file_name + "\n" + text[:8000]
    found = []
    for kw in KEYWORD_POOL:
        if kw.lower() in sample.lower():
            found.append(kw)
    # 增加省份/区域关键词
    regions = [
        "河北", "山西", "山东", "浙江", "江苏", "广东", "广西", "云南", "贵州",
        "四川", "重庆", "宁夏", "新疆", "甘肃", "青海", "辽宁", "吉林", "黑龙江",
        "华北", "华东", "华中", "华南", "西北", "东北"
    ]
    for r in regions:
        if r in sample and r not in found:
            found.append(r)
    return found[:max_keywords]


def build_markdown(title: str, source_file: str, file_type: str, category: str, text: str) -> str:
    return (
        f"# {title}\n\n"
        f"来源文件：{source_file}  \n"
        f"文件类型：{file_type}  \n"
        f"处理时间：{now_str()}  \n"
        f"所属类别：{category}  \n\n"
        f"## 正文\n\n"
        f"{text.strip()}\n"
    )


def split_into_paragraphs(text: str) -> List[str]:
    # 保留标题和条款边界
    raw_parts = re.split(r"\n\s*\n", text)
    parts = []
    for p in raw_parts:
        p = p.strip()
        if p:
            parts.append(p)
    return parts


def add_overlap(prev_chunk: str, overlap: int) -> str:
    if not prev_chunk or overlap <= 0:
        return ""
    tail = prev_chunk[-overlap:]
    # 尽量从句号/换行后开始
    pos_candidates = [tail.rfind("。"), tail.rfind("\n"), tail.rfind("；"), tail.rfind(";")]
    pos = max(pos_candidates)
    if pos > 20:
        return tail[pos + 1:].strip()
    return tail.strip()


def split_chunks(text: str, chunk_size: int = 1000, chunk_overlap: int = 180, min_chunk_size: int = 300) -> List[str]:
    text = clean_text(text)
    if not text:
        return []

    paragraphs = split_into_paragraphs(text)
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for p in paragraphs:
        # 单段过长时按句子切
        if len(p) > chunk_size * 1.5:
            sentences = re.split(r"(?<=[。！？；;])", p)
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                if current_len + len(s) + 2 <= chunk_size:
                    current.append(s)
                    current_len += len(s) + 2
                else:
                    if current:
                        chunks.append("\n\n".join(current).strip())
                    overlap_text = add_overlap(chunks[-1], chunk_overlap) if chunks else ""
                    current = [overlap_text, s] if overlap_text else [s]
                    current_len = sum(len(x) + 2 for x in current)
            continue

        if current_len + len(p) + 2 <= chunk_size:
            current.append(p)
            current_len += len(p) + 2
        else:
            if current:
                chunks.append("\n\n".join(current).strip())
            overlap_text = add_overlap(chunks[-1], chunk_overlap) if chunks else ""
            current = [overlap_text, p] if overlap_text else [p]
            current_len = sum(len(x) + 2 for x in current)

    if current:
        chunks.append("\n\n".join(current).strip())

    # 合并太短 chunk
    merged: List[str] = []
    for ch in chunks:
        if not merged:
            merged.append(ch)
        elif len(ch) < min_chunk_size:
            if len(merged[-1]) + len(ch) <= chunk_size + chunk_overlap:
                merged[-1] = merged[-1] + "\n\n" + ch
            else:
                merged.append(ch)
        else:
            merged.append(ch)

    # 最终清理
    return [c.strip() for c in merged if len(c.strip()) >= 80]


def detect_file_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext:
        return ext.lstrip(".")
    return "unknown"


def should_skip_file(path: Path) -> bool:
    name = path.name
    if name.startswith("~$"):
        return True
    if path.is_dir():
        return True
    # 跳过临时下载文件
    if name.lower().endswith((".tmp", ".crdownload", ".part")):
        return True
    return False


def scan_files(input_dir: Path) -> List[Path]:
    files = []
    for p in input_dir.rglob("*"):
        if p.is_file() and not should_skip_file(p):
            files.append(p)
    return sorted(files, key=lambda x: str(x).lower())


def extract_text_from_file(path: Path, dirs: Dict[str, Path]) -> Tuple[str, str, Optional[Path], str]:
    """
    返回：(text, normalized_type, converted_path, status_message)
    """
    ext = path.suffix.lower()

    if ext == ".pdf":
        text = extract_pdf_text(path)
        return text, "pdf", None, "PDF文本提取成功"

    if ext in WORD_EXTS:
        text = extract_docx_text(path)
        return text, "docx", None, "DOCX文本提取成功"

    if ext in EXCEL_EXTS:
        text = extract_xlsx_text(path)
        return text, "xlsx", None, "XLSX表格提取成功"

    if ext in HTML_EXTS:
        text = extract_html_text(path)
        return text, ext.lstrip("."), None, "HTML正文提取成功"

    if ext in TEXT_EXTS:
        text = read_text_by_encoding(path)
        return text, ext.lstrip("."), None, "文本文件读取成功"

    if ext in CONVERT_WORD_EXTS:
        converted = convert_with_libreoffice(path, dirs["converted_docx"], "docx")
        if converted and converted.exists():
            text = extract_docx_text(converted)
            return text, "docx", converted, f"{ext} 已转换为 DOCX 后提取成功"
        if ext == ".wps":
            raise RuntimeError("WPS文字文档需手动另存为DOCX，或安装LibreOffice后重试")
        raise RuntimeError("DOC文件自动转换DOCX失败，请安装LibreOffice或手动另存为DOCX")

    if ext in CONVERT_EXCEL_EXTS:
        converted = convert_with_libreoffice(path, dirs["converted_xlsx"], "xlsx")
        if converted and converted.exists():
            text = extract_xlsx_text(converted)
            return text, "xlsx", converted, f"{ext} 已转换为 XLSX 后提取成功"
        if ext == ".et":
            raise RuntimeError("WPS表格需手动另存为XLSX，或安装LibreOffice后重试")
        raise RuntimeError("XLS文件自动转换XLSX失败，请安装LibreOffice或手动另存为XLSX")

    # 异常后缀兜底
    text = extract_unknown_text(path)
    return text, detect_file_type(path), None, "异常后缀文件按文本兜底读取"


def suggested_action_for_error(ext: str, reason: str) -> str:
    ext = ext.lower()
    if "扫描版PDF" in reason or "文本不可提取" in reason:
        return "使用OCR工具识别后另存为可复制文本PDF或TXT"
    if ext == ".wps":
        return "用WPS打开后另存为DOCX，再重新运行脚本"
    if ext == ".et":
        return "用WPS打开后另存为XLSX，再重新运行脚本"
    if ext == ".doc":
        return "安装LibreOffice，或手动另存为DOCX"
    if ext == ".xls":
        return "安装LibreOffice，或手动另存为XLSX"
    if "LibreOffice" in reason:
        return "安装LibreOffice并确保soffice可用，或手动转换为标准格式"
    return "人工检查文件是否损坏、加密、空文件或下载不完整"


def append_jsonl(path: Path, items: Iterable[dict]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def validate_chunks(chunks_jsonl: Path) -> Tuple[bool, List[str]]:
    errors = []
    if not chunks_jsonl.exists():
        return False, ["chunks.jsonl 不存在"]

    ids = set()
    line_count = 0
    with chunks_jsonl.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line_count += 1
            try:
                item = json.loads(line)
            except Exception as e:
                errors.append(f"第 {i} 行 JSON 解析失败：{e}")
                continue

            cid = item.get("chunk_id")
            if not cid:
                errors.append(f"第 {i} 行缺少 chunk_id")
            elif cid in ids:
                errors.append(f"第 {i} 行 chunk_id 重复：{cid}")
            else:
                ids.add(cid)

            if not item.get("text", "").strip():
                errors.append(f"第 {i} 行 text 为空")
            if not item.get("source_file"):
                errors.append(f"第 {i} 行 source_file 为空")
            if not item.get("category"):
                errors.append(f"第 {i} 行 category 为空")

            text_len = len(item.get("text", ""))
            if text_len < 50:
                errors.append(f"第 {i} 行 chunk 过短：{text_len}")
            if text_len > 2500:
                errors.append(f"第 {i} 行 chunk 过长：{text_len}")

    if line_count == 0:
        errors.append("chunks.jsonl 为空")

    return len(errors) == 0, errors


def generate_report(
    output_path: Path,
    input_dir: Path,
    output_dir: Path,
    results: List[ProcessResult],
    failed: List[FailedFile],
    chunks_total: int,
    format_counter: Counter,
    category_counter: Counter,
    validation_ok: bool,
    validation_errors: List[str],
) -> None:
    success_count = sum(1 for r in results if r.status in {"成功", "转换成功"})
    failed_count = len(failed)

    avg_chunks = chunks_total / success_count if success_count else 0

    lines = []
    lines.append("# 知识库批量处理报告\n")
    lines.append(f"处理时间：{now_str()}\n")
    lines.append(f"输入目录：`{input_dir}`\n")
    lines.append(f"输出目录：`{output_dir}`\n")

    lines.append("## 1. 总体统计\n")
    lines.append(f"- 总文件数量：{len(results) + failed_count}")
    lines.append(f"- 成功处理文件数量：{success_count}")
    lines.append(f"- 失败文件数量：{failed_count}")
    lines.append(f"- 总 chunk 数：{chunks_total}")
    lines.append(f"- 平均每个成功文件 chunk 数：{avg_chunks:.2f}\n")

    lines.append("## 2. 各文件格式数量\n")
    for k, v in format_counter.most_common():
        lines.append(f"- {k}：{v}")
    lines.append("")

    lines.append("## 3. 各类别文件数量\n")
    for k, v in category_counter.most_common():
        lines.append(f"- {k}：{v}")
    lines.append("")

    lines.append("## 4. 需要人工处理的文件\n")
    if failed:
        for f in failed:
            lines.append(f"- `{f.source_file}`：{f.failed_reason}；建议：{f.suggested_action}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.append("## 5. Chunk 校验结果\n")
    lines.append(f"- 校验是否通过：{'是' if validation_ok else '否'}")
    if validation_errors:
        lines.append("- 校验问题：")
        for e in validation_errors[:50]:
            lines.append(f"  - {e}")
        if len(validation_errors) > 50:
            lines.append(f"  - 其余 {len(validation_errors) - 50} 条省略")
    lines.append("")

    lines.append("## 6. 下一步建议\n")
    lines.append("1. 优先查看 `failed_files.csv`，把 WPS/ET/DOC/XLS 手动另存为 DOCX/XLSX 后重新运行脚本。")
    lines.append("2. 抽查 `markdown/` 下的 Markdown 文件，确认政策条款、表格、标题是否保留完整。")
    lines.append("3. 抽查 `output/chunks.jsonl`，确认 chunk 文本长度和语义边界是否合理。")
    lines.append("4. 确认 chunk 质量后，再接入 BGE / bge-small-zh / bge-large-zh embedding。")
    lines.append("5. 向量库可以使用 FAISS 或 Chroma，建议先用 FAISS 做本地轻量版。")
    lines.append("6. 现阶段不建议直接让大模型改写全部政策原文，先保持原文可追溯，再额外构造“规则解读”和“问答案例”知识。")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def process_files(args: argparse.Namespace) -> None:
    input_dir = Path(args.input).expanduser()
    output_dir = Path(args.output).expanduser()

    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在：{input_dir}")

    dirs = ensure_dirs(output_dir)
    chunks_jsonl = dirs["output"] / "chunks.jsonl"
    failed_csv = dirs["output"] / "failed_files.csv"
    log_txt = dirs["output"] / "processing_log.txt"
    report_md = dirs["output"] / "processing_report.md"

    if not args.resume:
        # 非 resume 模式下重新生成输出
        for p in [chunks_jsonl, failed_csv, log_txt, report_md]:
            if p.exists():
                p.unlink()

    files = scan_files(input_dir)
    if args.dry_run:
        safe_print(f"扫描到文件数量：{len(files)}")
        counter = Counter([p.suffix.lower() or "无后缀" for p in files])
        for k, v in counter.most_common():
            safe_print(f"{k}: {v}")
        return

    processed_sources = load_processed_sources(chunks_jsonl) if args.resume else set()

    results: List[ProcessResult] = []
    failed: List[FailedFile] = []
    format_counter: Counter = Counter()
    category_counter: Counter = Counter()
    chunks_total = 0
    chunk_global_index = 1
    raw_hash_seen = set()
    text_hash_seen = set()

    # 如果 resume，需要从已有 jsonl 推断下一个 chunk id
    if args.resume and chunks_jsonl.exists():
        with chunks_jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                    cid = item.get("chunk_id", "")
                    m = re.search(r"knowledge_(\d+)", cid)
                    if m:
                        chunk_global_index = max(chunk_global_index, int(m.group(1)) + 1)
                    chunks_total += 1
                except Exception:
                    pass

    with log_txt.open("a", encoding="utf-8") as log:
        log.write(f"\n\n===== 开始处理：{now_str()} =====\n")
        log.write(f"输入目录：{input_dir}\n")
        log.write(f"输出目录：{output_dir}\n")
        log.write(f"扫描文件数：{len(files)}\n\n")

        for idx, path in enumerate(files, start=1):
            source_path_str = str(path)
            ext = path.suffix.lower() or "无后缀"
            format_counter[ext] += 1

            if args.resume and source_path_str in processed_sources:
                msg = f"[{idx}/{len(files)}] 跳过已处理：{path.name}"
                safe_print(msg)
                log.write(msg + "\n")
                continue

            safe_print(f"[{idx}/{len(files)}] 处理：{path.name}")
            log.write(f"[{idx}/{len(files)}] 处理：{source_path_str}\n")

            try:
                # 文件 hash 去重
                try:
                    raw_hash = file_sha256(path)
                    if raw_hash in raw_hash_seen:
                        msg = "重复文件，按文件hash跳过"
                        log.write(f"  跳过：{msg}\n")
                        results.append(ProcessResult(
                            source_file=path.name,
                            source_path=source_path_str,
                            file_type=detect_file_type(path),
                            status="跳过",
                            message=msg,
                        ))
                        continue
                    raw_hash_seen.add(raw_hash)
                except Exception:
                    pass

                text, normalized_type, converted_path, status_msg = extract_text_from_file(path, dirs)
                text = clean_text(text)

                # 扫描版/空文档判断
                if not text or len(text) < args.min_text_length:
                    reason = "扫描版PDF或文本不可提取，需要OCR" if ext == ".pdf" else "提取文本为空或过短"
                    failed.append(FailedFile(
                        source_file=path.name,
                        source_path=source_path_str,
                        file_type=detect_file_type(path),
                        failed_reason=reason,
                        suggested_action=suggested_action_for_error(ext, reason),
                    ))
                    log.write(f"  失败：{reason}\n")
                    continue

                # 文本 hash 去重
                t_hash = text_sha256(text[:200000])
                if t_hash in text_hash_seen:
                    msg = "重复内容，按文本hash跳过"
                    log.write(f"  跳过：{msg}\n")
                    results.append(ProcessResult(
                        source_file=path.name,
                        source_path=source_path_str,
                        file_type=normalized_type,
                        status="跳过",
                        message=msg,
                    ))
                    continue
                text_hash_seen.add(t_hash)

                title = guess_title(path, text)
                category = classify_document(path.name, text)
                keywords = extract_keywords(path.name, text)
                category_counter[category] += 1

                md = build_markdown(title, path.name, normalized_type, category, text)
                md_name = sanitize_filename(path.stem) + ".md"
                md_path = dirs["markdown"] / md_name
                # 防止同名覆盖
                if md_path.exists():
                    md_path = dirs["markdown"] / f"{sanitize_filename(path.stem)}_{hashlib.md5(source_path_str.encode('utf-8')).hexdigest()[:8]}.md"
                md_path.write_text(md, encoding="utf-8")

                chunks = split_chunks(
                    text,
                    chunk_size=args.chunk_size,
                    chunk_overlap=args.chunk_overlap,
                    min_chunk_size=args.min_chunk_size,
                )

                if not chunks:
                    reason = "文本存在但未能切分出有效chunk"
                    failed.append(FailedFile(
                        source_file=path.name,
                        source_path=source_path_str,
                        file_type=normalized_type,
                        failed_reason=reason,
                        suggested_action="人工检查文本内容是否为乱码、目录、空表或图片扫描"
                    ))
                    log.write(f"  失败：{reason}\n")
                    continue

                jsonl_items = []
                chunk_total_for_file = len(chunks)
                for chunk_index, chunk_text in enumerate(chunks, start=1):
                    chunk_id = f"knowledge_{chunk_global_index:06d}"
                    chunk_global_index += 1
                    chunks_total += 1

                    item = {
                        "chunk_id": chunk_id,
                        "source_file": path.name,
                        "source_path": source_path_str,
                        "converted_path": str(converted_path) if converted_path else "",
                        "file_type": normalized_type,
                        "category": category,
                        "title": title,
                        "chunk_index": chunk_index,
                        "chunk_total": chunk_total_for_file,
                        "text": chunk_text,
                        "keywords": keywords,
                        "created_at": now_str(),
                    }
                    jsonl_items.append(item)

                    # 可选：单独 chunk 文件，便于抽查
                    if args.write_chunk_files:
                        chunk_file = dirs["chunks"] / f"{chunk_id}_{sanitize_filename(path.stem, 60)}.md"
                        chunk_file.write_text(
                            f"# {title} - chunk {chunk_index}/{chunk_total_for_file}\n\n"
                            f"来源文件：{path.name}\n\n"
                            f"类别：{category}\n\n"
                            f"关键词：{', '.join(keywords)}\n\n"
                            f"## 内容\n\n{chunk_text}\n",
                            encoding="utf-8"
                        )

                append_jsonl(chunks_jsonl, jsonl_items)

                status = "转换成功" if converted_path else "成功"
                results.append(ProcessResult(
                    source_file=path.name,
                    source_path=source_path_str,
                    file_type=normalized_type,
                    status=status,
                    category=category,
                    title=title,
                    markdown_path=str(md_path),
                    chunks_count=chunk_total_for_file,
                    message=status_msg,
                ))

                log.write(f"  成功：{status_msg}；类别：{category}；chunk数：{chunk_total_for_file}\n")

            except Exception as e:
                reason = str(e).strip() or "未知错误"
                failed.append(FailedFile(
                    source_file=path.name,
                    source_path=source_path_str,
                    file_type=detect_file_type(path),
                    failed_reason=reason,
                    suggested_action=suggested_action_for_error(ext, reason),
                ))
                log.write(f"  失败：{reason}\n")
                if args.debug:
                    log.write(traceback.format_exc() + "\n")

    # 输出失败清单
    write_csv(
        failed_csv,
        [f.__dict__ for f in failed],
        ["source_file", "source_path", "file_type", "failed_reason", "suggested_action"]
    )

    # 输出成功处理清单
    success_csv = dirs["output"] / "processed_files.csv"
    write_csv(
        success_csv,
        [r.__dict__ for r in results],
        ["source_file", "source_path", "file_type", "status", "category", "title", "markdown_path", "chunks_count", "message"]
    )

    validation_ok, validation_errors = validate_chunks(chunks_jsonl)

    generate_report(
        output_path=report_md,
        input_dir=input_dir,
        output_dir=output_dir,
        results=results,
        failed=failed,
        chunks_total=chunks_total,
        format_counter=format_counter,
        category_counter=category_counter,
        validation_ok=validation_ok,
        validation_errors=validation_errors,
    )

    safe_print("\n处理完成。")
    safe_print(f"输出目录：{output_dir}")
    safe_print(f"chunks.jsonl：{chunks_jsonl}")
    safe_print(f"Markdown目录：{dirs['markdown']}")
    safe_print(f"失败清单：{failed_csv}")
    safe_print(f"处理报告：{report_md}")
    safe_print(f"总chunk数：{chunks_total}")
    safe_print(f"校验结果：{'通过' if validation_ok else '存在问题，请查看 processing_report.md'}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="智能运营分析项目知识库批量处理工具")
    parser.add_argument("--input", default=DEFAULT_INPUT_DIR, help="原始知识库资料目录")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="输出目录")
    parser.add_argument("--chunk-size", type=int, default=1000, help="chunk目标大小，默认1000字")
    parser.add_argument("--chunk-overlap", type=int, default=180, help="chunk重叠长度，默认180字")
    parser.add_argument("--min-chunk-size", type=int, default=300, help="最小chunk大小，默认300字")
    parser.add_argument("--min-text-length", type=int, default=80, help="文档最小有效文本长度，默认80字")
    parser.add_argument("--dry-run", action="store_true", help="只扫描文件，不处理")
    parser.add_argument("--resume", action="store_true", help="断点续跑，跳过已在chunks.jsonl中的文件")
    parser.add_argument("--write-chunk-files", action="store_true", help="同时输出每个chunk的单独md文件，便于人工抽查")
    parser.add_argument("--debug", action="store_true", help="输出详细错误堆栈到日志")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    process_files(args)


if __name__ == "__main__":
    main()

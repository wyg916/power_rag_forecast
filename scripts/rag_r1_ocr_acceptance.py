from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
GOLD_PATH = ROOT / "tests" / "evaluation" / "rag_r1_ocr_gold_30.json"
GOLD_SCHEMA = "rag-r1-ocr-gold/v1"
CANDIDATE_SCHEMA = "rag-r1-ocr-candidate/v1"
PAGE_ANNOTATION_SCHEMA = "rag-r1-ocr-page-annotation/v1"
MANUAL_REQUIRED = "MANUAL ANNOTATION REQUIRED"
REQUIRED_STRATA = {
    "scanned_pdf",
    "text_pdf",
    "table",
    "complex_table",
    "chart",
    "formula",
    "multi_column",
    "digit_dense",
    "mixed_zh_en",
}
ELEMENT_KINDS = {"text", "formula", "chart", "image"}
ANNOTATION_STATUSES = {"template", "annotation_in_progress", "review_in_progress", "verified"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NUMBER_RE = re.compile(r"(?<!\d)[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?%?(?!\d)")
CER_MAX_NUMERATOR = 5
CER_MAX_DENOMINATOR = 100
TABLE_F1_MIN_NUMERATOR = 9
TABLE_F1_MIN_DENOMINATOR = 10
LOCATOR_IOU_MIN = 0.5
METRIC_CONTRACT = {"normalization": "nfkc-whitespace-v1", "cer_max": 0.05, "table_f1_min": 0.9, "locator_iou_min": 0.5, "locator_complete": 1.0, "hallucinated_digits_max": 0}
MANUAL_POLICY = {"required_page_count": 30, "batch_size": 10, "source_of_truth": "human_transcription_from_rendered_page", "independent_reviewer": True, "candidate_blind_initial_annotation": True, "automatic_candidate_is_gold": False}
AI_ROLE_SCHEMA = "rag-r1-ocr-ai-role-output/v1"
AI_ADJUDICATION_SCHEMA = "rag-r1-ocr-ai-adjudication/v1"
AI_CONSENSUS_SCHEMA = "rag-r1-ocr-ai-consensus/v1"
AI_VERIFICATION_MODE = "multi_agent_independent_consensus"
AI_CONSENSUS_VERIFIED = "AI_CONSENSUS_VERIFIED"
AI_ROLE_ORIGINS = ("codex_ai_ocr_extractor", "codex_ai_independent_visual_reviewer", "codex_ai_consensus_adjudicator")


class OCRAcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceSpec:
    path: str
    sha256: str
    page_count: int


@dataclass(frozen=True)
class PageSelection:
    page_id: str
    batch: int
    source_key: str
    page_number: int
    strata: tuple[str, ...]
    reason: str


SOURCES: dict[str, SourceSpec] = {
    "shandong_scan": SourceSpec("知识库/山东省抽水蓄能项目管理实施细则（征求意见稿）-downfile.jsp_classid=0&filename=8460971e62e54062b368a0974ad7a6c2.pdf.pdf", "adbbcd9b3c7e41f4a11704cd98d073cd04d93680d13d189a1f5bf5697b004a1f", 7),
    "green_certificate_report": SourceSpec("知识库/中国绿色电力证书发展报告（2025）.pdf", "19bfe2955e5a0ff96c8e9ceb56e94ce6329937cc9f04f33ad4b79c1e4a5c2bf7", 49),
    "yunnan_two_low": SourceSpec("知识库/国家能源局云南监管办公室关于开展2026年“两低”专项治理和抵边村寨供....pdf", "34bb8ae0ab3bf6e4f15d103d10ea35d5f3e9ea6a12674ec091f7c3cdd649d2a0", 11),
    "beijing_buyer_guide": SourceSpec("知识库/北京登记结算公司支付渠道-买方指引(202605).pdf", "bce187a40acffade9884085009f7962b9c6503f02f6293647454baf0eeebc737", 2),
    "e_payment_guide": SourceSpec("知识库/电e宝支付渠道-功能使用指引.pdf", "f524588df25162ba6f42a1e599e87b0bf9ffa169c3c663f5a81aefc90f624537", 2),
    "shanghai_application": SourceSpec("知识库/关于做好上海市2026年陆上风电、光伏电站开发建设方案申报工作的通知.pdf.pdf", "2d268788df38691cefcbeab75078721473c6112eb5ab37f515ccefcefdb2b123", 7),
    "hebei_spot_rules": SourceSpec("知识库/河北南部电网电力现货市场实施细则.pdf-W020260122360751867980.pdf.pdf", "c6606e4248f8aeb603cafe927aa4609fe95b44b1da442d96417ed19626c633c9", 64),
    "northwest_mutual_aid": SourceSpec("知识库/国家能源局西北监管局关于印发《西北区域省间电力互济交易实施细则(试行)》的通知.pdf", "30de24213a4916ec462334f448d220df09c279c49cb6a048afcf647555d8df34", 74),
    "non_fossil_guide": SourceSpec("知识库/《非化石能源电力消费核算指南（试行）》.pdf-P020260601561979770878.pdf.pdf", "c3d78a4b091d9e4c805a55e7ff8457c98e17775e719d4e54b9620ba13b5ce2c1", 13),
    "yunxiao_transmission": SourceSpec("知识库/云霄直流输电权市场化交易方案（暂行）.pdf-P020260602591084142337.pdf.pdf", "21cdf3b77a55cdd73426e7147f2a623f8936b4e5fc3dae9ba384e992e5fa14a0", 5),
}


def _sel(page_id: int, batch: int, source: str, page: int, strata: str, reason: str) -> PageSelection:
    return PageSelection(f"ocr-{page_id:03d}", batch, source, page, tuple(strata.split(",")), reason)


DEFAULT_SELECTIONS = (
    _sel(1, 1, "shandong_scan", 1, "scanned_pdf", "无文本层扫描正文"),
    _sel(2, 1, "shandong_scan", 6, "scanned_pdf", "无文本层扫描正文"),
    _sel(3, 1, "green_certificate_report", 16, "text_pdf,chart,digit_dense,mixed_zh_en", "柱状图与数字标注"),
    _sel(4, 1, "green_certificate_report", 45, "text_pdf,table,digit_dense", "标准表格"),
    _sel(5, 1, "yunnan_two_low", 5, "text_pdf,table,complex_table,digit_dense", "横向复杂清单"),
    _sel(6, 1, "beijing_buyer_guide", 1, "text_pdf,multi_column,chart,mixed_zh_en", "三栏步骤与UI截图"),
    _sel(7, 1, "hebei_spot_rules", 31, "text_pdf,formula,digit_dense,mixed_zh_en", "密集数学公式"),
    _sel(8, 1, "northwest_mutual_aid", 73, "text_pdf,chart,digit_dense", "双阶梯曲线图"),
    _sel(9, 1, "non_fossil_guide", 6, "text_pdf,mixed_zh_en", "纯文本中英混排"),
    _sel(10, 1, "yunnan_two_low", 1, "text_pdf,table,digit_dense", "简单宽表"),
    _sel(11, 2, "shandong_scan", 2, "scanned_pdf", "无文本层扫描正文"),
    _sel(12, 2, "shandong_scan", 7, "scanned_pdf", "无文本层扫描正文"),
    _sel(13, 2, "green_certificate_report", 18, "text_pdf,chart,digit_dense,mixed_zh_en", "饼图与百分比"),
    _sel(14, 2, "green_certificate_report", 47, "text_pdf,table,complex_table,digit_dense", "复杂表格"),
    _sel(15, 2, "yunnan_two_low", 6, "text_pdf,table,complex_table,digit_dense", "跨行长文本清单"),
    _sel(16, 2, "e_payment_guide", 1, "text_pdf,chart,mixed_zh_en", "图文UI与中英混排"),
    _sel(17, 2, "hebei_spot_rules", 33, "text_pdf,formula,digit_dense,mixed_zh_en", "密集数学公式"),
    _sel(18, 2, "northwest_mutual_aid", 60, "text_pdf,formula,digit_dense,mixed_zh_en", "公式与英文单位"),
    _sel(19, 2, "yunxiao_transmission", 4, "text_pdf,digit_dense", "数字密集正文"),
    _sel(20, 2, "green_certificate_report", 37, "text_pdf,multi_column,mixed_zh_en", "复杂多栏阅读序"),
    _sel(21, 3, "shandong_scan", 4, "scanned_pdf", "无文本层扫描正文"),
    _sel(22, 3, "green_certificate_report", 27, "text_pdf,chart,digit_dense,mixed_zh_en", "双饼图与百分比"),
    _sel(23, 3, "green_certificate_report", 39, "text_pdf,chart,mixed_zh_en", "UI截图与复杂版式"),
    _sel(24, 3, "green_certificate_report", 40, "text_pdf,chart,mixed_zh_en", "流程图"),
    _sel(25, 3, "green_certificate_report", 48, "text_pdf,table,complex_table,digit_dense", "复杂数字表格"),
    _sel(26, 3, "yunnan_two_low", 9, "text_pdf,table,complex_table,digit_dense", "横向复杂清单"),
    _sel(27, 3, "yunnan_two_low", 10, "text_pdf,table,complex_table,digit_dense", "横向复杂清单"),
    _sel(28, 3, "shanghai_application", 6, "text_pdf,table,complex_table", "空白申报表"),
    _sel(29, 3, "hebei_spot_rules", 36, "text_pdf,formula,digit_dense,mixed_zh_en", "密集数学公式"),
    _sel(30, 3, "northwest_mutual_aid", 65, "text_pdf,formula,digit_dense,mixed_zh_en", "公式与英文单位"),
)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json_bytes(value: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise OCRAcceptanceError(f"duplicate_json_key:{label}:{key}")
            result[key] = item
        return result

    try:
        return json.loads(
            value.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise OCRAcceptanceError(f"invalid_json:{label}") from exc


def _safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise OCRAcceptanceError(f"unsafe_relative_path:{label}")
    return path


def _within(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as exc:
        raise OCRAcceptanceError(f"path_outside_allowed_root:{label}") from exc
    return resolved


def normalize_text(value: str) -> str:
    if not isinstance(value, str):
        raise OCRAcceptanceError("text_not_string")
    value = unicodedata.normalize("NFKC", value).replace("\u00ad", "")
    value = value.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def levenshtein_distance(left: str, right: str) -> int:
    left, right = normalize_text(left), normalize_text(right)
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def _ascii_digits(value: str) -> str:
    chars: list[str] = []
    for char in unicodedata.normalize("NFKC", value):
        if char.isdigit():
            try:
                chars.append(str(unicodedata.digit(char)))
            except (TypeError, ValueError) as exc:
                raise OCRAcceptanceError("unsupported_unicode_digit") from exc
        else:
            chars.append(char)
    return "".join(chars)


def _canonical_number(token: str) -> str:
    percent = token.endswith("%")
    number = token[:-1] if percent else token
    try:
        decimal = Decimal(number.replace(",", ""))
    except InvalidOperation as exc:
        raise OCRAcceptanceError("invalid_number_token") from exc
    if not decimal.is_finite():
        raise OCRAcceptanceError("nonfinite_number_token")
    if decimal == 0:
        decimal = Decimal(0)
    normalized = format(decimal.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized + ("%" if percent else "")


def number_counter(value: str) -> Counter[str]:
    normalized = _ascii_digits(value)
    matches = list(NUMBER_RE.finditer(normalized))
    covered = {index for match in matches for index in range(match.start(), match.end())}
    if any(char.isdigit() and index not in covered for index, char in enumerate(normalized)):
        raise OCRAcceptanceError("unparsed_digit_character")
    return Counter(_canonical_number(match.group(0)) for match in matches)


def _bbox(value: Any, width: float, height: float, label: str) -> tuple[float, float, float, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise OCRAcceptanceError(f"bbox_invalid:{label}")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) for item in value):
        raise OCRAcceptanceError(f"bbox_invalid:{label}")
    box = tuple(float(item) for item in value)
    if box[0] < 0 or box[1] < 0 or box[2] <= box[0] or box[3] <= box[1] or box[2] > width or box[3] > height:
        raise OCRAcceptanceError(f"bbox_out_of_bounds:{label}")
    return box


def _iou(left: Sequence[float], right: Sequence[float]) -> float:
    x0, y0 = max(left[0], right[0]), max(left[1], right[1])
    x1, y1 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if not intersection:
        return 0.0
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    return intersection / (left_area + right_area - intersection)


def _best_matching(
    gold: Sequence[Mapping[str, Any]], candidate: Sequence[Mapping[str, Any]], *, same_kind: bool,
) -> list[tuple[int, int]]:
    adjacency = []
    for gold_item in gold:
        options = []
        for candidate_index, candidate_item in enumerate(candidate):
            if same_kind and gold_item.get("kind") != candidate_item.get("kind"):
                continue
            overlap = _iou(gold_item["_bbox"], candidate_item["_bbox"])
            if overlap >= LOCATOR_IOU_MIN:
                options.append((-int(round(overlap * 1_000_000_000)), candidate_index))
        adjacency.append([index for _, index in sorted(options)])
    right_to_left: dict[int, int] = {}

    def augment(left: int, seen: set[int]) -> bool:
        for right in adjacency[left]:
            if right in seen:
                continue
            seen.add(right)
            if right not in right_to_left or augment(right_to_left[right], seen):
                right_to_left[right] = left
                return True
        return False

    for left in range(len(gold)):
        augment(left, set())
    return sorted((left, right) for right, left in right_to_left.items())


def _exact_keys(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise OCRAcceptanceError(f"schema_keys_invalid:{label}")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise OCRAcceptanceError(f"timestamp_missing:{label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OCRAcceptanceError(f"timestamp_invalid:{label}") from exc
    if parsed.utcoffset() is None:
        raise OCRAcceptanceError(f"timestamp_timezone_missing:{label}")
    return parsed


def _validate_table(table: Any, width: float, height: float, label: str) -> None:
    table = _exact_keys(table, {"table_id", "bbox", "cells"}, label)
    if not isinstance(table["table_id"], str) or not table["table_id"]:
        raise OCRAcceptanceError(f"table_id_invalid:{label}")
    _bbox(table["bbox"], width, height, label)
    if not isinstance(table["cells"], list):
        raise OCRAcceptanceError(f"table_cells_invalid:{label}")
    occupied: set[tuple[int, int]] = set()
    for index, cell in enumerate(table["cells"]):
        cell_label = f"{label}:cell:{index}"
        cell = _exact_keys(cell, {"row", "column", "row_span", "column_span", "text", "bbox"}, cell_label)
        integers = [cell[key] for key in ("row", "column", "row_span", "column_span")]
        if any(isinstance(item, bool) or not isinstance(item, int) for item in integers) or integers[0] < 0 or integers[1] < 0 or integers[2] < 1 or integers[3] < 1:
            raise OCRAcceptanceError(f"table_cell_coordinate_invalid:{cell_label}")
        if not isinstance(cell["text"], str):
            raise OCRAcceptanceError(f"table_cell_text_invalid:{cell_label}")
        _bbox(cell["bbox"], width, height, cell_label)
        covered = {
            (row, column)
            for row in range(cell["row"], cell["row"] + cell["row_span"])
            for column in range(cell["column"], cell["column"] + cell["column_span"])
        }
        if occupied & covered:
            raise OCRAcceptanceError(f"table_cell_overlap:{label}")
        occupied.update(covered)


def validate_gold(gold: Any, *, verify_files: bool = False, root: Path = ROOT) -> list[str]:
    gold = _exact_keys(gold, {"schema_version", "dataset_id", "dataset_status", "metric_contract", "manual_policy", "pages"}, "gold")
    if gold["schema_version"] != GOLD_SCHEMA or gold["dataset_id"] != "rag-r1b-ocr-gold-30" or gold["dataset_status"] not in ANNOTATION_STATUSES:
        raise OCRAcceptanceError("gold_identity_invalid")
    metric_contract = _exact_keys(gold["metric_contract"], set(METRIC_CONTRACT), "metric_contract")
    if metric_contract != METRIC_CONTRACT:
        raise OCRAcceptanceError("metric_contract_invalid")
    policy = _exact_keys(gold["manual_policy"], {"required_page_count", "batch_size", "source_of_truth", "independent_reviewer", "candidate_blind_initial_annotation", "automatic_candidate_is_gold"}, "manual_policy")
    if policy != MANUAL_POLICY:
        raise OCRAcceptanceError("manual_policy_invalid")
    pages = gold["pages"]
    if not isinstance(pages, list) or len(pages) != 30:
        raise OCRAcceptanceError("gold_page_count_not_30")
    ids: set[str] = set()
    source_pages: set[tuple[str, int]] = set()
    strata: set[str] = set()
    batches: Counter[int] = Counter()
    manual_reasons: list[str] = []
    expected_by_id = {item.page_id: item for item in DEFAULT_SELECTIONS}
    for page in pages:
        page = _exact_keys(page, {"page_id", "batch", "strata", "selection_reason", "source", "render", "annotation"}, "page")
        page_id = page["page_id"]
        if not isinstance(page_id, str) or not re.fullmatch(r"ocr-\d{3}", page_id) or page_id in ids:
            raise OCRAcceptanceError("page_id_invalid_or_duplicate")
        ids.add(page_id)
        if isinstance(page["batch"], bool) or page["batch"] not in {1, 2, 3}:
            raise OCRAcceptanceError(f"batch_invalid:{page_id}")
        batches[page["batch"]] += 1
        if not isinstance(page["strata"], list) or not page["strata"] or len(page["strata"]) != len(set(page["strata"])) or not set(page["strata"]) <= REQUIRED_STRATA:
            raise OCRAcceptanceError(f"strata_invalid:{page_id}")
        strata.update(page["strata"])
        source = _exact_keys(page["source"], {"path", "sha256", "page_number", "page_count", "page_width", "page_height"}, f"source:{page_id}")
        _safe_relative(source["path"], f"source:{page_id}")
        if not isinstance(source["sha256"], str) or not SHA256_RE.fullmatch(source["sha256"]):
            raise OCRAcceptanceError(f"source_hash_invalid:{page_id}")
        page_number, page_count = source["page_number"], source["page_count"]
        if any(isinstance(item, bool) or not isinstance(item, int) for item in (page_number, page_count)) or not 1 <= page_number <= page_count:
            raise OCRAcceptanceError(f"source_page_invalid:{page_id}")
        expected = expected_by_id.get(page_id)
        if expected is None or (page["batch"], tuple(page["strata"]), page["selection_reason"], source["path"], source["sha256"], page_number, page_count) != (expected.batch, expected.strata, expected.reason, SOURCES[expected.source_key].path, SOURCES[expected.source_key].sha256, expected.page_number, SOURCES[expected.source_key].page_count):
            raise OCRAcceptanceError(f"fixed_selection_mismatch:{page_id}")
        source_key = (source["sha256"], page_number)
        if source_key in source_pages:
            raise OCRAcceptanceError("source_page_duplicate")
        source_pages.add(source_key)
        width, height = source["page_width"], source["page_height"]
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(float(item)) or item <= 0 for item in (width, height)):
            raise OCRAcceptanceError(f"page_size_invalid:{page_id}")
        render = _exact_keys(page["render"], {"archive", "entry", "sha256", "dpi", "width_px", "height_px", "coordinate_space"}, f"render:{page_id}")
        _safe_relative(render["archive"], f"render_archive:{page_id}")
        _safe_relative(render["entry"], f"render_entry:{page_id}")
        if not isinstance(render["sha256"], str) or not SHA256_RE.fullmatch(render["sha256"]) or render["coordinate_space"] != "pdf_points":
            raise OCRAcceptanceError(f"render_contract_invalid:{page_id}")
        if render["dpi"] != 200 or any(isinstance(render[key], bool) or not isinstance(render[key], int) or render[key] <= 0 for key in ("dpi", "width_px", "height_px")):
            raise OCRAcceptanceError(f"render_dimensions_invalid:{page_id}")
        annotation = _exact_keys(
            page["annotation"],
            {"status", "source_of_truth", "candidate_visible_during_initial_annotation", "annotator_id", "annotated_at", "reviewer_id", "reviewed_at", "checks", "text", "elements", "tables", "verified_digits", "unresolved_issues"},
            f"annotation:{page_id}",
        )
        if annotation["status"] not in ANNOTATION_STATUSES or annotation["source_of_truth"] != policy["source_of_truth"] or annotation["candidate_visible_during_initial_annotation"] is not False:
            raise OCRAcceptanceError(f"annotation_policy_invalid:{page_id}")
        _exact_keys(annotation["checks"], {"text", "table_cells", "bbox", "page_number", "digits"}, f"checks:{page_id}")
        if not isinstance(annotation["text"], str) or not isinstance(annotation["elements"], list) or not isinstance(annotation["tables"], list) or not isinstance(annotation["verified_digits"], list) or not isinstance(annotation["unresolved_issues"], list):
            raise OCRAcceptanceError(f"annotation_content_invalid:{page_id}")
        element_ids, reading_orders = set(), set()
        for index, element in enumerate(annotation["elements"]):
            label = f"element:{page_id}:{index}"
            element = _exact_keys(element, {"element_id", "kind", "reading_order", "page_number", "text", "bbox"}, label)
            if not isinstance(element["element_id"], str) or not element["element_id"] or element["kind"] not in ELEMENT_KINDS or isinstance(element["reading_order"], bool) or not isinstance(element["reading_order"], int) or element["reading_order"] < 1 or element["page_number"] != page_number or not isinstance(element["text"], str):
                raise OCRAcceptanceError(f"element_invalid:{label}")
            if element["element_id"] in element_ids or element["reading_order"] in reading_orders:
                raise OCRAcceptanceError(f"element_duplicate:{label}")
            element_ids.add(element["element_id"])
            reading_orders.add(element["reading_order"])
            _bbox(element["bbox"], width, height, label)
        table_ids = [table.get("table_id") for table in annotation["tables"] if isinstance(table, Mapping)]
        if len(table_ids) != len(set(table_ids)):
            raise OCRAcceptanceError(f"table_id_duplicate:{page_id}")
        for index, table in enumerate(annotation["tables"]):
            _validate_table(table, width, height, f"table:{page_id}:{index}")
        if annotation["status"] != "verified":
            manual_reasons.append(f"page_not_verified:{page_id}")
        else:
            if any(not isinstance(annotation[key], str) or not annotation[key].strip() for key in ("annotator_id", "reviewer_id")) or annotation["annotator_id"] == annotation["reviewer_id"]:
                manual_reasons.append(f"independent_review_missing:{page_id}")
            else:
                annotated = _timestamp(annotation["annotated_at"], f"annotated_at:{page_id}")
                reviewed = _timestamp(annotation["reviewed_at"], f"reviewed_at:{page_id}")
                if reviewed < annotated:
                    manual_reasons.append(f"review_before_annotation:{page_id}")
            if not all(value is True for value in annotation["checks"].values()) or annotation["unresolved_issues"]:
                manual_reasons.append(f"manual_checks_incomplete:{page_id}")
            if not normalize_text(annotation["text"]) and not annotation["tables"] and not annotation["elements"]:
                manual_reasons.append(f"human_truth_empty:{page_id}")
            reconstructed = "\n".join(element["text"] for element in sorted(annotation["elements"], key=lambda item: item["reading_order"]) if element["text"])
            if normalize_text(reconstructed) != normalize_text(annotation["text"]):
                manual_reasons.append(f"human_text_elements_mismatch:{page_id}")
            if ({"table", "complex_table"} & set(page["strata"]) and not annotation["tables"]) or any(label in page["strata"] and not any(element["kind"] == label for element in annotation["elements"]) for label in ("chart", "formula")):
                manual_reasons.append(f"strata_annotation_incomplete:{page_id}")
            expected_digits = number_counter(annotation["text"])
            for table in annotation["tables"]:
                for cell in table["cells"]:
                    expected_digits.update(number_counter(cell["text"]))
            if any(not isinstance(item, str) for item in annotation["verified_digits"]):
                raise OCRAcceptanceError(f"verified_digits_type_invalid:{page_id}")
            supplied_digits = Counter(annotation["verified_digits"])
            if supplied_digits != expected_digits:
                manual_reasons.append(f"verified_digits_mismatch:{page_id}")
        if verify_files:
            try:
                import fitz
            except ImportError as exc:
                raise OCRAcceptanceError("dependency_unavailable:pymupdf") from exc
            source_path = _within(root / Path(*PurePosixPath(source["path"]).parts), root, f"source:{page_id}")
            if not source_path.is_file() or _sha256_file(source_path) != source["sha256"]:
                raise OCRAcceptanceError(f"source_file_hash_mismatch:{page_id}")
            archive = _within(root / Path(*PurePosixPath(render["archive"]).parts), root, f"render_archive:{page_id}")
            try:
                with zipfile.ZipFile(archive) as package:
                    image = package.read(render["entry"])
            except (OSError, KeyError, zipfile.BadZipFile) as exc:
                raise OCRAcceptanceError(f"render_unavailable:{page_id}") from exc
            if _sha256_bytes(image) != render["sha256"]:
                raise OCRAcceptanceError(f"render_hash_mismatch:{page_id}")
            try:
                with fitz.open(source_path) as document:
                    if document.needs_pass or document.page_count != page_count:
                        raise OCRAcceptanceError(f"source_pdf_contract_mismatch:{page_id}")
                    pdf_page = document[page_number - 1]
                    if abs(pdf_page.rect.width - width) > 0.001 or abs(pdf_page.rect.height - height) > 0.001:
                        raise OCRAcceptanceError(f"source_page_size_mismatch:{page_id}")
                    pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), colorspace=fitz.csRGB, alpha=False)
                    if pixmap.width != render["width_px"] or pixmap.height != render["height_px"] or pixmap.tobytes("png") != image:
                        raise OCRAcceptanceError(f"render_not_reproducible:{page_id}")
            except OCRAcceptanceError:
                raise
            except Exception as exc:
                raise OCRAcceptanceError(f"source_page_render_failed:{page_id}") from exc
    if batches != Counter({1: 10, 2: 10, 3: 10}) or not REQUIRED_STRATA <= strata:
        raise OCRAcceptanceError("stratification_contract_invalid")
    if not manual_reasons and gold["dataset_status"] != "verified":
        manual_reasons.append("dataset_status_not_verified")
    if manual_reasons and gold["dataset_status"] == "verified":
        manual_reasons.append("dataset_status_claims_unverified_gold")
    return sorted(set(manual_reasons))


def _cells(table: Mapping[str, Any]) -> Counter[tuple[int, int, int, int, str]]:
    return Counter(
        (cell["row"], cell["column"], cell["row_span"], cell["column_span"], normalize_text(cell["text"]))
        for cell in table["cells"]
    )


def _counter_counts(gold: Counter[Any], candidate: Counter[Any]) -> tuple[int, int, int]:
    true_positive = sum((gold & candidate).values())
    return true_positive, sum((candidate - gold).values()), sum((gold - candidate).values())


def _page_tables(page: Mapping[str, Any], *, candidate: bool) -> list[dict[str, Any]]:
    source = page["source"]
    width, height = float(source["page_width"]), float(source["page_height"])
    tables = page["tables"] if candidate else page["annotation"]["tables"]
    result: list[dict[str, Any]] = []
    for index, table in enumerate(tables):
        _validate_table(table, width, height, f"evaluation_table:{page['page_id']}:{index}")
        item = dict(table)
        item["_bbox"] = _bbox(table["bbox"], width, height, f"evaluation_table:{page['page_id']}:{index}")
        result.append(item)
    return result


def _table_metrics(gold_page: Mapping[str, Any], candidate_page: Mapping[str, Any]) -> tuple[int, int, int, list[tuple[int, int]]]:
    gold_tables = _page_tables(gold_page, candidate=False)
    candidate_tables = _page_tables(candidate_page, candidate=True)
    pairs = _best_matching(gold_tables, candidate_tables, same_kind=False)
    matched_gold, matched_candidate = {left for left, _ in pairs}, {right for _, right in pairs}
    true_positive = false_positive = false_negative = 0
    for gold_index, candidate_index in pairs:
        counts = _counter_counts(_cells(gold_tables[gold_index]), _cells(candidate_tables[candidate_index]))
        true_positive += counts[0]
        false_positive += counts[1]
        false_negative += counts[2]
    false_negative += sum(sum(_cells(table).values()) for index, table in enumerate(gold_tables) if index not in matched_gold)
    false_positive += sum(sum(_cells(table).values()) for index, table in enumerate(candidate_tables) if index not in matched_candidate)
    return true_positive, false_positive, false_negative, pairs


def _candidate_text(page: Mapping[str, Any]) -> str:
    source = page["source"]
    elements = page.get("elements")
    if not isinstance(page.get("text"), str) or not isinstance(elements, list):
        raise OCRAcceptanceError(f"candidate_text_contract_invalid:{page.get('page_id', '')}")
    orders: set[int] = set()
    for index, element in enumerate(elements):
        element = _exact_keys(element, {"element_id", "kind", "reading_order", "page_number", "text", "bbox"}, f"candidate_element:{page['page_id']}:{index}")
        if element["kind"] not in ELEMENT_KINDS or isinstance(element["reading_order"], bool) or not isinstance(element["reading_order"], int) or element["reading_order"] < 1 or element["reading_order"] in orders or element["page_number"] != source["page_number"] or not isinstance(element["text"], str):
            raise OCRAcceptanceError(f"candidate_element_contract_invalid:{page['page_id']}:{index}")
        orders.add(element["reading_order"])
    reconstructed = "\n".join(element["text"] for element in sorted(elements, key=lambda item: item["reading_order"]) if element["text"])
    if normalize_text(reconstructed) != normalize_text(page["text"]):
        raise OCRAcceptanceError(f"candidate_text_elements_mismatch:{page['page_id']}")
    return reconstructed


def _locators(page: Mapping[str, Any], *, candidate: bool) -> tuple[list[dict[str, Any]], int, int]:
    source = page["source"]
    width, height = float(source["page_width"]), float(source["page_height"])
    elements = page["elements"] if candidate else page["annotation"]["elements"]
    locators: list[dict[str, Any]] = []
    total = valid = 0
    for index, element in enumerate(elements):
        total += 1
        try:
            box = _bbox(element["bbox"], width, height, f"locator_element:{page['page_id']}:{index}")
        except OCRAcceptanceError:
            if not candidate:
                raise
            continue
        valid += 1
        locators.append({"kind": element["kind"], "_bbox": box})
    tables = page["tables"] if candidate else page["annotation"]["tables"]
    for table_index, table in enumerate(tables):
        for kind, item_index, item in [("table", table_index, table), *[("table_cell", index, cell) for index, cell in enumerate(table["cells"])]]:
            total += 1
            try:
                box = _bbox(item["bbox"], width, height, f"locator_{kind}:{page['page_id']}:{item_index}")
            except OCRAcceptanceError:
                if not candidate:
                    raise
                continue
            valid += 1
            locators.append({"kind": kind, "_bbox": box})
    return locators, total, valid


def _hallucinated_digits(gold_page: Mapping[str, Any], candidate_page: Mapping[str, Any], candidate_text: str, table_pairs: Sequence[tuple[int, int]]) -> tuple[int, dict[str, int]]:
    issues = candidate_page["page_id"]
    extras = number_counter(candidate_text) - number_counter(gold_page["annotation"]["text"])
    gold_tables = gold_page["annotation"]["tables"]
    candidate_tables = candidate_page["tables"]
    matched_candidate = {candidate_index for _, candidate_index in table_pairs}
    for gold_index, candidate_index in table_pairs:
        gold_cells = {(cell["row"], cell["column"]): cell["text"] for cell in gold_tables[gold_index]["cells"]}
        for cell in candidate_tables[candidate_index]["cells"]:
            extras.update(number_counter(cell["text"]) - number_counter(gold_cells.get((cell["row"], cell["column"]), "")))
    for index, table in enumerate(candidate_tables):
        if index not in matched_candidate:
            for cell in table["cells"]:
                extras.update(number_counter(cell["text"]))
    return sum(extras.values()), {f"{issues}:{token}": count for token, count in sorted(extras.items())}


def evaluate_verified(gold: Mapping[str, Any], candidates: Mapping[str, Mapping[str, Any]], *, gold_sha256: str = "", candidate_sha256: str = "") -> dict[str, Any]:
    pages = sorted(gold["pages"], key=lambda item: item["page_id"])
    if set(candidates) != {page["page_id"] for page in pages}:
        raise OCRAcceptanceError("candidate_page_set_mismatch")
    edits = characters = table_tp = table_fp = table_fn = 0
    locator_matched = locator_gold = locator_candidate = locator_candidate_valid = hallucinated = 0
    digit_issues: dict[str, int] = {}
    per_page: list[dict[str, Any]] = []
    for gold_page in pages:
        candidate_page = candidates[gold_page["page_id"]]
        if candidate_page.get("schema_version") != CANDIDATE_SCHEMA or candidate_page.get("source") != gold_page["source"]:
            raise OCRAcceptanceError(f"candidate_identity_mismatch:{gold_page['page_id']}")
        gold_text, candidate_text = normalize_text(gold_page["annotation"]["text"]), normalize_text(_candidate_text(candidate_page))
        page_edits = levenshtein_distance(gold_text, candidate_text)
        edits += page_edits
        characters += len(gold_text)
        tp, fp, fn, table_pairs = _table_metrics(gold_page, candidate_page)
        table_tp += tp
        table_fp += fp
        table_fn += fn
        gold_locators, gold_total, _ = _locators(gold_page, candidate=False)
        candidate_locators, candidate_total, candidate_valid = _locators(candidate_page, candidate=True)
        matched = len(_best_matching(gold_locators, candidate_locators, same_kind=True))
        locator_matched += matched
        locator_gold += gold_total
        locator_candidate += candidate_total
        locator_candidate_valid += candidate_valid
        page_hallucinated, page_digit_issues = _hallucinated_digits(gold_page, candidate_page, candidate_text, table_pairs)
        hallucinated += page_hallucinated
        digit_issues.update(page_digit_issues)
        per_page.append({"page_id": gold_page["page_id"], "cer_edits": page_edits, "gold_characters": len(gold_text), "table_tp": tp, "table_fp": fp, "table_fn": fn, "locator_matched": matched, "locator_gold": gold_total, "hallucinated_digits": page_hallucinated})
    if characters == 0 or table_tp + table_fn == 0 or locator_gold == 0:
        raise OCRAcceptanceError("evaluation_denominator_empty")
    table_denominator = 2 * table_tp + table_fp + table_fn
    checks = {
        "page_count_30": len(pages) == 30,
        "cer_lte_5pct": edits * CER_MAX_DENOMINATOR <= characters * CER_MAX_NUMERATOR,
        "table_f1_gte_0_90": TABLE_F1_MIN_DENOMINATOR * 2 * table_tp >= TABLE_F1_MIN_NUMERATOR * table_denominator,
        "locator_complete_100pct": locator_matched == locator_gold and locator_candidate_valid == locator_candidate,
        "hallucinated_digits_zero": hallucinated == 0,
    }
    report: dict[str, Any] = {
        "schema_version": "rag-r1-ocr-evaluation/v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "inputs": {"gold_sha256": gold_sha256, "candidate_sha256": candidate_sha256},
        "metrics": {
            "cer": edits / characters,
            "cer_edits": edits,
            "gold_characters": characters,
            "table_f1": (2 * table_tp / table_denominator) if table_denominator else None,
            "table_tp": table_tp,
            "table_fp": table_fp,
            "table_fn": table_fn,
            "locator_completeness": locator_matched / locator_gold,
            "locator_matched": locator_matched,
            "locator_gold": locator_gold,
            "candidate_locators": locator_candidate,
            "candidate_locators_valid": locator_candidate_valid,
            "hallucinated_digits": hallucinated,
        },
        "digit_issues": digit_issues,
        "pages": per_page,
    }
    report["evaluation_digest"] = _sha256_bytes(_json_bytes(report))
    return report


def _candidate_pages(path: Path) -> tuple[dict[str, Mapping[str, Any]], str]:
    path = path.resolve(strict=True)
    if path.suffix.lower() != ".zip":
        raise OCRAcceptanceError("candidate_package_must_be_zip")
    result: dict[str, Mapping[str, Any]] = {}
    try:
        with zipfile.ZipFile(path) as package:
            names = sorted(name for name in package.namelist() if "/candidates/" in name and name.endswith(".json"))
            for name in names:
                value = _load_json_bytes(package.read(name), name)
                page_id = value.get("page_id") if isinstance(value, Mapping) else None
                if not isinstance(page_id, str) or page_id in result:
                    raise OCRAcceptanceError("candidate_page_id_invalid_or_duplicate")
                result[page_id] = value
    except (OSError, zipfile.BadZipFile) as exc:
        raise OCRAcceptanceError("candidate_package_invalid") from exc
    return result, _sha256_file(path)


def _zip_bytes(entries: Mapping[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for name, value in sorted(entries.items()):
            _safe_relative(name, f"zip_entry:{name}")
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            package.writestr(info, value)
    return output.getvalue()


def _write_new_or_identical(path: Path, value: bytes) -> None:
    if path.exists():
        if not path.is_file() or path.read_bytes() != value:
            raise OCRAcceptanceError(f"refuse_overwrite_different_output:{path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _extract_page(selection: PageSelection, dpi: int) -> tuple[dict[str, Any], bytes]:
    try:
        import fitz
    except ImportError as exc:
        raise OCRAcceptanceError("dependency_unavailable:pymupdf") from exc
    source = SOURCES[selection.source_key]
    path = _within(ROOT / Path(*PurePosixPath(source.path).parts), ROOT, selection.page_id)
    if not path.is_file() or _sha256_file(path) != source.sha256:
        raise OCRAcceptanceError(f"source_hash_mismatch:{selection.page_id}")
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise OCRAcceptanceError(f"pdf_open_failed:{selection.page_id}") from exc
    try:
        if document.needs_pass or document.page_count != source.page_count or not 1 <= selection.page_number <= document.page_count:
            raise OCRAcceptanceError(f"pdf_contract_mismatch:{selection.page_id}")
        page = document[selection.page_number - 1]
        width, height = float(page.rect.width), float(page.rect.height)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), colorspace=fitz.csRGB, alpha=False)
        png = pixmap.tobytes("png")
        tables: list[dict[str, Any]] = []
        warnings = ["NO OCR OR VLM MODEL WAS INVOKED", "candidate_is_not_human_gold"]
        try:
            found = page.find_tables().tables
        except Exception:
            found = []
            warnings.append("native_table_detection_failed")
        for table_index, table in enumerate(found, start=1):
            extracted = table.extract()
            cells: list[dict[str, Any]] = []
            for row in range(table.row_count):
                for column in range(table.col_count):
                    flat_index = row * table.col_count + column
                    cell_box = table.cells[flat_index] if flat_index < len(table.cells) else None
                    text = "" if row >= len(extracted) or column >= len(extracted[row]) or extracted[row][column] is None else str(extracted[row][column])
                    if cell_box is None:
                        continue
                    cells.append({"row": row, "column": column, "row_span": 1, "column_span": 1, "text": text, "bbox": [round(float(item), 3) for item in cell_box]})
            tables.append({"table_id": f"{selection.page_id}-table-{table_index:03d}", "bbox": [round(float(item), 3) for item in table.bbox], "cells": cells})
        table_boxes = [table["bbox"] for table in tables]
        elements: list[dict[str, Any]] = []
        text_parts: list[str] = []
        order = 0
        for block in page.get_text("blocks", sort=True):
            if len(block) <= 6 or block[6] != 0 or not str(block[4]).strip():
                continue
            block_box = [float(item) for item in block[:4]]
            block_area = max(1.0, (block_box[2] - block_box[0]) * (block_box[3] - block_box[1]))
            in_table = any(
                max(0.0, min(block_box[2], box[2]) - max(block_box[0], box[0]))
                * max(0.0, min(block_box[3], box[3]) - max(block_box[1], box[1]))
                / block_area
                >= 0.5
                for box in table_boxes
            )
            if in_table:
                continue
            order += 1
            text = str(block[4]).strip()
            text_parts.append(text)
            elements.append({"element_id": f"{selection.page_id}-text-{order:03d}", "kind": "text", "reading_order": order, "page_number": selection.page_number, "text": text, "bbox": [round(float(item), 3) for item in block_box]})
        image_index = 0
        for info in page.get_image_info(hashes=True):
            box = info.get("bbox")
            if not box:
                continue
            image_index += 1
            elements.append({"element_id": f"{selection.page_id}-image-{image_index:03d}", "kind": "image", "reading_order": order + image_index, "page_number": selection.page_number, "text": "", "bbox": [round(float(item), 3) for item in box]})
        text = "\n".join(text_parts)
        status = "native_text_candidate" if normalize_text(text) else "no_text_layer_ocr_not_run"
        if status != "native_text_candidate":
            warnings.append(MANUAL_REQUIRED)
        source_record = {"path": source.path, "sha256": source.sha256, "page_number": selection.page_number, "page_count": source.page_count, "page_width": round(width, 3), "page_height": round(height, 3)}
        candidate = {
            "schema_version": CANDIDATE_SCHEMA,
            "page_id": selection.page_id,
            "source": source_record,
            "method": "pymupdf-native-text-layer-no-ocr-v1",
            "status": status,
            "ocr_model_used": False,
            "vlm_model_used": False,
            "human_verified": False,
            "text": text,
            "elements": elements,
            "tables": tables,
            "digits": sorted(number_counter(text).elements()),
            "warnings": warnings,
        }
        return candidate, png
    finally:
        document.close()


def _overlay(png: bytes, candidate: Mapping[str, Any]) -> bytes:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise OCRAcceptanceError("dependency_unavailable:pillow") from exc
    image = Image.open(io.BytesIO(png)).convert("RGB")
    source = candidate["source"]
    scale_x, scale_y = image.width / source["page_width"], image.height / source["page_height"]
    draw = ImageDraw.Draw(image)
    colors = {"text": "#1677ff", "image": "#fa8c16", "table": "#f5222d", "table_cell": "#52c41a"}
    items = [*candidate["elements"], *candidate["tables"]]
    for item in items:
        kind = item.get("kind", "table")
        box = item["bbox"]
        pixels = [round(box[0] * scale_x), round(box[1] * scale_y), round(box[2] * scale_x), round(box[3] * scale_y)]
        draw.rectangle(pixels, outline=colors[kind], width=max(2, image.width // 800))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _contact_sheet(rendered: Sequence[tuple[PageSelection, bytes]]) -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as exc:
        raise OCRAcceptanceError("dependency_unavailable:pillow") from exc
    cell_width, cell_height, label_height = 500, 700, 42
    canvas = Image.new("RGB", (cell_width * 3, (cell_height + label_height) * 10), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (selection, png) in enumerate(rendered):
        column, row = selection.batch - 1, (index % 10)
        x, y = column * cell_width, row * (cell_height + label_height)
        image = Image.open(io.BytesIO(png)).convert("RGB")
        image = ImageOps.contain(image, (cell_width - 12, cell_height - 12))
        canvas.paste(image, (x + (cell_width - image.width) // 2, y + 6))
        label = f"{selection.page_id} | p{selection.page_number} | {selection.strata[0]}"
        draw.text((x + 8, y + cell_height + 10), label, fill="black")
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _blank_annotation() -> dict[str, Any]:
    return {
        "status": "template",
        "source_of_truth": "human_transcription_from_rendered_page",
        "candidate_visible_during_initial_annotation": False,
        "annotator_id": "",
        "annotated_at": "",
        "reviewer_id": "",
        "reviewed_at": "",
        "checks": {"text": False, "table_cells": False, "bbox": False, "page_number": False, "digits": False},
        "text": "",
        "elements": [],
        "tables": [],
        "verified_digits": [],
        "unresolved_issues": ["manual_transcription_pending"],
    }


def _batch_readme(batch: int) -> bytes:
    return (
        f"# RAG-R1B OCR blind annotation batch {batch:02d}\n\n"
        "This archive contains exactly 10 rendered source pages and empty human annotation forms.\n"
        "Do not open the candidate review archive before the initial annotation is submitted and hashed.\n"
        "Automatic/native PDF extraction is never human gold. Fill text, tables/cells, elements, page/bbox, digits, annotator and timestamps; a different reviewer must verify all five checks.\n"
    ).encode("utf-8")


def prepare(output_dir: Path, gold_path: Path = GOLD_PATH, *, dpi: int = 200, selections: Sequence[PageSelection] = DEFAULT_SELECTIONS) -> dict[str, Any]:
    output_dir = _within(output_dir, ROOT / "docs" / "codex" / "evidence", "output_dir")
    if not output_dir.name.startswith("RAG_R1B_OCR_"):
        raise OCRAcceptanceError("output_directory_name_not_whitelisted")
    gold_path = gold_path.resolve()
    if gold_path != GOLD_PATH.resolve():
        raise OCRAcceptanceError("gold_path_not_whitelisted")
    if dpi != 200:
        raise OCRAcceptanceError("render_dpi_must_be_200")
    if len(selections) != 30 or Counter(item.batch for item in selections) != Counter({1: 10, 2: 10, 3: 10}) or len({item.page_id for item in selections}) != 30:
        raise OCRAcceptanceError("selection_contract_invalid")
    if not REQUIRED_STRATA <= {label for item in selections for label in item.strata}:
        raise OCRAcceptanceError("selection_strata_incomplete")
    page_records: list[dict[str, Any]] = []
    candidates: dict[str, bytes] = {}
    raw_images: dict[str, bytes] = {}
    overlays: dict[str, bytes] = {}
    rendered: list[tuple[PageSelection, bytes]] = []
    for selection in selections:
        candidate, png = _extract_page(selection, dpi)
        candidate_bytes = _json_bytes(candidate)
        candidates[selection.page_id] = candidate_bytes
        raw_images[selection.page_id] = png
        overlays[selection.page_id] = _overlay(png, candidate)
        rendered.append((selection, png))
        archive_name = f"rag_r1b_ocr_annotation_batch_{selection.batch:02d}.zip"
        page_records.append({
            "page_id": selection.page_id,
            "batch": selection.batch,
            "strata": list(selection.strata),
            "selection_reason": selection.reason,
            "source": candidate["source"],
            "render": {
                "archive": (output_dir.relative_to(ROOT) / archive_name).as_posix(),
                "entry": f"pages/{selection.page_id}.png",
                "sha256": _sha256_bytes(png),
                "dpi": dpi,
                "width_px": __import__("PIL.Image", fromlist=["Image"]).open(io.BytesIO(png)).width,
                "height_px": __import__("PIL.Image", fromlist=["Image"]).open(io.BytesIO(png)).height,
                "coordinate_space": "pdf_points",
            },
            "annotation": _blank_annotation(),
        })
    artifacts: dict[str, bytes] = {}
    for batch in (1, 2, 3):
        entries: dict[str, bytes] = {"README.md": _batch_readme(batch)}
        batch_pages = [page for page in page_records if page["batch"] == batch]
        for page in batch_pages:
            page_id = page["page_id"]
            annotation = {"schema_version": PAGE_ANNOTATION_SCHEMA, **page}
            entries[f"pages/{page_id}.png"] = raw_images[page_id]
            entries[f"annotations/{page_id}.json"] = _json_bytes(annotation)
        entries["manifest.json"] = _json_bytes({"schema_version": "rag-r1-ocr-blind-batch/v1", "batch": batch, "page_count": 10, "candidate_content_included": False, "pages": [{"page_id": page["page_id"], "source": page["source"], "render": page["render"], "strata": page["strata"]} for page in batch_pages]})
        checksums = "".join(f"{_sha256_bytes(value)}  {name}\n" for name, value in sorted(entries.items()))
        entries["checksums.sha256"] = checksums.encode("utf-8")
        artifacts[f"rag_r1b_ocr_annotation_batch_{batch:02d}.zip"] = _zip_bytes(entries)
    reviewer_entries: dict[str, bytes] = {
        "README.md": (
            "# RAG-R1B OCR candidate review material\n\n"
            "Open only after blind initial annotations are submitted and hashed. Candidates use the native PDF text layer and geometry only; no OCR/VLM model was invoked and no candidate is human gold.\n"
        ).encode("utf-8")
    }
    for selection in selections:
        reviewer_entries[f"batch_{selection.batch:02d}/candidates/{selection.page_id}.json"] = candidates[selection.page_id]
        reviewer_entries[f"batch_{selection.batch:02d}/overlays/{selection.page_id}.png"] = overlays[selection.page_id]
    reviewer_entries["manifest.json"] = _json_bytes({"schema_version": "rag-r1-ocr-candidate-review/v1", "page_count": 30, "human_verified": False, "ocr_or_vlm_model_used": False, "pages": [{"page_id": page["page_id"], "source": page["source"], "candidate_sha256": _sha256_bytes(candidates[page["page_id"]])} for page in page_records]})
    reviewer_entries["checksums.sha256"] = "".join(f"{_sha256_bytes(value)}  {name}\n" for name, value in sorted(reviewer_entries.items())).encode("utf-8")
    artifacts["rag_r1b_ocr_candidate_review.zip"] = _zip_bytes(reviewer_entries)
    artifacts["rag_r1b_ocr_contact_sheet.png"] = _contact_sheet(rendered)
    gold = {
        "schema_version": GOLD_SCHEMA,
        "dataset_id": "rag-r1b-ocr-gold-30",
        "dataset_status": "template",
        "metric_contract": dict(METRIC_CONTRACT),
        "manual_policy": dict(MANUAL_POLICY),
        "pages": page_records,
    }
    manifest = {
        "schema_version": "rag-r1-ocr-annotation-package/v1",
        "status": MANUAL_REQUIRED,
        "page_count": 30,
        "batch_count": 3,
        "batch_size": 10,
        "ocr_or_vlm_model_used": False,
        "automatic_candidate_is_gold": False,
        "sources": [{"source_key": key, "path": source.path, "sha256": source.sha256, "page_count": source.page_count} for key, source in sorted(SOURCES.items())],
        "pages": [{"page_id": page["page_id"], "batch": page["batch"], "strata": page["strata"], "source": page["source"], "render": page["render"], "candidate_entry": f"batch_{page['batch']:02d}/candidates/{page['page_id']}.json", "candidate_sha256": _sha256_bytes(candidates[page["page_id"]])} for page in page_records],
        "artifacts": {name: _sha256_bytes(value) for name, value in sorted(artifacts.items())},
    }
    artifacts["package_manifest.json"] = _json_bytes(manifest)
    for name, value in artifacts.items():
        _write_new_or_identical(output_dir / name, value)
    _write_new_or_identical(gold_path, _json_bytes(gold))
    return {"status": MANUAL_REQUIRED, "page_count": 30, "output_dir": str(output_dir), "gold": str(gold_path), "artifacts": manifest["artifacts"] | {"package_manifest.json": _sha256_bytes(artifacts["package_manifest.json"])} }


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 1.0
    return round(numerator / denominator, 6)


def _json_file(path: Path, label: str) -> tuple[Mapping[str, Any], str]:
    value = _load_json_bytes(path.resolve(strict=True).read_bytes(), label)
    if not isinstance(value, Mapping):
        raise OCRAcceptanceError(f"json_object_required:{label}")
    return value, _sha256_file(path)


def _package_pages(package: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if package.get("schema_version") != "rag-r1-ocr-annotation-package/v1" or package.get("page_count") != 30:
        raise OCRAcceptanceError("ai_consensus_package_invalid")
    pages = package.get("pages")
    if not isinstance(pages, list) or len(pages) != 30:
        raise OCRAcceptanceError("ai_consensus_package_pages_invalid")
    by_id = {str(page.get("page_id") or ""): page for page in pages if isinstance(page, Mapping)}
    if len(by_id) != 30 or "" in by_id:
        raise OCRAcceptanceError("ai_consensus_package_page_ids_invalid")
    return by_id


def _ai_page_digits(page: Mapping[str, Any]) -> Counter[str]:
    values = number_counter(str(page.get("text") or ""))
    for table in page.get("tables") or []:
        if isinstance(table, Mapping):
            for cell in table.get("cells") or []:
                if isinstance(cell, Mapping):
                    values += number_counter(str(cell.get("text") or ""))
    return values


def _validate_ai_page(page: Any, package_page: Mapping[str, Any], label: str) -> dict[str, Any]:
    page = _exact_keys(page, {"page_id", "render_sha256", "text", "elements", "tables", "page_number", "digits", "unresolved"}, label)
    page_id = str(page["page_id"])
    if page_id != package_page.get("page_id") or page["render_sha256"] != package_page.get("render", {}).get("sha256"):
        raise OCRAcceptanceError(f"ai_page_identity_invalid:{page_id}")
    source = package_page.get("source")
    if not isinstance(source, Mapping):
        raise OCRAcceptanceError(f"ai_page_source_invalid:{page_id}")
    width, height = float(source.get("page_width") or 0), float(source.get("page_height") or 0)
    if width <= 0 or height <= 0 or type(page["page_number"]) is not int or page["page_number"] != source.get("page_number"):
        raise OCRAcceptanceError(f"ai_page_number_invalid:{page_id}")
    if not isinstance(page["text"], str) or "\ufffd" in page["text"] or not isinstance(page["elements"], list) or not isinstance(page["tables"], list):
        raise OCRAcceptanceError(f"ai_page_content_invalid:{page_id}")
    element_ids: set[str] = set()
    for index, element in enumerate(page["elements"]):
        element = _exact_keys(element, {"element_id", "kind", "reading_order", "page_number", "text", "bbox"}, f"{label}:element:{index}")
        if not _text(element["element_id"]) or element["element_id"] in element_ids or element["kind"] not in ELEMENT_KINDS:
            raise OCRAcceptanceError(f"ai_element_identity_invalid:{page_id}:{index}")
        element_ids.add(element["element_id"])
        if type(element["reading_order"]) is not int or element["reading_order"] < 1 or element["page_number"] != page["page_number"] or not isinstance(element["text"], str):
            raise OCRAcceptanceError(f"ai_element_contract_invalid:{page_id}:{index}")
        _bbox(element["bbox"], width, height, f"{label}:element:{index}")
    if len({element["reading_order"] for element in page["elements"]}) != len(page["elements"]):
        raise OCRAcceptanceError(f"ai_element_order_duplicate:{page_id}")
    table_ids: set[str] = set()
    for index, table in enumerate(page["tables"]):
        _validate_table(table, width, height, f"{label}:table:{index}")
        table_id = str(table.get("table_id") or "")
        if not table_id or table_id in table_ids:
            raise OCRAcceptanceError(f"ai_table_identity_invalid:{page_id}:{index}")
        table_ids.add(table_id)
    reconstructed = "\n".join(
        element["text"]
        for element in sorted(page["elements"], key=lambda item: item["reading_order"])
        if element["text"]
    )
    if not normalize_text(page["text"]) and not page["elements"] and not page["tables"]:
        raise OCRAcceptanceError(f"ai_page_truth_empty:{page_id}")
    if normalize_text(reconstructed) != normalize_text(page["text"]):
        raise OCRAcceptanceError(f"ai_page_text_elements_mismatch:{page_id}")
    strata = set(package_page.get("strata") or [])
    if ({"table", "complex_table"} & strata and not page["tables"]) or any(
        kind in strata and not any(element["kind"] == kind for element in page["elements"])
        for kind in ("chart", "formula")
    ):
        raise OCRAcceptanceError(f"ai_page_strata_incomplete:{page_id}")
    if not isinstance(page["digits"], list) or any(not isinstance(value, str) for value in page["digits"]):
        raise OCRAcceptanceError(f"ai_digits_invalid:{page_id}")
    try:
        supplied = Counter(_canonical_number(value) for value in page["digits"])
    except (InvalidOperation, ValueError) as exc:
        raise OCRAcceptanceError(f"ai_digits_invalid:{page_id}") from exc
    if supplied != _ai_page_digits(page):
        raise OCRAcceptanceError(f"ai_digits_content_mismatch:{page_id}")
    if not isinstance(page["unresolved"], list) or any(not _text(value) for value in page["unresolved"]):
        raise OCRAcceptanceError(f"ai_unresolved_invalid:{page_id}")
    return dict(page)


def validate_ai_role_output(value: Any, package: Mapping[str, Any], *, origin: str, isolation: str, review_pass: int) -> list[dict[str, Any]]:
    value = _exact_keys(value, {"schema_version", "origin", "model_role", "input_isolation", "review_pass", "human_verified", "pages"}, origin)
    if value["schema_version"] != AI_ROLE_SCHEMA or value["origin"] != origin or not _text(value["model_role"]):
        raise OCRAcceptanceError(f"ai_role_identity_invalid:{origin}")
    if value["input_isolation"] != isolation or value["review_pass"] != review_pass or value["human_verified"] is not False:
        raise OCRAcceptanceError(f"ai_role_isolation_invalid:{origin}")
    pages = value["pages"]
    package_pages = _package_pages(package)
    if not isinstance(pages, list) or len(pages) != 30:
        raise OCRAcceptanceError(f"ai_role_page_count_invalid:{origin}")
    by_id = {str(page.get("page_id") or ""): page for page in pages if isinstance(page, Mapping)}
    if set(by_id) != set(package_pages):
        raise OCRAcceptanceError(f"ai_role_page_set_invalid:{origin}")
    return [_validate_ai_page(by_id[page_id], package_pages[page_id], f"{origin}:{page_id}") for page_id in sorted(package_pages)]


def _ai_cells(page: Mapping[str, Any]) -> Counter[tuple[int, int, int, int, str]]:
    result: Counter[tuple[int, int, int, int, str]] = Counter()
    for table in page["tables"]:
        result += _cells(table)
    return result


def _ai_boxes(page: Mapping[str, Any], package_page: Mapping[str, Any], label: str) -> list[dict[str, Any]]:
    source = package_page["source"]
    width, height = float(source["page_width"]), float(source["page_height"])
    result: list[dict[str, Any]] = []
    for index, element in enumerate(page["elements"]):
        result.append({"kind": str(element["kind"]), "_bbox": _bbox(element["bbox"], width, height, f"{label}:element:{index}")})
    for table_index, table in enumerate(page["tables"]):
        result.append({"kind": "table", "_bbox": _bbox(table["bbox"], width, height, f"{label}:table:{table_index}")})
        for cell_index, cell in enumerate(table["cells"]):
            result.append({"kind": "cell", "_bbox": _bbox(cell["bbox"], width, height, f"{label}:cell:{table_index}:{cell_index}")})
    return result


def _ai_page_comparison(left: Mapping[str, Any], right: Mapping[str, Any], package_page: Mapping[str, Any]) -> dict[str, Any]:
    left_text, right_text = normalize_text(left["text"]), normalize_text(right["text"])
    left_cells, right_cells = _ai_cells(left), _ai_cells(right)
    left_boxes = _ai_boxes(left, package_page, "extractor")
    right_boxes = _ai_boxes(right, package_page, "reviewer")
    pairs = _best_matching(left_boxes, right_boxes, same_kind=True)
    bbox_ious = [_iou(left_boxes[a]["_bbox"], right_boxes[b]["_bbox"]) for a, b in pairs]
    left_digits, right_digits = _ai_page_digits(left), _ai_page_digits(right)
    return {
        "text_edits": levenshtein_distance(left_text, right_text),
        "text_characters": max(len(left_text), len(right_text)),
        "table_cell_symmetric_difference": sum((left_cells - right_cells).values()) + sum((right_cells - left_cells).values()),
        "table_tp": sum((left_cells & right_cells).values()),
        "table_left": sum(left_cells.values()),
        "table_right": sum(right_cells.values()),
        "bbox_matched": len(pairs),
        "bbox_total": max(len(left_boxes), len(right_boxes)),
        "bbox_iou_sum": round(sum(bbox_ious), 9),
        "page_number_mismatch": left["page_number"] != right["page_number"],
        "digit_symmetric_difference": sum((left_digits - right_digits).values()) + sum((right_digits - left_digits).values()),
        "digit_intersection": sum((left_digits & right_digits).values()),
        "digit_union": sum((left_digits | right_digits).values()),
    }


def _ai_metrics(pages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparisons = [page["computed_differences"] for page in pages]
    text_characters = sum(row["text_characters"] for row in comparisons)
    edits = sum(row["text_edits"] for row in comparisons)
    table_tp = sum(row["table_tp"] for row in comparisons)
    table_total = sum(row["table_left"] + row["table_right"] for row in comparisons)
    bbox_matched = sum(row["bbox_matched"] for row in comparisons)
    digit_union = sum(row["digit_union"] for row in comparisons)
    return {
        "page_count": len(pages),
        "text_agreement_rate": _rate(sum(row["text_edits"] == 0 for row in comparisons), len(pages)),
        "consensus_CER_proxy": round(edits / text_characters, 6) if text_characters else 0.0,
        "table_structure_agreement_rate": _rate(sum(row["table_cell_symmetric_difference"] == 0 for row in comparisons), len(pages)),
        "consensus_table_F1_proxy": round((2 * table_tp) / table_total, 6) if table_total else 1.0,
        "bbox_iou_proxy": round(sum(row["bbox_iou_sum"] for row in comparisons) / bbox_matched, 6) if bbox_matched else 1.0,
        "page_number_agreement_rate": _rate(sum(not row["page_number_mismatch"] for row in comparisons), len(pages)),
        "digit_agreement_rate": round(sum(row["digit_intersection"] for row in comparisons) / digit_union, 6) if digit_union else 1.0,
        "unresolved_disagreements": sum(len(page["adjudication"]["unresolved"]) for page in pages),
        "hallucinated_digits": sum(page["hallucinated_digits"] for page in pages),
        "human_gold_status": "unavailable",
        "metric_semantics": "AI consensus proxy; not human gold CER/F1",
        "per_page": [{"page_id": page["page_id"], "status": page["status"], **page["computed_differences"], "hallucinated_digits": page["hallucinated_digits"]} for page in pages],
    }


def assemble_ai_consensus(extractor: Mapping[str, Any], reviewer: Mapping[str, Any], adjudication: Mapping[str, Any], package: Mapping[str, Any], *, extractor_sha256: str, reviewer_sha256: str, adjudication_sha256: str, package_sha256: str, frozen_at: str) -> dict[str, Any]:
    package_pages = _package_pages(package)
    left = validate_ai_role_output(extractor, package, origin=AI_ROLE_ORIGINS[0], isolation="blind_page_images_only", review_pass=1)
    right = validate_ai_role_output(reviewer, package, origin=AI_ROLE_ORIGINS[1], isolation="blind_page_images_only_no_extractor_access", review_pass=2)
    adjudication = _exact_keys(adjudication, {"schema_version", "origin", "model_role", "input_isolation", "review_pass", "human_verified", "pages"}, "adjudication")
    if adjudication["schema_version"] != AI_ADJUDICATION_SCHEMA or adjudication["origin"] != AI_ROLE_ORIGINS[2] or not _text(adjudication["model_role"]):
        raise OCRAcceptanceError("ai_adjudicator_identity_invalid")
    if adjudication["input_isolation"] != "page_images_plus_a_b_only" or adjudication["review_pass"] != 3 or adjudication["human_verified"] is not False:
        raise OCRAcceptanceError("ai_adjudicator_isolation_invalid")
    adjudication_pages = adjudication["pages"]
    if not isinstance(adjudication_pages, list) or len(adjudication_pages) != 30:
        raise OCRAcceptanceError("ai_adjudication_page_count_invalid")
    adj_by_id = {str(page.get("page_id") or ""): page for page in adjudication_pages if isinstance(page, Mapping)}
    if set(adj_by_id) != set(package_pages):
        raise OCRAcceptanceError("ai_adjudication_page_set_invalid")
    left_by_id, right_by_id = {page["page_id"]: page for page in left}, {page["page_id"]: page for page in right}
    pages: list[dict[str, Any]] = []
    for page_id in sorted(package_pages):
        item = _exact_keys(adj_by_id[page_id], {"page_id", "render_sha256", "differences", "decisions", "final", "resolved", "unresolved"}, f"adjudication:{page_id}")
        if item["render_sha256"] != package_pages[page_id]["render"]["sha256"] or item["resolved"] is not True:
            raise OCRAcceptanceError(f"ai_adjudication_resolution_invalid:{page_id}")
        if not isinstance(item["differences"], list) or any(not _text(value) for value in item["differences"]):
            raise OCRAcceptanceError(f"ai_adjudication_differences_invalid:{page_id}")
        if not isinstance(item["decisions"], list) or any(not _text(value) for value in item["decisions"]):
            raise OCRAcceptanceError(f"ai_adjudication_decisions_invalid:{page_id}")
        if not isinstance(item["unresolved"], list) or item["unresolved"]:
            raise OCRAcceptanceError(f"ai_adjudication_unresolved:{page_id}")
        final = _validate_ai_page(item["final"], package_pages[page_id], f"adjudication_final:{page_id}")
        if final["unresolved"]:
            raise OCRAcceptanceError(f"ai_final_unresolved:{page_id}")
        comparison = _ai_page_comparison(left_by_id[page_id], right_by_id[page_id], package_pages[page_id])
        has_difference = any((value is True) or (type(value) in {int, float} and value > 0) for key, value in comparison.items() if key in {"text_edits", "table_cell_symmetric_difference", "page_number_mismatch", "digit_symmetric_difference"}) or comparison["bbox_matched"] < comparison["bbox_total"]
        if has_difference and not item["decisions"]:
            raise OCRAcceptanceError(f"ai_adjudication_decision_missing:{page_id}")
        allowed_digits = _ai_page_digits(left_by_id[page_id]) | _ai_page_digits(right_by_id[page_id])
        hallucinated = sum((_ai_page_digits(final) - allowed_digits).values())
        if hallucinated:
            raise OCRAcceptanceError(f"ai_final_hallucinated_digits:{page_id}")
        pages.append({"page_id": page_id, "render_sha256": item["render_sha256"], "extractor": left_by_id[page_id], "reviewer": right_by_id[page_id], "computed_differences": comparison, "adjudication": {"origin": AI_ROLE_ORIGINS[2], "differences": list(item["differences"]), "decisions": list(item["decisions"]), "resolved": True, "unresolved": []}, "final": final, "hallucinated_digits": 0, "status": "consensus_verified"})
    metrics = _ai_metrics(pages)
    if metrics["page_count"] != 30 or metrics["unresolved_disagreements"] != 0 or metrics["hallucinated_digits"] != 0:
        raise OCRAcceptanceError("ai_consensus_gate_failed")
    if not isinstance(frozen_at, str) or not frozen_at.endswith(("Z", "+00:00")):
        raise OCRAcceptanceError("ai_consensus_frozen_at_invalid")
    roles = {
        "extractor": {"origin": AI_ROLE_ORIGINS[0], "model_role": extractor["model_role"], "input_isolation": extractor["input_isolation"], "review_pass": 1, "artifact_sha256": extractor_sha256},
        "reviewer": {"origin": AI_ROLE_ORIGINS[1], "model_role": reviewer["model_role"], "input_isolation": reviewer["input_isolation"], "review_pass": 2, "artifact_sha256": reviewer_sha256},
        "adjudicator": {"origin": AI_ROLE_ORIGINS[2], "model_role": adjudication["model_role"], "input_isolation": adjudication["input_isolation"], "review_pass": 3, "artifact_sha256": adjudication_sha256},
    }
    result = {"schema_version": AI_CONSENSUS_SCHEMA, "status": AI_CONSENSUS_VERIFIED, "verification_mode": AI_VERIFICATION_MODE, "human_verified": False, "automated_consensus_verified": True, "production_human_signoff": False, "review_passes": 3, "source_package_sha256": package_sha256, "roles": roles, "frozen_at": frozen_at, "pages": pages, "metrics": metrics}
    result["consensus_sha256"] = _sha256_bytes(_json_bytes(result))
    return result


def validate_ai_consensus(value: Any, package: Mapping[str, Any], package_sha256: str) -> dict[str, Any]:
    expected_keys = {"schema_version", "status", "verification_mode", "human_verified", "automated_consensus_verified", "production_human_signoff", "review_passes", "source_package_sha256", "roles", "frozen_at", "pages", "metrics", "consensus_sha256"}
    value = _exact_keys(value, expected_keys, "ai_consensus")
    if value["schema_version"] != AI_CONSENSUS_SCHEMA or value["status"] != AI_CONSENSUS_VERIFIED or value["verification_mode"] != AI_VERIFICATION_MODE:
        raise OCRAcceptanceError("ai_consensus_identity_invalid")
    if value["human_verified"] is not False or value["automated_consensus_verified"] is not True or value["production_human_signoff"] is not False or value["review_passes"] != 3:
        raise OCRAcceptanceError("ai_consensus_provenance_invalid")
    if value["source_package_sha256"] != package_sha256 or len(value["pages"]) != 30:
        raise OCRAcceptanceError("ai_consensus_package_mismatch")
    roles = value["roles"]
    if not isinstance(roles, Mapping) or tuple(roles[name]["origin"] for name in ("extractor", "reviewer", "adjudicator")) != AI_ROLE_ORIGINS:
        raise OCRAcceptanceError("ai_consensus_roles_invalid")
    package_pages = _package_pages(package)
    if {page["page_id"] for page in value["pages"]} != set(package_pages):
        raise OCRAcceptanceError("ai_consensus_page_set_invalid")
    for page in value["pages"]:
        if page.get("status") != "consensus_verified" or page.get("hallucinated_digits") != 0 or page.get("adjudication", {}).get("unresolved"):
            raise OCRAcceptanceError(f"ai_consensus_page_gate_failed:{page.get('page_id')}")
        _validate_ai_page(page["extractor"], package_pages[page["page_id"]], f"consensus_extractor:{page['page_id']}")
        _validate_ai_page(page["reviewer"], package_pages[page["page_id"]], f"consensus_reviewer:{page['page_id']}")
        _validate_ai_page(page["final"], package_pages[page["page_id"]], f"consensus_final:{page['page_id']}")
        if page["computed_differences"] != _ai_page_comparison(page["extractor"], page["reviewer"], package_pages[page["page_id"]]):
            raise OCRAcceptanceError(f"ai_consensus_difference_tampered:{page['page_id']}")
    if value["metrics"] != _ai_metrics(value["pages"]):
        raise OCRAcceptanceError("ai_consensus_metrics_tampered")
    unsigned = dict(value)
    consensus_sha256 = unsigned.pop("consensus_sha256")
    if not isinstance(consensus_sha256, str) or consensus_sha256 != _sha256_bytes(_json_bytes(unsigned)):
        raise OCRAcceptanceError("ai_consensus_sha256_invalid")
    return {"status": AI_CONSENSUS_VERIFIED, "page_count": 30, "metrics": value["metrics"], "consensus_sha256": consensus_sha256, "human_verified": False, "automated_consensus_verified": True, "production_human_signoff": False}


def _manual_report(reasons: Sequence[str]) -> dict[str, Any]:
    return {"schema_version": "rag-r1-ocr-evaluation/v1", "status": MANUAL_REQUIRED, "reason_codes": list(reasons), "metrics": None, "gate": {"status": MANUAL_REQUIRED}}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare and evaluate the RAG-R1B 30-page OCR human-gold package")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    assemble_parser = subparsers.add_parser("assemble-ai-consensus")
    assemble_parser.add_argument("--extractor", type=Path, required=True)
    assemble_parser.add_argument("--reviewer", type=Path, required=True)
    assemble_parser.add_argument("--adjudication", type=Path, required=True)
    assemble_parser.add_argument("--package-manifest", type=Path, required=True)
    assemble_parser.add_argument("--output", type=Path, required=True)
    assemble_parser.add_argument("--frozen-at", required=True)
    consensus_parser = subparsers.add_parser("validate-ai-consensus")
    consensus_parser.add_argument("--consensus", type=Path, required=True)
    consensus_parser.add_argument("--package-manifest", type=Path, required=True)
    validate_parser = subparsers.add_parser("validate-gold")
    validate_parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    evaluate_parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            report = prepare(args.output_dir, args.gold)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.command == "assemble-ai-consensus":
            extractor, extractor_sha = _json_file(args.extractor, "extractor")
            reviewer, reviewer_sha = _json_file(args.reviewer, "reviewer")
            adjudication, adjudication_sha = _json_file(args.adjudication, "adjudication")
            package, package_sha = _json_file(args.package_manifest, "package_manifest")
            report = assemble_ai_consensus(extractor, reviewer, adjudication, package, extractor_sha256=extractor_sha, reviewer_sha256=reviewer_sha, adjudication_sha256=adjudication_sha, package_sha256=package_sha, frozen_at=args.frozen_at)
            _write_new_or_identical(args.output, _json_bytes(report))
            print(json.dumps({"status": report["status"], "page_count": 30, "output": str(args.output), "consensus_sha256": report["consensus_sha256"]}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "validate-ai-consensus":
            consensus, _ = _json_file(args.consensus, "ai_consensus")
            package, package_sha = _json_file(args.package_manifest, "package_manifest")
            print(json.dumps(validate_ai_consensus(consensus, package, package_sha), ensure_ascii=False, indent=2))
            return 0
        if args.gold.resolve() != GOLD_PATH.resolve():
            raise OCRAcceptanceError("gold_path_not_whitelisted")
        gold_bytes = args.gold.resolve(strict=True).read_bytes()
        gold = _load_json_bytes(gold_bytes, str(args.gold))
        reasons = validate_gold(gold, verify_files=True)
        if reasons:
            print(json.dumps(_manual_report(reasons), ensure_ascii=False, indent=2))
            return 3
        if args.command == "validate-gold":
            print(json.dumps({"status": "VERIFIED HUMAN GOLD", "page_count": 30}, ensure_ascii=False, indent=2))
            return 0
        candidates, candidate_sha256 = _candidate_pages(args.candidate)
        report = evaluate_verified(gold, candidates, gold_sha256=_sha256_bytes(gold_bytes), candidate_sha256=candidate_sha256)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 2
    except Exception as exc:
        print(f"RAG-R1B OCR acceptance ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

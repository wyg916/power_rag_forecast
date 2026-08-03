import copy, io, json, zipfile
from collections import Counter

import pytest

from scripts import rag_r1_ocr_acceptance as acceptance


def _verified_fixture():
    pages, candidates = [], {}
    for index in range(1, 31):
        page_id = f"ocr-{index:03d}"
        selection, spec = acceptance.DEFAULT_SELECTIONS[index - 1], acceptance.SOURCES[acceptance.DEFAULT_SELECTIONS[index - 1].source_key]
        source = {
            "path": spec.path,
            "sha256": spec.sha256,
            "page_number": selection.page_number,
            "page_count": spec.page_count,
            "page_width": 100.0,
            "page_height": 100.0,
        }
        cell = {"row": 0, "column": 0, "row_span": 1, "column_span": 1, "text": "20", "bbox": [10, 30, 40, 40]}
        table = {"table_id": f"g-{index}", "bbox": [5, 25, 50, 50], "cells": [cell]}
        element = {"element_id": f"g-e-{index}", "kind": "text", "reading_order": 1, "page_number": selection.page_number, "text": "电价100", "bbox": [5, 5, 50, 20]}
        elements = [element, {"element_id": f"g-c-{index}", "kind": "chart", "reading_order": 2, "page_number": selection.page_number, "text": "", "bbox": [55, 5, 75, 20]}, {"element_id": f"g-f-{index}", "kind": "formula", "reading_order": 3, "page_number": selection.page_number, "text": "", "bbox": [76, 5, 95, 20]}]
        annotation = {
            "status": "verified",
            "source_of_truth": "human_transcription_from_rendered_page",
            "candidate_visible_during_initial_annotation": False,
            "annotator_id": "annotator",
            "annotated_at": "2026-08-03T10:00:00+08:00",
            "reviewer_id": "reviewer",
            "reviewed_at": "2026-08-03T11:00:00+08:00",
            "checks": {"text": True, "table_cells": True, "bbox": True, "page_number": True, "digits": True},
            "text": "电价100",
            "elements": elements,
            "tables": [table],
            "verified_digits": ["100", "20"],
            "unresolved_issues": [],
        }
        pages.append({"page_id": page_id, "batch": selection.batch, "strata": list(selection.strata), "selection_reason": selection.reason, "source": source, "render": {"archive": "x.zip", "entry": f"pages/{page_id}.png", "sha256": "a" * 64, "dpi": 200, "width_px": 200, "height_px": 200, "coordinate_space": "pdf_points"}, "annotation": annotation})
        candidates[page_id] = {"schema_version": acceptance.CANDIDATE_SCHEMA, "page_id": page_id, "source": source, "text": "电价100", "elements": elements, "tables": [{"table_id": f"c-{index}", "bbox": table["bbox"], "cells": [cell]}]}
    gold = {
        "schema_version": acceptance.GOLD_SCHEMA,
        "dataset_id": "rag-r1b-ocr-gold-30",
        "dataset_status": "verified",
        "metric_contract": {"normalization": "nfkc-whitespace-v1", "cer_max": 0.05, "table_f1_min": 0.9, "locator_iou_min": 0.5, "locator_complete": 1.0, "hallucinated_digits_max": 0},
        "manual_policy": {"required_page_count": 30, "batch_size": 10, "source_of_truth": "human_transcription_from_rendered_page", "independent_reviewer": True, "candidate_blind_initial_annotation": True, "automatic_candidate_is_gold": False},
        "pages": pages,
    }
    return gold, candidates


def test_fixed_selection_is_stratified_unique_and_three_batches():
    selections = acceptance.DEFAULT_SELECTIONS
    assert len(selections) == len({item.page_id for item in selections}) == 30
    assert Counter(item.batch for item in selections) == Counter({1: 10, 2: 10, 3: 10})
    assert acceptance.REQUIRED_STRATA <= {label for item in selections for label in item.strata}
    assert len({(acceptance.SOURCES[item.source_key].sha256, item.page_number) for item in selections}) == 30
    locators = [{"kind": "text", "_bbox": [index, 0, index + 1, 1]} for index in range(25)]
    assert len(acceptance._best_matching(locators, locators, same_kind=True)) == 25


def test_text_and_number_normalization_are_reproducible():
    assert acceptance.normalize_text("Ａ\u200b\r\n  B") == "A B"
    assert acceptance.levenshtein_distance("电价100", "电价10O") == 1
    assert acceptance.number_counter("１,０００ 1e3 -0% 5 5") == Counter({"1000": 2, "5": 2, "0%": 1})
    assert sum(acceptance._cells({"cells": [{"row": 0, "column": 0, "row_span": 1, "column_span": 1, "text": ""}]}).values()) == 1


def test_verified_metrics_pass_then_detect_repeated_fabricated_number():
    gold, candidates = _verified_fixture()
    assert acceptance.validate_gold(gold) == []
    tampered = copy.deepcopy(gold)
    tampered["metric_contract"]["cer_max"] = 0.99
    with pytest.raises(acceptance.OCRAcceptanceError, match="metric_contract_invalid"):
        acceptance.validate_gold(tampered)
    report = acceptance.evaluate_verified(gold, candidates)
    assert report["status"] == "PASS" and all(report["checks"].values())
    altered = copy.deepcopy(candidates)
    altered["ocr-001"]["text"] = "电价100 100"
    altered["ocr-001"]["elements"][0]["text"] = "电价100 100"
    failed = acceptance.evaluate_verified(gold, altered)
    assert failed["status"] == "FAIL"
    assert failed["metrics"]["hallucinated_digits"] == 1
    invalid = copy.deepcopy(candidates)
    invalid["ocr-001"]["elements"][0]["page_number"] = 999
    with pytest.raises(acceptance.OCRAcceptanceError, match="candidate_element_contract_invalid"):
        acceptance.evaluate_verified(gold, invalid)


def test_gold_template_and_blind_archives_never_claim_human_truth():
    gold = json.loads(acceptance.GOLD_PATH.read_text(encoding="utf-8"))
    reasons = acceptance.validate_gold(gold, verify_files=True)
    assert len([reason for reason in reasons if reason.startswith("page_not_verified:")]) == 30
    assert gold["dataset_status"] == "template"
    evidence = acceptance.ROOT / gold["pages"][0]["render"]["archive"]
    with zipfile.ZipFile(evidence) as package:
        names = package.namelist()
        assert any(name.startswith("pages/") for name in names)
        assert any(name.startswith("annotations/") for name in names)
        assert not any("candidate" in name.lower() for name in names)


def test_stable_zip_and_manual_cli_exit_code(capsys):
    first = acceptance._zip_bytes({"b.txt": b"2", "a.txt": b"1"})
    second = acceptance._zip_bytes({"a.txt": b"1", "b.txt": b"2"})
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as package:
        assert package.namelist() == ["a.txt", "b.txt"]
    assert acceptance.main(["validate-gold", "--gold", str(acceptance.GOLD_PATH)]) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == acceptance.MANUAL_REQUIRED and output["metrics"] is None


def _ai_page(package_page, *, text_suffix=""):
    page_number = package_page["source"]["page_number"]
    text = f"page {page_number} value {page_number}{text_suffix}"
    required_kinds = [kind for kind in ("chart", "formula") if kind in package_page["strata"]]
    kinds = required_kinds or ["text"]
    elements = [
        {
            "element_id": f"{package_page['page_id']}-e{index}",
            "kind": kind,
            "reading_order": index,
            "page_number": page_number,
            "text": text if index == 1 else "",
            "bbox": [float(index - 1), 0.0, float(index + 9), 10.0],
        }
        for index, kind in enumerate(kinds, start=1)
    ]
    tables = []
    if {"table", "complex_table"} & set(package_page["strata"]):
        tables = [{
            "table_id": f"{package_page['page_id']}-t1",
            "bbox": [0.0, 10.0, 10.0, 20.0],
            "cells": [{
                "row": 0, "column": 0, "row_span": 1, "column_span": 1,
                "text": "", "bbox": [0.0, 10.0, 10.0, 20.0],
            }],
        }]
    return {
        "page_id": package_page["page_id"],
        "render_sha256": package_page["render"]["sha256"],
        "text": text,
        "elements": elements,
        "tables": tables,
        "page_number": page_number,
        "digits": [str(page_number), str(page_number)],
        "unresolved": [],
    }


def _ai_role(package, *, origin, isolation, review_pass, suffix=""):
    return {
        "schema_version": acceptance.AI_ROLE_SCHEMA,
        "origin": origin,
        acceptance.AI_ROLE_ORIGIN_FIELDS[origin]: origin,
        "model_role": f"role-{review_pass}",
        "input_isolation": isolation,
        "review_pass": review_pass,
        "human_verified": False,
        "pages": [_ai_page(page, text_suffix=suffix) for page in package["pages"]],
    }


def _ai_adjudication(package, extractor):
    return {
        "schema_version": acceptance.AI_ADJUDICATION_SCHEMA,
        "origin": acceptance.AI_ROLE_ORIGINS[2],
        "adjudicator_origin": acceptance.AI_ROLE_ORIGINS[2],
        "model_role": "role-3",
        "input_isolation": "page_images_plus_a_b_only",
        "review_pass": 3,
        "human_verified": False,
        "pages": [
            {
                "page_id": page["page_id"],
                "render_sha256": page["render"]["sha256"],
                "differences": [],
                "decisions": [],
                "final": copy.deepcopy(extractor["pages"][index]),
                "resolved": True,
                "unresolved": [],
            }
            for index, page in enumerate(package["pages"])
        ],
    }


def _consensus_fixture():
    package_path = acceptance.ROOT / "docs/codex/evidence/RAG_R1B_OCR_20260803T140208+0800/package_manifest.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    extractor = _ai_role(
        package,
        origin=acceptance.AI_ROLE_ORIGINS[0],
        isolation="blind_page_images_only",
        review_pass=1,
    )
    reviewer = _ai_role(
        package,
        origin=acceptance.AI_ROLE_ORIGINS[1],
        isolation="blind_page_images_only_no_extractor_access",
        review_pass=2,
    )
    adjudication = _ai_adjudication(package, extractor)
    consensus = acceptance.assemble_ai_consensus(
        extractor,
        reviewer,
        adjudication,
        package,
        extractor_sha256="a" * 64,
        reviewer_sha256="b" * 64,
        adjudication_sha256="c" * 64,
        package_sha256="d" * 64,
        frozen_at="2026-08-04T00:00:00Z",
    )
    return package, extractor, reviewer, adjudication, consensus


def test_ai_consensus_three_roles_build_validate_and_tamper_fail_closed():
    package, _, _, _, consensus = _consensus_fixture()
    report = acceptance.validate_ai_consensus(consensus, package, "d" * 64)
    assert report["status"] == acceptance.AI_CONSENSUS_VERIFIED
    assert report["page_count"] == 30
    assert report["human_verified"] is False
    assert report["automated_consensus_verified"] is True
    assert report["production_human_signoff"] is False
    tampered = copy.deepcopy(consensus)
    tampered["metrics"]["hallucinated_digits"] = 1
    with pytest.raises(acceptance.OCRAcceptanceError, match="metrics_tampered"):
        acceptance.validate_ai_consensus(tampered, package, "d" * 64)


@pytest.mark.parametrize("mutation", ["human", "same_role", "unresolved", "hallucinated", "package"])
def test_ai_consensus_rejects_provenance_and_gate_mutations(mutation):
    package, extractor, reviewer, adjudication, _ = _consensus_fixture()
    if mutation == "human":
        extractor["human_verified"] = True
    elif mutation == "same_role":
        reviewer["origin"] = acceptance.AI_ROLE_ORIGINS[0]
    elif mutation == "unresolved":
        adjudication["pages"][0]["resolved"] = False
        adjudication["pages"][0]["unresolved"] = ["needs review"]
    elif mutation == "hallucinated":
        final = adjudication["pages"][0]["final"]
        final["text"] += " 999"
        next(element for element in final["elements"] if element["text"])["text"] += " 999"
        final["digits"].append("999")
    else:
        package["page_count"] = 29
    with pytest.raises(acceptance.OCRAcceptanceError):
        acceptance.assemble_ai_consensus(
            extractor,
            reviewer,
            adjudication,
            package,
            extractor_sha256="a" * 64,
            reviewer_sha256="b" * 64,
            adjudication_sha256="c" * 64,
            package_sha256="d" * 64,
            frozen_at="2026-08-04T00:00:00Z",
        )


@pytest.mark.parametrize("mutation", ["empty", "text_mismatch", "strata_incomplete"])
def test_ai_consensus_rejects_incomplete_page_truth(mutation):
    package, extractor, reviewer, adjudication, _ = _consensus_fixture()
    if mutation == "empty":
        extractor["pages"][0].update(text="", elements=[], tables=[], digits=[])
    elif mutation == "text_mismatch":
        next(element for element in extractor["pages"][0]["elements"] if element["text"])["text"] += " mismatch"
    else:
        package["pages"][0]["strata"] = list(package["pages"][0]["strata"]) + ["chart"]
    with pytest.raises(acceptance.OCRAcceptanceError):
        acceptance.assemble_ai_consensus(
            extractor,
            reviewer,
            adjudication,
            package,
            extractor_sha256="a" * 64,
            reviewer_sha256="b" * 64,
            adjudication_sha256="c" * 64,
            package_sha256="d" * 64,
            frozen_at="2026-08-04T00:00:00Z",
        )

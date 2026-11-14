"""Text, table and reading-order baseline for a Middle JSON against its source PDF.

The reference is the PDF's own visible text layer, used only on pages that pass
``judge_text_layer``. That makes this a proxy for digital-born PDFs: it measures
how faithfully a pipeline reproduces text that is already there, and it is the
right tool for regression checks and for comparing backends on the same file.
It says nothing about scans, and the reading-order score is agreement with the
PDF content-stream order, which equals reading order only for PDFs authored in
reading order. Hand-labelled truth (tables, order) is accepted and, when given,
is what the TEDS and order scores use.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from aih_contexture.evaluation.metrics import (
    character_bag_scores,
    edit_distance,
    fold_typography,
    normalize_text,
    reading_order_scores,
    table_shape,
    table_teds,
)
from aih_contexture.evaluation.text_layer_truth import (
    LayerChar,
    TextLayerTruth,
    extract_text_layer,
    judge_text_layer,
)
from aih_contexture.middle.storage import decode_middle_storage

# Only these are left out of the reference: their text (chart labels, formula glyphs) is not
# something a plain text transcription is expected to reproduce. Every other block type,
# ComplexRegion included, is scored, so a region that kept layer text but came out empty
# shows up as a miss instead of vanishing from the reference.
NON_TEXT_TYPES = frozenset({"Figure", "Picture", "Equation"})
FURNITURE_TYPES = frozenset({"PageHeader", "PageFooter", "PageNumber"})
TABLE_TYPE = "Table"


def _is_rtl(char: str) -> bool:
    code = ord(char)
    return 0x0590 <= code <= 0x08FF or 0xFB1D <= code <= 0xFDFF or 0xFE70 <= code <= 0xFEFF


def _mostly_rtl(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and sum(_is_rtl(char) for char in letters) / len(letters) > 0.3


def _leaf_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    for block in blocks:
        children = block.get("children")
        if isinstance(children, list) and children:
            leaves.extend(_leaf_blocks(children))
        else:
            leaves.append(block)
    return leaves


def _area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _contains(bbox: list[float], point: tuple[float, float]) -> bool:
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def _assign_chars(truth: TextLayerTruth, blocks: list[dict[str, Any]]) -> dict[int, list[LayerChar]]:
    """Give every layer character to the smallest block containing its centre."""
    ordered = sorted(
        (index for index, block in enumerate(blocks) if block.get("bbox")),
        key=lambda index: _area(blocks[index]["bbox"]),
    )
    owned: dict[int, list[LayerChar]] = defaultdict(list)
    for char in truth.chars:
        for index in ordered:
            if _contains(blocks[index]["bbox"], char.center):
                owned[index].append(char)
                break
    return owned


def _evaluate_page(
    page: dict[str, Any],
    truth: TextLayerTruth,
    *,
    table_truth: dict[str, str],
    order_truth: dict[str, list[str]],
) -> dict[str, Any]:
    blocks = sorted(_leaf_blocks(page.get("blocks") or []), key=lambda item: item.get("order", 0))
    owned = _assign_chars(truth, blocks)
    owned_count = sum(len(chars) for chars in owned.values())

    block_rows: list[dict[str, Any]] = []
    reference_parts: list[str] = []
    hypothesis_parts: list[str] = []
    skipped_types: dict[str, int] = defaultdict(int)
    unowned = len(truth.chars) - owned_count
    reference_chars_in_skipped = 0
    hypothesis_without_reference = 0

    for index, block in enumerate(blocks):
        block_type = str(block.get("type"))
        chars = sorted(owned.get(index, []), key=lambda item: item.seq)
        if block_type in NON_TEXT_TYPES:
            skipped_types[block_type] += 1
            reference_chars_in_skipped += len(chars)
            continue
        reference = "".join(item.char for item in chars)
        hypothesis = str(block.get("text") or "")
        norm_ref, norm_hyp = normalize_text(reference), normalize_text(hypothesis)
        row: dict[str, Any] = {
            "id": block.get("id"),
            "type": block_type,
            "reference_chars": len(norm_ref),
            "hypothesis_chars": len(norm_hyp),
        }
        if norm_ref and block_type == TABLE_TYPE:
            # Cell text follows row order, the layer follows stream order: compare content only.
            row["bag"] = character_bag_scores(reference, hypothesis)
        elif norm_ref and _mostly_rtl(reference):
            # A right-to-left text layer is usually stored in visual order, one glyph form per
            # position, so a sequence comparison would score the reference, not the transcription.
            row["bag"] = character_bag_scores(reference, hypothesis)
            row["rtl_reference_unordered"] = True
        elif norm_ref:
            row["edit_distance"] = edit_distance(norm_ref, norm_hyp)
            row["cer"] = row["edit_distance"] / len(norm_ref)
            row["edit_distance_folded"] = edit_distance(fold_typography(norm_ref), fold_typography(norm_hyp))
        else:
            row["no_reference"] = True
            hypothesis_without_reference += len(norm_hyp)
        block_id = str(block.get("id"))
        attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
        if block_type == TABLE_TYPE:
            html = str(attrs.get("table_html") or "")
            row["has_table_html"] = bool(html)
            row["shape"] = table_shape(html)
            if block_id in table_truth:
                row["teds"] = table_teds(table_truth[block_id], html)
                row["teds_structure_only"] = table_teds(table_truth[block_id], html, structure_only=True)
        if attrs.get("ocr_failure"):
            row["ocr_failure"] = attrs["ocr_failure"]
        block_rows.append(row)
        reference_parts.append(reference)
        hypothesis_parts.append(hypothesis)

    page_bag = character_bag_scores("".join(reference_parts), "".join(hypothesis_parts))

    # Reading order: proxy from the PDF stream unless a hand-labelled order is supplied.
    order_blocks = [
        (block, owned.get(index, []))
        for index, block in enumerate(blocks)
        if block.get("type") not in NON_TEXT_TYPES | FURNITURE_TYPES | {TABLE_TYPE} and owned.get(index)
    ]
    hypothesis_ids = [str(block.get("id")) for block, _ in order_blocks]
    page_key = str(page.get("index"))
    if page_key in order_truth:
        reference_ids = list(order_truth[page_key])
        order_source = "manual"
    else:
        reference_ids = [
            str(block.get("id"))
            for block, chars in sorted(order_blocks, key=lambda pair: median(item.seq for item in pair[1]))
        ]
        order_source = "pdf_stream_proxy"
    order = reading_order_scores(reference_ids, hypothesis_ids)
    order["reference_source"] = order_source

    return {
        "page_index": page.get("index"),
        "trusted": True,
        "content": page_bag,
        "blocks": block_rows,
        "order": order,
        "layer_chars_unowned_by_any_block": unowned,
        "layer_chars_in_skipped_blocks": reference_chars_in_skipped,
        "hypothesis_chars_without_reference": hypothesis_without_reference,
        "skipped_block_types": dict(skipped_types),
    }


def _micro_cer(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if "cer" in row]
    ref = sum(row["reference_chars"] for row in scored)
    dist = sum(row["edit_distance"] for row in scored)
    folded = sum(row["edit_distance_folded"] for row in scored)
    return {
        "blocks": len(scored),
        "reference_chars": ref,
        "edit_distance": dist,
        "cer": (dist / ref) if ref else None,
        "cer_typography_folded": (folded / ref) if ref else None,
    }


def evaluate_text_baseline(
    middle: dict[str, Any],
    pdf_path: str | Path,
    *,
    table_truth: dict[str, str] | None = None,
    order_truth: dict[str, list[str]] | None = None,
    pages: list[int] | None = None,
    allow_embedded_ocr: bool = False,
) -> dict[str, Any]:
    """Score ``middle`` against ``pdf_path``.

    ``allow_embedded_ocr`` also accepts scan pages whose only text is an invisible OCR layer
    as the reference. Their scores are agreement with that layer (``reference_kind``
    ``embedded_ocr_layer``), reported separately from scores against a visible text layer.
    """
    middle = decode_middle_storage(middle)
    table_truth = table_truth or {}
    order_truth = order_truth or {}
    page_reports: list[dict[str, Any]] = []
    for page in middle.get("pages") or []:
        page_index = page.get("index")
        if not isinstance(page_index, int) or (pages is not None and page_index not in pages):
            continue
        truth = extract_text_layer(pdf_path, page_index, include_invisible=allow_embedded_ocr)
        verdict = judge_text_layer(truth, allow_embedded_ocr=allow_embedded_ocr)
        if not verdict["trusted"]:
            page_reports.append(
                {"page_index": page_index, "trusted": False, "reasons": verdict["reasons"], "layer": verdict["stats"]}
            )
            continue
        report = _evaluate_page(page, truth, table_truth=table_truth, order_truth=order_truth)
        report["layer"] = verdict["stats"]
        report["reference_kind"] = verdict["reference_kind"]
        page_reports.append(report)

    trusted = [page for page in page_reports if page["trusted"]]
    all_rows = [row for page in trusted for row in page["blocks"]]
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        by_type[row["type"]].append(row)
    taus = [page["order"]["kendall_tau"] for page in trusted if page["order"]["kendall_tau"] is not None]
    successors = [
        page["order"]["successor_accuracy"] for page in trusted if page["order"]["successor_accuracy"] is not None
    ]
    teds_rows = [row["teds"] for row in all_rows if row.get("teds") is not None]
    ref_total = sum(page["content"]["reference_chars"] for page in trusted)
    overlap_total = sum(page["content"]["overlap_chars"] for page in trusted)
    hyp_total = sum(page["content"]["hypothesis_chars"] for page in trusted)
    untrusted_reasons: dict[str, int] = defaultdict(int)
    for page in page_reports:
        for reason in page.get("reasons", []):
            untrusted_reasons[reason] += 1

    return {
        "source": {
            "pdf": str(pdf_path),
            "middle_backends": middle.get("backends"),
            "reference": sorted({page.get("reference_kind", "visible_text_layer") for page in trusted})
            or ["none"],
            "reference_note": "embedded_ocr_layer scores measure agreement with someone else's OCR, not accuracy",
        },
        "pages": {
            "evaluated": len(page_reports),
            "trusted": len(trusted),
            "untrusted": len(page_reports) - len(trusted),
            "untrusted_reasons": dict(untrusted_reasons),
        },
        "summary": {
            "text_cer_micro": _micro_cer([row for row in all_rows if row["type"] != TABLE_TYPE]),
            "text_cer_by_type": {name: _micro_cer(rows) for name, rows in sorted(by_type.items())},
            "content_recall": (overlap_total / ref_total) if ref_total else None,
            "content_precision": (overlap_total / hyp_total) if hyp_total else None,
            "reading_order": {
                "kendall_tau_mean": (sum(taus) / len(taus)) if taus else None,
                "successor_accuracy_mean": (sum(successors) / len(successors)) if successors else None,
                "pages_scored": len(taus),
                "note": "agreement with PDF content-stream order unless a manual order is supplied",
            },
            "tables": {
                "count": sum(1 for row in all_rows if row["type"] == TABLE_TYPE),
                "with_table_html": sum(1 for row in all_rows if row.get("has_table_html")),
                "teds_mean": (sum(teds_rows) / len(teds_rows)) if teds_rows else None,
                "teds_scored": len(teds_rows),
            },
            "ocr_failures": sum(1 for row in all_rows if row.get("ocr_failure")),
            "hypothesis_chars_without_reference": sum(
                page["hypothesis_chars_without_reference"] for page in trusted
            ),
        },
        "page_reports": page_reports,
    }


def evaluate_text_baseline_files(
    middle_path: str | Path,
    pdf_path: str | Path,
    *,
    truth_path: str | Path | None = None,
    pages: list[int] | None = None,
    allow_embedded_ocr: bool = False,
) -> dict[str, Any]:
    middle = json.loads(Path(middle_path).read_text(encoding="utf-8"))
    truth: dict[str, Any] = {}
    if truth_path:
        truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    return evaluate_text_baseline(
        middle,
        pdf_path,
        table_truth=truth.get("tables"),
        order_truth=truth.get("reading_order"),
        pages=pages,
        allow_embedded_ocr=allow_embedded_ocr,
    )

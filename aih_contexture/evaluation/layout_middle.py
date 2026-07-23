from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aih_contexture.middle.validation import validate_middle_json


def evaluate_middle_layout(
    data: dict[str, Any],
    *,
    source_path: str | None = None,
    required_block_types: list[str] | None = None,
    min_blocks: int = 1,
) -> dict[str, Any]:
    """Evaluate one Contexture Middle JSON layout artifact.

    This is intentionally lightweight: it does not compare against ground truth
    boxes yet. It establishes a stable smoke metric layer for Surya/MinerU/Paddle
    layout outputs before heavier annotated evaluation is introduced.
    """

    required_block_types = required_block_types or []
    report = validate_middle_json(data)
    summary = report.summary
    block_types = dict(summary.get("block_types") or {})

    pages_without_blocks: list[int] = []
    blocks_missing_bbox = 0
    blocks_missing_provenance = 0
    unmapped_complex_regions = 0
    total_blocks = 0
    blocks_with_spans = 0
    total_spans = 0
    spans_missing_bbox = 0
    spans_missing_provenance = 0
    spans_with_provenance = 0
    empty_complex_regions = 0
    small_empty_complex_regions = 0

    pages = data.get("pages") if isinstance(data, dict) else []
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_index = page.get("index")
            blocks = page.get("blocks", [])
            if not isinstance(blocks, list) or not blocks:
                if isinstance(page_index, int):
                    pages_without_blocks.append(page_index)
                continue
            page_area = _page_area(page)
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                total_blocks += 1
                if block.get("bbox") is None and block.get("polygon") is None:
                    blocks_missing_bbox += 1
                if not block.get("provenance"):
                    blocks_missing_provenance += 1
                attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
                if block.get("type") == "ComplexRegion" and attrs.get("unmapped_label"):
                    unmapped_complex_regions += 1
                spans = block.get("spans")
                if block.get("type") == "ComplexRegion" and _is_empty_block(block, spans):
                    empty_complex_regions += 1
                    if _is_small_block(block, page_area):
                        small_empty_complex_regions += 1
                if isinstance(spans, list) and spans:
                    blocks_with_spans += 1
                    for span in spans:
                        if not isinstance(span, dict):
                            continue
                        total_spans += 1
                        if span.get("bbox") is None and span.get("polygon") is None:
                            spans_missing_bbox += 1
                        if span.get("provenance"):
                            spans_with_provenance += 1
                        else:
                            spans_missing_provenance += 1

    missing_required = [
        block_type for block_type in required_block_types
        if int(block_types.get(block_type, 0)) <= 0
    ]
    passed = (
        report.ok
        and total_blocks >= min_blocks
        and not missing_required
    )

    return {
        "source_path": source_path,
        "ok": passed,
        "validation_ok": report.ok,
        "errors": [
            {"path": issue.path, "message": issue.message}
            for issue in report.errors
        ],
        "warnings": [
            {"path": issue.path, "message": issue.message}
            for issue in report.warnings
        ],
        "summary": summary,
        "metrics": {
            "page_count": int(summary.get("page_count", 0)),
            "pages_with_blocks": int(summary.get("pages_with_blocks", 0)),
            "pages_without_blocks": pages_without_blocks,
            "block_count": total_blocks,
            "block_types": block_types,
            "blocks_missing_bbox": blocks_missing_bbox,
            "blocks_missing_provenance": blocks_missing_provenance,
            "unmapped_complex_regions": unmapped_complex_regions,
            "empty_complex_regions": empty_complex_regions,
            "small_empty_complex_regions": small_empty_complex_regions,
            "span_count": total_spans,
            "blocks_with_spans": blocks_with_spans,
            "spans_missing_bbox": spans_missing_bbox,
            "spans_missing_provenance": spans_missing_provenance,
            "span_provenance_completeness": (
                spans_with_provenance / total_spans if total_spans else None
            ),
            "required_block_types": required_block_types,
            "missing_required_block_types": missing_required,
            "min_blocks": min_blocks,
        },
    }


def _page_area(page: dict[str, Any]) -> float | None:
    width = page.get("width")
    height = page.get("height")
    if isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > 0 and height > 0:
        return float(width) * float(height)
    return None


def _is_empty_block(block: dict[str, Any], spans: Any) -> bool:
    if str(block.get("text") or "").strip():
        return False
    if isinstance(spans, list):
        for span in spans:
            if isinstance(span, dict) and str(span.get("text") or "").strip():
                return False
    return True


def _is_small_block(block: dict[str, Any], page_area: float | None) -> bool:
    bbox = block.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4 or page_area is None:
        return False
    if not all(isinstance(value, (int, float)) for value in bbox):
        return False
    width = max(0.0, float(bbox[2]) - float(bbox[0]))
    height = max(0.0, float(bbox[3]) - float(bbox[1]))
    return page_area > 0 and (width * height / page_area) <= 0.01


def evaluate_middle_layout_files(
    paths: list[str | Path],
    *,
    required_block_types: list[str] | None = None,
    min_blocks: int = 1,
) -> dict[str, Any]:
    results = []
    for path in paths:
        json_path = Path(path)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        results.append(
            evaluate_middle_layout(
                data,
                source_path=str(json_path),
                required_block_types=required_block_types,
                min_blocks=min_blocks,
            )
        )

    return {
        "ok": all(result["ok"] for result in results),
        "case_count": len(results),
        "results": results,
    }


def evaluate_middle_layout_manifest(manifest: dict[str, Any], *, base_dir: str | Path | None = None) -> dict[str, Any]:
    base_path = Path(base_dir) if base_dir is not None else None
    cases = manifest.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("Layout evaluation manifest must contain a 'cases' list.")

    results = []
    for case_pos, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"Layout evaluation case {case_pos} must be an object.")
        raw_path = case.get("path")
        if not raw_path:
            raise ValueError(f"Layout evaluation case {case_pos} is missing 'path'.")
        path = Path(str(raw_path))
        if not path.is_absolute() and base_path is not None:
            path = base_path / path

        required_block_types = case.get("required_block_types") or manifest.get("required_block_types") or []
        if not isinstance(required_block_types, list):
            raise ValueError(f"Layout evaluation case {case_pos} required_block_types must be a list.")

        min_blocks = int(case.get("min_blocks", manifest.get("min_blocks", 1)))
        data = json.loads(path.read_text(encoding="utf-8"))
        result = evaluate_middle_layout(
            data,
            source_path=str(path),
            required_block_types=[str(item) for item in required_block_types],
            min_blocks=min_blocks,
        )
        result["case"] = {
            "id": case.get("id") or path.stem,
            "backend": case.get("backend"),
            "document_type": case.get("document_type"),
            "source_pdf": case.get("source_pdf"),
            "page_range": case.get("page_range"),
            "notes": case.get("notes"),
        }
        results.append(result)

    return {
        "ok": all(result["ok"] for result in results),
        "manifest": {
            "name": manifest.get("name"),
            "version": manifest.get("version"),
        },
        "case_count": len(results),
        "results": results,
    }

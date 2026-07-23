from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aih_contexture.evaluation.layout_overlay import render_middle_review_crops_file


def compare_layout_eval_reports(report_paths: list[str | Path]) -> dict[str, Any]:
    reports = [_load_report(path) for path in report_paths]
    rows = []
    for report in reports:
        report_path = report["path"]
        for result in report["payload"].get("results") or []:
            if not isinstance(result, dict):
                continue
            summary = result.get("summary") or {}
            metrics = result.get("metrics") or {}
            case = result.get("case") or {}
            source_pdf = case.get("source_pdf") or summary.get("source_name") or result.get("source_path")
            page_range = _normalize_page_range(case.get("page_range"))
            rows.append(
                {
                    "report": str(report_path),
                    "source_path": result.get("source_path"),
                    "case_id": case.get("id"),
                    "backend": case.get("backend") or (summary.get("backends") or {}).get("layout"),
                    "source_pdf": source_pdf,
                    "source_name": _source_name(source_pdf),
                    "page_range": page_range,
                    "group_key": _group_key(source_pdf, page_range, case.get("id")),
                    "ok": bool(result.get("ok", False)),
                    "validation_ok": bool(result.get("validation_ok", False)),
                    "page_count": int(metrics.get("page_count", summary.get("page_count", 0)) or 0),
                    "block_count": int(metrics.get("block_count", summary.get("block_count", 0)) or 0),
                    "pages_without_blocks": metrics.get("pages_without_blocks") or [],
                    "blocks_missing_bbox": int(metrics.get("blocks_missing_bbox", 0) or 0),
                    "blocks_missing_provenance": int(metrics.get("blocks_missing_provenance", 0) or 0),
                    "unmapped_complex_regions": int(metrics.get("unmapped_complex_regions", 0) or 0),
                    "empty_complex_regions": int(metrics.get("empty_complex_regions", 0) or 0),
                    "small_empty_complex_regions": int(metrics.get("small_empty_complex_regions", 0) or 0),
                    "span_count": int(metrics.get("span_count", 0) or 0),
                    "blocks_with_spans": int(metrics.get("blocks_with_spans", 0) or 0),
                    "spans_missing_bbox": int(metrics.get("spans_missing_bbox", 0) or 0),
                    "spans_missing_provenance": int(metrics.get("spans_missing_provenance", 0) or 0),
                    "span_provenance_completeness": metrics.get("span_provenance_completeness"),
                    "block_types": metrics.get("block_types") or summary.get("block_types") or {},
                    "warnings": len(result.get("warnings") or []),
                    "errors": len(result.get("errors") or []),
                }
            )
    groups = _group_rows(rows)
    quality_summary = _build_quality_summary(rows)
    return {
        "ok": all(row["ok"] for row in rows) if rows else False,
        "report_count": len(reports),
        "case_count": len(rows),
        "group_count": len(groups),
        "quality_summary": quality_summary,
        "rows": rows,
        "groups": groups,
    }


def render_layout_comparison_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Contexture Layout Comparison",
        "",
        f"- Reports: {payload.get('report_count', 0)}",
        f"- Cases: {payload.get('case_count', 0)}",
        f"- Groups: {payload.get('group_count', 0)}",
        f"- Overall OK: {payload.get('ok')}",
        "",
        "| Backend | Case | OK | Pages | Blocks | Spans | Blocks with spans | Missing block bbox | Missing span bbox | Missing block provenance | Missing span provenance | Span provenance | Types |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload.get("rows") or []:
        types = ", ".join(f"{key}:{value}" for key, value in sorted((row.get("block_types") or {}).items()))
        lines.append(
            "| {backend} | {case_id} | {ok} | {page_count} | {block_count} | {span_count} | {blocks_with_spans} | {blocks_missing_bbox} | {spans_missing_bbox} | {blocks_missing_provenance} | {spans_missing_provenance} | {span_provenance_completeness} | {types} |".format(
                backend=_cell(row.get("backend")),
                case_id=_cell(row.get("case_id")),
                ok="yes" if row.get("ok") else "no",
                page_count=row.get("page_count", 0),
                block_count=row.get("block_count", 0),
                span_count=row.get("span_count", 0),
                blocks_with_spans=row.get("blocks_with_spans", 0),
                blocks_missing_bbox=row.get("blocks_missing_bbox", 0),
                spans_missing_bbox=row.get("spans_missing_bbox", 0),
                blocks_missing_provenance=row.get("blocks_missing_provenance", 0),
                spans_missing_provenance=row.get("spans_missing_provenance", 0),
                span_provenance_completeness=_format_ratio(row.get("span_provenance_completeness")),
                types=_cell(types),
            )
        )
    lines.extend(_render_quality_summary(payload.get("quality_summary") or {}))
    lines.extend(_render_grouped_tables(payload.get("groups") or []))
    lines.append("")
    return "\n".join(lines)


def write_layout_comparison_review_crops(
    payload: dict[str, Any],
    output_dir: str | Path,
    *,
    target: str = "small_empty_complex",
    dpi: int = 144,
    padding: int = 24,
) -> dict[str, Any]:
    """Write review crops for comparison rows that carry review flags."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []

    for row in payload.get("rows") or []:
        if not isinstance(row, dict) or not _row_matches_crop_target(row, target=target):
            continue
        source_path = row.get("source_path")
        if not source_path:
            cases.append({"ok": False, "case_id": row.get("case_id"), "error": "missing_source_path"})
            continue
        middle_path = Path(str(source_path))
        if not middle_path.exists():
            cases.append(
                {
                    "ok": False,
                    "case_id": row.get("case_id"),
                    "source_path": str(middle_path),
                    "error": "source_path_not_found",
                }
            )
            continue
        case_dir = output_path / _safe_name(row.get("backend")) / _safe_name(row.get("case_id"))
        crop_report = render_middle_review_crops_file(
            middle_path,
            source_pdf=row.get("source_pdf"),
            output_dir=case_dir,
            dpi=dpi,
            padding=padding,
            target=target,
        )
        cases.append(
            {
                "ok": True,
                "case_id": row.get("case_id"),
                "backend": row.get("backend"),
                "source_path": str(middle_path),
                "output_dir": str(case_dir),
                "crop_count": crop_report.get("crop_count", 0),
                "manifest": crop_report.get("manifest"),
            }
        )

    manifest_path = output_path / "layout_review_crops.json"
    report = {
        "ok": all(case.get("ok") for case in cases) if cases else True,
        "target": target,
        "case_count": len(cases),
        "crop_count": sum(int(case.get("crop_count", 0) or 0) for case in cases),
        "cases": cases,
        "manifest": str(manifest_path),
    }
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _load_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    return {
        "path": report_path,
        "payload": json.loads(report_path.read_text(encoding="utf-8")),
    }


def _cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|")


def _format_ratio(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _normalize_page_range(value: Any) -> list[int] | None:
    if value is None:
        return None
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        pages: list[int] = []
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                pages.extend(range(int(start), int(end) + 1))
            else:
                pages.append(int(part))
        return sorted(set(pages))
    if isinstance(value, list):
        pages = []
        for item in value:
            if isinstance(item, int):
                pages.append(item)
        return sorted(set(pages))
    return None


def _source_name(value: Any) -> str:
    if value is None:
        return ""
    return Path(str(value)).name


def _group_key(source_pdf: Any, page_range: list[int] | None, case_id: Any) -> str:
    if source_pdf and page_range is not None:
        pages = ",".join(str(page) for page in page_range)
        return f"{_source_name(source_pdf)}#pages={pages}"
    return str(case_id or source_pdf or "")


def _group_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("group_key") or "")
        group = grouped.setdefault(
            key,
            {
                "key": key,
                "source_name": row.get("source_name"),
                "source_pdf": row.get("source_pdf"),
                "page_range": row.get("page_range"),
                "rows": [],
            },
        )
        group["rows"].append(row)
    return sorted(grouped.values(), key=lambda group: str(group.get("key") or ""))


def _render_grouped_tables(groups: list[dict[str, Any]]) -> list[str]:
    if not groups:
        return []
    lines = [
        "",
        "## Grouped By Source/Page",
        "",
    ]
    rendered_any = False
    for group in groups:
        rows = group.get("rows") or []
        if len(rows) < 2:
            continue
        rendered_any = True
        page_range = group.get("page_range")
        pages = ",".join(str(page) for page in page_range) if page_range else ""
        lines.extend(
            [
                f"### {_cell(group.get('source_name'))} {f'pages {pages}' if pages else ''}".rstrip(),
                "",
                "| Backend | Case | OK | Blocks | Spans | Missing bbox | Missing provenance | Review flags | Types |",
                "|---|---|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for row in rows:
            types = ", ".join(f"{key}:{value}" for key, value in sorted((row.get("block_types") or {}).items()))
            missing_bbox = int(row.get("blocks_missing_bbox", 0) or 0) + int(row.get("spans_missing_bbox", 0) or 0)
            missing_provenance = int(row.get("blocks_missing_provenance", 0) or 0) + int(row.get("spans_missing_provenance", 0) or 0)
            lines.append(
                "| {backend} | {case_id} | {ok} | {block_count} | {span_count} | {missing_bbox} | {missing_provenance} | {review_flags} | {types} |".format(
                    backend=_cell(row.get("backend")),
                    case_id=_cell(row.get("case_id")),
                    ok="yes" if row.get("ok") else "no",
                    block_count=row.get("block_count", 0),
                    span_count=row.get("span_count", 0),
                    missing_bbox=missing_bbox,
                    missing_provenance=missing_provenance,
                    review_flags=_cell(_review_flags(row)),
                    types=_cell(types),
                )
            )
        lines.append("")
    if not rendered_any:
        return []
    return lines


def _review_flags(row: dict[str, Any]) -> str:
    flags = []
    if int(row.get("unmapped_complex_regions", 0) or 0):
        flags.append(f"unmapped_complex:{row['unmapped_complex_regions']}")
    if int(row.get("empty_complex_regions", 0) or 0):
        flags.append(f"empty_complex:{row['empty_complex_regions']}")
    if int(row.get("small_empty_complex_regions", 0) or 0):
        flags.append(f"small_empty_complex:{row['small_empty_complex_regions']}")
    return ", ".join(flags)


def _row_matches_crop_target(row: dict[str, Any], *, target: str) -> bool:
    if target == "all":
        return bool(_review_flags(row))
    if target == "complex":
        return int(row.get("unmapped_complex_regions", 0) or 0) > 0 or int(row.get("empty_complex_regions", 0) or 0) > 0
    if target == "empty_complex":
        return int(row.get("empty_complex_regions", 0) or 0) > 0
    if target == "small_empty_complex":
        return int(row.get("small_empty_complex_regions", 0) or 0) > 0
    return False


def _safe_name(value: Any) -> str:
    text = str(value or "unknown")
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in text)
    return safe or "unknown"


def _build_quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_backend: dict[str, dict[str, Any]] = {}
    review_items = []
    for row in rows:
        backend = str(row.get("backend") or "")
        summary = by_backend.setdefault(
            backend,
            {
                "backend": backend,
                "case_count": 0,
                "failed_cases": 0,
                "missing_bbox": 0,
                "missing_provenance": 0,
                "unmapped_complex_regions": 0,
                "empty_complex_regions": 0,
                "small_empty_complex_regions": 0,
                "review_flag_count": 0,
            },
        )
        summary["case_count"] += 1
        if not row.get("ok"):
            summary["failed_cases"] += 1
        summary["missing_bbox"] += int(row.get("blocks_missing_bbox", 0) or 0)
        summary["missing_bbox"] += int(row.get("spans_missing_bbox", 0) or 0)
        summary["missing_provenance"] += int(row.get("blocks_missing_provenance", 0) or 0)
        summary["missing_provenance"] += int(row.get("spans_missing_provenance", 0) or 0)
        summary["unmapped_complex_regions"] += int(row.get("unmapped_complex_regions", 0) or 0)
        summary["empty_complex_regions"] += int(row.get("empty_complex_regions", 0) or 0)
        summary["small_empty_complex_regions"] += int(row.get("small_empty_complex_regions", 0) or 0)
        flags = _review_flags(row)
        if flags:
            summary["review_flag_count"] += 1
            review_items.append(
                {
                    "backend": backend,
                    "case_id": row.get("case_id"),
                    "source_name": row.get("source_name"),
                    "page_range": row.get("page_range"),
                    "flags": flags,
                }
            )
    return {
        "by_backend": sorted(by_backend.values(), key=lambda item: item["backend"]),
        "review_items": review_items,
    }


def _render_quality_summary(summary: dict[str, Any]) -> list[str]:
    by_backend = summary.get("by_backend") or []
    if not by_backend:
        return []
    lines = [
        "",
        "## Quality Summary",
        "",
        "| Backend | Cases | Failed | Missing bbox | Missing provenance | Review cases | Empty complex | Small empty complex |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in by_backend:
        lines.append(
            "| {backend} | {case_count} | {failed_cases} | {missing_bbox} | {missing_provenance} | {review_flag_count} | {empty_complex_regions} | {small_empty_complex_regions} |".format(
                backend=_cell(item.get("backend")),
                case_count=item.get("case_count", 0),
                failed_cases=item.get("failed_cases", 0),
                missing_bbox=item.get("missing_bbox", 0),
                missing_provenance=item.get("missing_provenance", 0),
                review_flag_count=item.get("review_flag_count", 0),
                empty_complex_regions=item.get("empty_complex_regions", 0),
                small_empty_complex_regions=item.get("small_empty_complex_regions", 0),
            )
        )
    review_items = summary.get("review_items") or []
    if review_items:
        lines.extend(
            [
                "",
                "### Review Items",
                "",
                "| Backend | Case | Source | Pages | Flags |",
                "|---|---|---|---|---|",
            ]
        )
        for item in review_items:
            page_range = item.get("page_range")
            pages = ",".join(str(page) for page in page_range) if page_range else ""
            lines.append(
                "| {backend} | {case_id} | {source_name} | {pages} | {flags} |".format(
                    backend=_cell(item.get("backend")),
                    case_id=_cell(item.get("case_id")),
                    source_name=_cell(item.get("source_name")),
                    pages=_cell(pages),
                    flags=_cell(item.get("flags")),
                )
            )
    return lines

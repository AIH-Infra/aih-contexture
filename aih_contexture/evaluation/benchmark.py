"""Page-sampled benchmark: build sample PDFs from a manifest, run backends, score, summarise.

A manifest entry names a source PDF, 0-based pages and a category. The source PDFs are the
user's library and are only ever read; the sampled pages are copied into a work directory
that is not under version control. Scores come from ``text_baseline`` and therefore carry its
reference caveats: each entry says which reference it may use (``visible`` text layer, an
``embedded_ocr`` layer as agreement-only, or ``none``).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from aih_contexture.evaluation.text_baseline import evaluate_text_baseline

REFERENCE_MODES = ("visible", "embedded_ocr", "none")


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    seen: set[str] = set()
    for entry in manifest["entries"]:
        if entry["id"] in seen:
            raise ValueError(f"duplicate entry id: {entry['id']}")
        seen.add(entry["id"])
        if entry.get("reference", "visible") not in REFERENCE_MODES:
            raise ValueError(f"{entry['id']}: reference must be one of {REFERENCE_MODES}")
        if not entry.get("pages"):
            raise ValueError(f"{entry['id']}: no pages")
    return manifest


def build_sample(entry: dict[str, Any], out_dir: str | Path) -> Path:
    """Copy the entry's pages, in order, into ``<out_dir>/<id>.pdf``. Sample page i is entry pages[i]."""
    import pymupdf

    target = Path(out_dir) / f"{entry['id']}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    with pymupdf.open(entry["source"]) as source, pymupdf.open() as sample:
        for page_index in entry["pages"]:
            sample.insert_pdf(source, from_page=page_index, to_page=page_index)
        sample.save(str(target), garbage=3, deflate=True)
    return target


def run_backend(sample_pdf: Path, backend: dict[str, Any], out_dir: Path, *, timeout: int = 1800) -> dict[str, Any]:
    """Convert one sample with one backend config in a subprocess; return paths and wall time."""
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("*/*_middle.json"))
    if existing:
        return {"middle": existing[-1], "seconds": backend_seconds(out_dir), "cached": True}
    code = "from aih_contexture.scripts.convert_single import convert_single_cli; convert_single_cli()"
    command = [
        sys.executable, "-X", "utf8", "-c", code,
        str(sample_pdf), *backend["args"], "--output_format", "json", "--output_dir", str(out_dir),
    ]
    started = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    seconds = time.perf_counter() - started
    (out_dir / "run.log").write_text((completed.stdout or "") + "\n" + (completed.stderr or ""), encoding="utf-8")
    (out_dir / "seconds.txt").write_text(f"{seconds:.2f}", encoding="utf-8")
    middles = sorted(out_dir.glob("*/*_middle.json"))
    return {
        "middle": middles[-1] if middles else None,
        "seconds": seconds,
        "returncode": completed.returncode,
        "cached": False,
    }


def backend_seconds(out_dir: Path) -> float | None:
    marker = out_dir / "seconds.txt"
    return float(marker.read_text(encoding="utf-8")) if marker.exists() else None


def _repeated_halves(text: str, threshold: float = 0.85) -> bool:
    """True when the first and second half of a page's output text are near-identical."""
    from aih_contexture.evaluation.metrics import edit_distance, normalize_text

    normalized = normalize_text(text)
    if len(normalized) < 200:
        return False
    half = len(normalized) // 2
    first, second = normalized[:half], normalized[half : 2 * half]
    return 1.0 - edit_distance(first, second) / len(first) >= threshold


def score_entry(entry: dict[str, Any], sample_pdf: Path, middle_path: Path | None) -> dict[str, Any]:
    if middle_path is None:
        return {"status": "no_output"}
    mode = entry.get("reference", "visible")
    if mode == "none":
        from aih_contexture.evaluation.metrics import normalize_text
        from aih_contexture.evaluation.text_layer_truth import extract_text_layer

        middle = json.loads(Path(middle_path).read_text(encoding="utf-8"))
        pages = middle.get("pages", [])
        chars = sum(len(normalize_text(block.get("text"))) for page in pages for block in page.get("blocks", []))
        visible = sum(
            len(normalize_text(extract_text_layer(sample_pdf, page["index"]).text)) for page in pages
        )
        # About 1.0 when the output carries each visible character once, about 2.0 when a hidden
        # layer was emitted next to the visible one. None when the sample has no visible text.
        # Only meaningful when the visible layer is the page's real text: on a scan whose visible
        # text is a watermark the ratio is large for a correct output.
        ratio = chars / visible if visible else None
        repeated_pages = [
            _repeated_halves(" ".join(str(block.get("text") or "") for block in page.get("blocks", [])))
            for page in pages
        ]
        return {
            "status": "no_reference",
            "output_chars": chars,
            "visible_layer_chars": visible,
            "output_to_visible_ratio": ratio,
            "pages": len(pages),
            "pages_with_repeated_halves": sum(1 for value in repeated_pages if value),
        }
    middle = json.loads(Path(middle_path).read_text(encoding="utf-8"))
    report = evaluate_text_baseline(middle, sample_pdf, allow_embedded_ocr=(mode == "embedded_ocr"))
    summary = report["summary"]
    return {
        "status": "scored" if report["pages"]["trusted"] else "reference_untrusted",
        "pages": report["pages"],
        "reference": report["source"]["reference"],
        "cer": summary["text_cer_micro"]["cer"],
        "cer_folded": summary["text_cer_micro"]["cer_typography_folded"],
        "reference_chars": summary["text_cer_micro"]["reference_chars"],
        "content_recall": summary["content_recall"],
        "content_reference_chars": sum(
            page["content"]["reference_chars"] for page in report["page_reports"] if page.get("trusted")
        ),
        "content_precision": summary["content_precision"],
        "kendall_tau": summary["reading_order"]["kendall_tau_mean"],
        "ocr_failures": summary["ocr_failures"],
        "tables": summary["tables"],
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Micro-average per (category, backend) over scored entries; counts for the rest."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["category"], row["backend"])].append(row)
    table = []
    for (category, backend), items in sorted(groups.items()):
        scored = [item for item in items if item["score"].get("status") == "scored"]
        chars = sum(item["score"]["reference_chars"] or 0 for item in scored)
        errors = sum((item["score"]["cer"] or 0) * (item["score"]["reference_chars"] or 0) for item in scored)
        folded = sum((item["score"]["cer_folded"] or 0) * (item["score"]["reference_chars"] or 0) for item in scored)
        content_chars = sum(item["score"].get("content_reference_chars") or 0 for item in scored)
        recall = sum(
            (item["score"]["content_recall"] or 0) * (item["score"].get("content_reference_chars") or 0)
            for item in scored
        )
        pages = sum(len(item["pages"]) for item in items)
        seconds = sum(item["seconds"] or 0 for item in items)
        table.append(
            {
                "category": category,
                "backend": backend,
                "entries": len(items),
                "scored": len(scored),
                "untrusted_or_unscored": len(items) - len(scored),
                "pages": pages,
                "reference_chars": chars,
                "cer": errors / chars if chars else None,
                "cer_folded": folded / chars if chars else None,
                "content_recall": recall / content_chars if content_chars else None,
                "pages_with_repeated_halves": sum(
                    item["score"].get("pages_with_repeated_halves") or 0 for item in items
                ),
                "ocr_failures": sum(item["score"].get("ocr_failures") or 0 for item in scored),
                "seconds_per_page": seconds / pages if pages else None,
                "reference_kinds": sorted({kind for item in scored for kind in item["score"]["reference"]}),
            }
        )
    return {"groups": table}


def render_markdown(summary: dict[str, Any]) -> str:
    def pct(value: float | None) -> str:
        return "-" if value is None else f"{value * 100:.2f}%"

    lines = [
        "| 类别 | 后端 | 样本(已打分/总) | 页数 | 参考字符 | 严格 CER | 折叠 CER | 内容召回 | 输出自我重复页 | OCR 失败块 | 秒/页 | 参考类型 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in summary["groups"]:
        seconds = "-" if row["seconds_per_page"] is None else f"{row['seconds_per_page']:.1f}"
        lines.append(
            f"| {row['category']} | {row['backend']} | {row['scored']}/{row['entries']} | {row['pages']} | "
            f"{row['reference_chars']} | {pct(row['cer'])} | {pct(row['cer_folded'])} | "
            f"{pct(row['content_recall'])} | {row['pages_with_repeated_halves']} | "
            f"{row['ocr_failures']} | {seconds} | {', '.join(row['reference_kinds']) or '-'} |"
        )
    return "\n".join(lines)

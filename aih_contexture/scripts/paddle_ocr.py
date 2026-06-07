from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import click
import pypdfium2 as pdfium
from PIL import Image

from aih_contexture.backends.ocr.paddle_runtime import PaddleOcrRuntime
from aih_contexture.middle.adapters.external_ocr import merge_external_ocr_into_middle_document
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.validation import validate_middle_json


@click.command(help="Run optional PaddleOCR OCR runtime and write raw OCR JSON, optionally merged into Middle JSON.")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--output-json", type=click.Path(dir_okay=False), required=True, help="Raw OCR JSON output path.")
@click.option("--middle-json", type=click.Path(exists=True, dir_okay=False), help="Optional existing Contexture Middle JSON to merge OCR spans into.")
@click.option("--merged-output", type=click.Path(dir_okay=False), help="Optional output Middle JSON path after OCR merge.")
@click.option("--report", type=click.Path(dir_okay=False), help="Optional validation/import report for merged Middle JSON.")
@click.option("--debug-markdown", type=click.Path(dir_okay=False), help="Optional debug Markdown preview for merged Middle JSON.")
@click.option("--page", "pages", multiple=True, type=int, help="PDF page index to OCR. Can be repeated. Defaults to all pages.")
@click.option("--dpi", default=192, show_default=True, type=int, help="PDF render DPI.")
@click.option("--lang", default="ch", show_default=True, help="PaddleOCR language.")
@click.option("--ocr-version", default="PP-OCRv5", show_default=True, help="PaddleOCR OCR version.")
@click.option("--device", default=None, help="Paddle device, e.g. cpu, gpu:0.")
@click.option("--engine", default=None, help="Paddle inference engine.")
@click.option("--enable-mkldnn/--no-enable-mkldnn", default=False, show_default=True, help="Enable MKL-DNN for PaddleOCR.")
@click.option("--cpu-threads", default=None, type=int, help="PaddleOCR CPU thread count.")
@click.option("--use-doc-orientation-classify/--no-use-doc-orientation-classify", default=False, show_default=True, help="Enable PaddleOCR document orientation classifier.")
@click.option("--use-doc-unwarping/--no-use-doc-unwarping", default=False, show_default=True, help="Enable PaddleOCR document unwarping.")
@click.option("--use-textline-orientation/--no-use-textline-orientation", default=False, show_default=True, help="Enable PaddleOCR text-line orientation classifier.")
def paddle_ocr_cli(
    input_path: str,
    output_json: str,
    middle_json: str | None,
    merged_output: str | None,
    report: str | None,
    debug_markdown: str | None,
    pages: tuple[int, ...],
    dpi: int,
    lang: str,
    ocr_version: str,
    device: str | None,
    engine: str | None,
    enable_mkldnn: bool,
    cpu_threads: int | None,
    use_doc_orientation_classify: bool,
    use_doc_unwarping: bool,
    use_textline_orientation: bool,
):
    input_file = Path(input_path)
    config = {
        "paddle_ocr_lang": lang,
        "paddle_ocr_version": ocr_version,
        "paddle_ocr_device": device,
        "paddle_ocr_engine": engine,
        "paddle_ocr_enable_mkldnn": enable_mkldnn,
        "paddle_ocr_cpu_threads": cpu_threads,
        "paddle_ocr_use_doc_orientation_classify": use_doc_orientation_classify,
        "paddle_ocr_use_doc_unwarping": use_doc_unwarping,
        "paddle_ocr_use_textline_orientation": use_textline_orientation,
    }

    with tempfile.TemporaryDirectory(prefix="contexture-paddle-ocr-") as temp_dir:
        image_paths, page_sizes = _input_to_images(input_file, pages=pages, dpi=dpi, output_dir=Path(temp_dir))
        raw_payload = PaddleOcrRuntime(config).run(image_paths, page_sizes=page_sizes)

    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    click.echo(json.dumps({"ok": True, "page_count": len(raw_payload), "output_json": str(output_path)}, ensure_ascii=False, indent=2))

    if middle_json:
        middle_path = Path(middle_json)
        merged_path = Path(merged_output) if merged_output else middle_path.with_name(f"{middle_path.stem}_with_paddle_ocr.json")
        middle_payload = json.loads(middle_path.read_text(encoding="utf-8"))
        merged = merge_external_ocr_into_middle_document(
            middle_payload,
            raw_payload,
            backend="paddle_ocr_v5",
            model=ocr_version,
            source=str(output_path),
        )
        validation = validate_middle_json(merged)
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        merged_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        report_data = {
            "ok": validation.ok,
            "summary": validation.summary,
            "errors": [asdict(issue) for issue in validation.errors],
            "warnings": [asdict(issue) for issue in validation.warnings],
            "ocr_import": merged.get("metadata", {}).get("ocr_import"),
        }
        if report:
            report_path = Path(report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
        if debug_markdown:
            debug_path = Path(debug_markdown)
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(render_middle_debug_markdown(merged), encoding="utf-8")
        click.echo(json.dumps({"merged_output": str(merged_path), "validation": report_data}, ensure_ascii=False, indent=2))


def _input_to_images(
    input_path: Path,
    *,
    pages: tuple[int, ...],
    dpi: int,
    output_dir: Path,
) -> tuple[list[Path], list[tuple[int, int]]]:
    if input_path.suffix.lower() == ".pdf":
        return _render_pdf(input_path, pages=pages, dpi=dpi, output_dir=output_dir)
    image = Image.open(input_path)
    return [input_path], [(int(image.size[0]), int(image.size[1]))]


def _render_pdf(
    pdf_path: Path,
    *,
    pages: tuple[int, ...],
    dpi: int,
    output_dir: Path,
) -> tuple[list[Path], list[tuple[int, int]]]:
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        page_indices = list(pages) if pages else list(range(len(doc)))
        image_paths: list[Path] = []
        page_sizes: list[tuple[int, int]] = []
        for page_index in page_indices:
            page = doc[page_index]
            image = page.render(scale=dpi / 72, draw_annots=False).to_pil().convert("RGB")
            image_path = output_dir / f"page_{page_index:06d}.png"
            image.save(image_path)
            image_paths.append(image_path)
            page_sizes.append((int(image.size[0]), int(image.size[1])))
        return image_paths, page_sizes
    finally:
        doc.close()


if __name__ == "__main__":
    paddle_ocr_cli()

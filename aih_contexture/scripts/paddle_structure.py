from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from aih_contexture.backends.document.paddle_structure_runtime import PaddleStructureV3Runtime
from aih_contexture.middle.adapters.external_document import external_document_to_middle_document
from aih_contexture.middle.debug_markdown import render_middle_debug_markdown
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.validation import validate_middle_json


@click.command(help="Run optional PaddleOCR PP-StructureV3 and import its raw JSON into Contexture Middle.")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--output-json", type=click.Path(dir_okay=False), required=True, help="Raw PP-StructureV3 JSON output path.")
@click.option("--middle-output", type=click.Path(dir_okay=False), help="Optional Contexture Middle JSON output path.")
@click.option("--report", type=click.Path(dir_okay=False), help="Optional validation/import report path.")
@click.option("--debug-markdown", type=click.Path(dir_okay=False), help="Optional debug Markdown preview path.")
@click.option("--scholarly-markdown", type=click.Path(dir_okay=False), help="Optional normalized scholarly Markdown output path.")
@click.option("--include-provenance-comments", is_flag=True, help="Include block provenance comments in scholarly Markdown.")
@click.option("--lang", default="ch", show_default=True, help="PP-StructureV3 OCR language.")
@click.option("--ocr-version", default="PP-OCRv5", show_default=True, help="PP-StructureV3 OCR version.")
@click.option("--device", default=None, help="Paddle device, e.g. cpu, gpu:0.")
@click.option("--engine", default=None, help="Paddle inference engine.")
@click.option("--paddlex-config", default=None, type=click.Path(dir_okay=False), help="Optional PaddleX pipeline YAML config.")
@click.option("--layout-model", default=None, help="Layout detection model name.")
@click.option("--layout-model-dir", default=None, type=click.Path(file_okay=False), help="Layout detection model directory.")
@click.option("--text-detection-model", default=None, help="Text detection model name.")
@click.option("--text-detection-model-dir", default=None, type=click.Path(file_okay=False), help="Text detection model directory.")
@click.option("--text-recognition-model", default=None, help="Text recognition model name.")
@click.option("--text-recognition-model-dir", default=None, type=click.Path(file_okay=False), help="Text recognition model directory.")
@click.option("--use-doc-orientation-classify/--no-use-doc-orientation-classify", default=False, show_default=True)
@click.option("--use-doc-unwarping/--no-use-doc-unwarping", default=False, show_default=True)
@click.option("--use-textline-orientation/--no-use-textline-orientation", default=False, show_default=True)
@click.option("--use-table-recognition/--no-use-table-recognition", default=True, show_default=True)
@click.option("--use-formula-recognition/--no-use-formula-recognition", default=True, show_default=True)
@click.option("--use-chart-recognition/--no-use-chart-recognition", default=True, show_default=True)
@click.option("--use-region-detection/--no-use-region-detection", default=True, show_default=True)
@click.option("--use-seal-recognition/--no-use-seal-recognition", default=False, show_default=True)
@click.option("--format-block-content/--no-format-block-content", default=False, show_default=True)
@click.option("--unmatched-policy", type=click.Choice(["append_text_blocks", "drop"]), default="append_text_blocks", show_default=True)
@click.option("--min-containment", default=0.20, show_default=True, type=float)
def paddle_structure_cli(
    input_path: str,
    output_json: str,
    middle_output: str | None,
    report: str | None,
    debug_markdown: str | None,
    scholarly_markdown: str | None,
    include_provenance_comments: bool,
    lang: str,
    ocr_version: str,
    device: str | None,
    engine: str | None,
    paddlex_config: str | None,
    layout_model: str | None,
    layout_model_dir: str | None,
    text_detection_model: str | None,
    text_detection_model_dir: str | None,
    text_recognition_model: str | None,
    text_recognition_model_dir: str | None,
    use_doc_orientation_classify: bool,
    use_doc_unwarping: bool,
    use_textline_orientation: bool,
    use_table_recognition: bool,
    use_formula_recognition: bool,
    use_chart_recognition: bool,
    use_region_detection: bool,
    use_seal_recognition: bool,
    format_block_content: bool,
    unmatched_policy: str,
    min_containment: float,
):
    input_file = Path(input_path)
    config = {
        "paddle_structure_lang": lang,
        "paddle_structure_ocr_version": ocr_version,
        "paddle_structure_device": device,
        "paddle_structure_engine": engine,
        "paddle_structure_paddlex_config": paddlex_config,
        "paddle_structure_layout_detection_model_name": layout_model,
        "paddle_structure_layout_detection_model_dir": layout_model_dir,
        "paddle_structure_text_detection_model_name": text_detection_model,
        "paddle_structure_text_detection_model_dir": text_detection_model_dir,
        "paddle_structure_text_recognition_model_name": text_recognition_model,
        "paddle_structure_text_recognition_model_dir": text_recognition_model_dir,
        "paddle_structure_use_doc_orientation_classify": use_doc_orientation_classify,
        "paddle_structure_use_doc_unwarping": use_doc_unwarping,
        "paddle_structure_use_textline_orientation": use_textline_orientation,
        "paddle_structure_use_table_recognition": use_table_recognition,
        "paddle_structure_use_formula_recognition": use_formula_recognition,
        "paddle_structure_use_chart_recognition": use_chart_recognition,
        "paddle_structure_use_region_detection": use_region_detection,
        "paddle_structure_use_seal_recognition": use_seal_recognition,
        "paddle_structure_format_block_content": format_block_content,
    }
    try:
        raw_payload = PaddleStructureV3Runtime(config).run(input_file)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {"ok": True, "page_count": len(raw_payload), "output_json": str(output_path)}

    if middle_output or report or debug_markdown or scholarly_markdown:
        middle_path = Path(middle_output) if middle_output else output_path.with_name(f"{output_path.stem}_contexture_middle.json")
        middle = external_document_to_middle_document(
            raw_payload,
            layout_backend="paddle_pp_structure_v3",
            layout_model="PP-StructureV3",
            ocr_backend="paddle_ocr_v5",
            ocr_model=ocr_version,
            source_name=input_file.name,
            source=str(output_path),
            block_source="parsing_res_list",
            unmatched_policy=unmatched_policy,
            min_containment=min_containment,
        )
        middle = resolve_middle_for_rendering(middle)
        validation = validate_middle_json(middle)
        middle_path.parent.mkdir(parents=True, exist_ok=True)
        middle_path.write_text(json.dumps(middle, ensure_ascii=False, indent=2), encoding="utf-8")

        report_data = {
            "ok": validation.ok,
            "summary": validation.summary,
            "errors": [asdict(issue) for issue in validation.errors],
            "warnings": [asdict(issue) for issue in validation.warnings],
            "document_import": middle.get("metadata", {}).get("document_import"),
            "ocr_import": middle.get("metadata", {}).get("ocr_import"),
        }
        result["middle_output"] = str(middle_path)
        result["validation"] = report_data
        if report:
            report_path = Path(report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
        if debug_markdown:
            debug_path = Path(debug_markdown)
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(render_middle_debug_markdown(middle), encoding="utf-8")
        if scholarly_markdown:
            scholarly_path = Path(scholarly_markdown)
            scholarly_path.parent.mkdir(parents=True, exist_ok=True)
            scholarly_path.write_text(
                render_middle_scholarly_markdown(middle, include_provenance_comments=include_provenance_comments),
                encoding="utf-8",
            )
            result["scholarly_markdown"] = str(scholarly_path)

    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    paddle_structure_cli()

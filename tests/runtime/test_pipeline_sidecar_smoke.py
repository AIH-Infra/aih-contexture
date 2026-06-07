import json
from types import SimpleNamespace

from aih_contexture.runtime.artifacts import save_contexture_result
from aih_contexture.runtime.job import ContextureJob
from aih_contexture.runtime.runner import run_job
from aih_contexture.evaluation.scholarly_markdown import evaluate_scholarly_markdown_text


SMOKE_TEXT = "Contexture sidecar smoke text"


class DummyDetectionModel:
    disable_tqdm = False

    def __call__(self, images, batch_size=None):
        return [SimpleNamespace(bboxes=[]) for _ in images]


class DummyOcrErrorModel:
    disable_tqdm = False

    def __call__(self, page_texts, batch_size=None):
        return SimpleNamespace(labels=["good" for _ in page_texts])


def _write_minimal_text_pdf(path):
    stream = f"BT /F1 14 Tf 72 720 Td ({SMOKE_TEXT}) Tj ET".encode("latin-1")
    objects = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        (
            3,
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        ),
        (4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
        (5, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"),
    ]

    payload = bytearray(b"%PDF-1.4\n")
    offsets = []
    for obj_id, body in objects:
        offsets.append(len(payload))
        payload.extend(f"{obj_id} 0 obj\n".encode("latin-1"))
        payload.extend(body)
        payload.extend(b"\nendobj\n")

    xref_offset = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        payload.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    )
    path.write_bytes(payload)


def _write_sidecar(path, pdf_path):
    payload = {
        "schema_version": "contexture-middle-json/0.1",
        "source_name": str(pdf_path),
        "pages": [
            {
                "index": 0,
                "width": 612,
                "height": 792,
                "blocks": [
                    {
                        "id": "p0-b0",
                        "type": "Text",
                        "page_index": 0,
                        "order": 0,
                        "bbox": [60, 60, 552, 760],
                        "text": SMOKE_TEXT,
                    }
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pipeline_external_layout_sidecar_real_pdf_smoke(tmp_path):
    pdf_path = tmp_path / "smoke.pdf"
    sidecar_path = tmp_path / "sidecar.json"
    output_dir = tmp_path / "out"
    _write_minimal_text_pdf(pdf_path)
    _write_sidecar(sidecar_path, pdf_path)

    result = run_job(
        ContextureJob(
            input_path=str(pdf_path),
            mode="pipeline",
            output_formats=["markdown"],
            config={
                "layout_backend": "external_layout_sidecar",
                "external_layout_json": str(sidecar_path),
                "ocr_backend": "none",
                "disable_ocr": True,
                "emit_middle_json": True,
                "emit_middle_report": True,
                "emit_middle_debug": True,
                "emit_middle_scholarly": True,
                "emit_middle_scholarly_report": True,
                "pdftext_workers": 1,
                "build_highres_images": False,
                "equation_enabled": False,
                "table_enabled": False,
            },
        ),
        artifact_dict={
            "detection_model": DummyDetectionModel(),
            "ocr_error_model": DummyOcrErrorModel(),
        },
    )

    assert result.page_count == 1
    assert SMOKE_TEXT in (result.markdown or "")
    assert result.middle_json["schema_version"] == "contexture-middle-json/0.1"
    assert result.middle_json["backends"] == {
        "layout": "external_layout_sidecar",
        "ocr": "none",
    }

    output = save_contexture_result(result, str(output_dir), "smoke", "markdown")
    assert (output_dir / "smoke.md").exists()
    assert (output_dir / "smoke_middle.json").exists()
    assert (output_dir / "smoke_middle_report.json").exists()
    assert (output_dir / "smoke_middle_debug.md").exists()
    assert (output_dir / "smoke_middle_scholarly.md").exists()
    assert (output_dir / "smoke_middle_scholarly_report.json").exists()
    assert output["middle_json_path"] == str(output_dir / "smoke_middle.json")

    report = json.loads((output_dir / "smoke_middle_report.json").read_text(encoding="utf-8"))
    assert report["ok"] is True
    scholarly = (output_dir / "smoke_middle_scholarly.md").read_text(encoding="utf-8")
    assert SMOKE_TEXT in scholarly
    assert evaluate_scholarly_markdown_text(scholarly)["ok"] is True
    scholarly_report = json.loads((output_dir / "smoke_middle_scholarly_report.json").read_text(encoding="utf-8"))
    assert scholarly_report["ok"] is True

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

from aih_contexture.runtime import artifacts
from aih_contexture.runtime.config_builder import config_from_ui_params
from aih_contexture.scripts.ui.pipeline_job_plan import (
    build_pipeline_batch_jobs,
    build_pipeline_file_job_spec,
)
from aih_contexture.scripts.ui.task_outputs import (
    finalize_zip_outputs,
    output_paths_from_records,
)


SMOKE_TEXT = "Contexture UI artifact smoke text"


class DummyDetectionModel:
    disable_tqdm = False

    def __call__(self, images, batch_size=None):
        return [SimpleNamespace(bboxes=[]) for _ in images]


class DummyOcrErrorModel:
    disable_tqdm = False

    def __call__(self, page_texts, batch_size=None):
        return SimpleNamespace(labels=["good" for _ in page_texts])


def _write_minimal_text_pdf(path: Path) -> None:
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


def _write_sidecar(path: Path, pdf_path: Path) -> None:
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


def test_pipeline_worker_writes_middle_artifacts_and_ui_zip(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "smoke.pdf"
    sidecar_path = tmp_path / "sidecar.json"
    output_dir = tmp_path / "out"
    _write_minimal_text_pdf(pdf_path)
    _write_sidecar(sidecar_path, pdf_path)

    monkeypatch.setattr(
        artifacts,
        "create_model_dict",
        lambda: {
            "detection_model": DummyDetectionModel(),
            "ocr_error_model": DummyOcrErrorModel(),
        },
    )

    values = {
        "layout_backend": "external_layout_sidecar",
        "external_layout_json": str(sidecar_path),
        "external_layout_backend_name": "artifact_smoke",
        "external_layout_model": "contexture-test-sidecar",
        "ocr_backend": "none",
        "use_llm": False,
        "emit_middle_json": True,
        "emit_middle_report": True,
        "emit_middle_debug": True,
        "emit_middle_scholarly": True,
        "emit_middle_scholarly_report": True,
        "process_mode": "自动",
        "batch_threshold": 50,
        "pages_per_batch": 25,
        "table_enabled": False,
        "equation_enabled": False,
    }
    batch_jobs = build_pipeline_batch_jobs([(0, 1)], values, config_from_ui_params)
    job_spec = build_pipeline_file_job_spec(
        file_path=str(pdf_path),
        file_name=pdf_path.name,
        output_dir=str(output_dir),
        output_formats=["markdown"],
        fname_base="smoke",
        batch_jobs=batch_jobs,
    )

    result = artifacts.process_pipeline_job(job_spec)

    assert result["success"] is True
    names = {record["name"] for record in result["file_outputs"]}
    expected_names = {
        "smoke.md",
        "smoke_middle.json",
        "smoke_middle_report.json",
        "smoke_middle_debug.md",
        "smoke_middle_scholarly.md",
        "smoke_middle_scholarly_report.json",
    }
    assert expected_names <= names
    assert SMOKE_TEXT in (output_dir / "smoke.md").read_text(encoding="utf-8")
    assert json.loads((output_dir / "smoke_middle_report.json").read_text(encoding="utf-8"))["ok"] is True
    assert json.loads((output_dir / "smoke_middle_scholarly_report.json").read_text(encoding="utf-8"))["ok"] is True

    ctx = {}
    zip_path = finalize_zip_outputs(
        ctx,
        output_paths_from_records(result["file_outputs"]),
        output_dir,
        "contexture_pipeline_outputs.zip",
    )

    assert zip_path == str(output_dir / "contexture_pipeline_outputs.zip")
    assert ctx["last_zip_name"] == "contexture_pipeline_outputs.zip"
    with zipfile.ZipFile(zip_path) as zf:
        assert expected_names <= set(zf.namelist())

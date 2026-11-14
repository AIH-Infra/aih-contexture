from __future__ import annotations

from typing import Any

import pymupdf

from aih_contexture.backends.ocr.indra import IndraRuntime, IndraSettings, review_summary
from aih_contexture.backends.ocr.indra.evidence import attach_indra_evidence, clear_indra_evidence_stage
from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.builders.paddle_ocr import PaddleOcrBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.runtime.errors import ContextureConfigError
from aih_contexture.schema.document import Document


class IndraOcrBuilder(PaddleOcrBuilder):
    """Pipeline OCR builder backed by Indra OCR, usable with any layout backend.

    Indra reads the pages that need OCR; its lines (already in PDF points) are written back into the pipeline's
    line/span structures the same way the PaddleOCR builder does. With ``indra_layout`` as well, the runner takes
    the direct Middle route instead and this builder is not used.
    """

    ocr_backend_name = "indra_ocr"

    def __init__(self, config: dict[str, Any] | None = None, *, runtime: IndraRuntime | None = None):
        BaseBuilder.__init__(self, config)
        self.config = dict(config or {})
        self.settings = IndraSettings.from_config(self.config)
        self.runtime = runtime
        self._ocr_helper = OcrBuilder(recognition_model=None, config=self.config)
        self.last_runtime_payload = None
        self.last_review: dict[str, Any] | None = None

    def __call__(self, document: Document, provider: PdfProvider):
        from aih_contexture.runtime.pipeline_parallelism import plan_indra_workers

        self.last_review = None
        clear_indra_evidence_stage(document, stage="ocr")
        pages_to_ocr = [page for page in document.pages if page.text_extraction_method == "surya"]
        if not pages_to_ocr:
            return document
        pdf_path = getattr(provider, "filepath", None)
        if not pdf_path or not str(pdf_path).lower().endswith(".pdf"):
            raise ContextureConfigError("ocr_backend=indra_ocr reads PDF input only")
        indices = [int(page.page_id) for page in pages_to_ocr]

        plan = plan_indra_workers(self.config, total_pages=len(indices))
        pool = self.config.get("_sidecar_runtime_pool")
        runtime = self.runtime or IndraRuntime(self.settings, pool=pool)
        try:
            indra_pages = runtime.run(pdf_path, indices, cores=plan.workers)
        except RuntimeError as exc:
            raise ContextureConfigError(f"Indra OCR failed: {exc}") from exc
        finally:
            if self.runtime is None:
                runtime.close()
        self.last_review = review_summary(indra_pages, review_mean=self.settings.review_mean, review_min=self.settings.review_min)
        attach_indra_evidence(
            document, indra_pages, stage="ocr", settings=self.settings, version=runtime.version,
        )

        with pymupdf.open(pdf_path) as pdf:
            for page in pages_to_ocr:
                indra_page = indra_pages[int(page.page_id)]
                width, height = float(pdf[int(page.page_id)].rect.width), float(pdf[int(page.page_id)].rect.height)
                payload = _paddle_shaped_payload(indra_page, width=width, height=height)
                self._write_page_ocr(document, page, payload, image_size=(width, height), provider=provider)
        return document


def _paddle_shaped_payload(indra_page: dict[str, Any], *, width: float, height: float) -> dict[str, Any]:
    """Indra lines as the (texts, boxes, scores) lists the write-back expects, boxes in PDF points."""
    from aih_contexture.backends.ocr.indra.mapping import box_to_page_points

    dpi = float(indra_page.get("dpi") or 200)
    rotation = 0 if indra_page.get("vertical") else int(indra_page.get("rotation") or 0)
    lines = [line for line in indra_page.get("lines") or [] if str(line.get("text") or "").strip()]
    return {"res": {
        "rec_texts": [line["text"] for line in lines],
        "rec_boxes": [box_to_page_points(line["bbox"], dpi=dpi, rotation=rotation, page_width=width, page_height=height) for line in lines],
        "rec_scores": [line.get("conf") for line in lines],
    }}

from __future__ import annotations

from typing import Any

import pymupdf

from aih_contexture.backends.ocr.indra import IndraRuntime, IndraSettings, pages_to_middle, review_summary
from aih_contexture.backends.ocr.indra.evidence import attach_indra_evidence, clear_indra_evidence_stage
from aih_contexture.builders.external_layout_sidecar import ExternalLayoutSidecarBuilder, _page_index
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.runtime.errors import ContextureConfigError
from aih_contexture.schema.document import Document


class IndraLayoutBuilder(ExternalLayoutSidecarBuilder):
    """Pipeline layout builder backed by Indra OCR's layout labels and reading order.

    Only the block boxes, labels and order are used; the text comes from whatever OCR stage the pipeline has
    (disable_ocr = the PDF's own text layer, Chrome ScreenAI's searchable PDF, Surya, ...).
    """

    def __init__(self, config: dict[str, Any] | None = None, *, runtime: IndraRuntime | None = None):
        config = dict(config or {})
        config.setdefault("external_layout_backend_name", "indra_layout")
        config.setdefault("external_layout_model", "indra-ocr")
        super().__init__(config)
        self.settings = IndraSettings.from_config(config)
        self._config = config
        self.runtime = runtime
        self.last_review: dict[str, Any] | None = None

    def __call__(self, document: Document, provider: PdfProvider):
        from aih_contexture.runtime.pipeline_parallelism import plan_indra_workers

        self.last_review = None
        clear_indra_evidence_stage(document, stage="layout")
        pdf_path = getattr(provider, "filepath", None)
        if not pdf_path or not str(pdf_path).lower().endswith(".pdf"):
            raise ContextureConfigError("layout_backend=indra_layout reads PDF input only")
        indices = [_page_index(page, position) for position, page in enumerate(document.pages)]
        with pymupdf.open(pdf_path) as pdf:
            sizes = {index: (float(pdf[index].rect.width), float(pdf[index].rect.height)) for index in indices}

        plan = plan_indra_workers(self._config, total_pages=len(indices))
        runtime = self.runtime or IndraRuntime(self.settings)
        try:
            pages = runtime.run(pdf_path, indices, cores=plan.workers)
        except RuntimeError as exc:
            raise ContextureConfigError(f"Indra layout failed: {exc}") from exc
        finally:
            if self.runtime is None:
                runtime.close()

        self.last_review = review_summary(pages, review_mean=self.settings.review_mean, review_min=self.settings.review_min)
        attach_indra_evidence(
            document, pages, stage="layout", settings=self.settings, version=runtime.version,
        )
        middle = pages_to_middle(pages, page_sizes=sizes, version=runtime.version)
        sidecar_pages = self._load_pages_from_payload(middle, source="indra_runtime")
        layout_results = self._layout_results_for_pages(document.pages, sidecar_pages)
        self._layout_helper.add_blocks_to_pages(document.pages, layout_results)
        self._layout_helper.expand_layout_blocks(document)

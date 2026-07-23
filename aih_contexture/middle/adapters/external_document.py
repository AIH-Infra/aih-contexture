from __future__ import annotations

from typing import Any

from aih_contexture.middle.adapters.external_layout import external_layout_document_to_middle_document
from aih_contexture.middle.adapters.external_ocr import merge_external_ocr_into_middle_document


def external_document_to_middle_document(
    payload: dict[str, Any] | list[Any],
    *,
    layout_backend: str,
    ocr_backend: str | None = None,
    source_name: str | None = None,
    source: str | None = None,
    layout_model: str | None = None,
    ocr_model: str | None = None,
    block_source: str = "auto",
    unmatched_policy: str = "append_text_blocks",
    min_containment: float = 0.20,
) -> dict[str, Any]:
    """Normalize a full external document result into Contexture Middle JSON.

    This adapter is the preferred bridge for MinerU/Paddle-style document
    pipeline outputs that contain both layout blocks and OCR spans. It keeps the
    external pipeline upstream of Contexture Middle instead of letting it own
    Markdown rendering.
    """
    middle_doc = external_layout_document_to_middle_document(
        payload,
        backend=layout_backend,
        source_name=source_name,
        source=source,
        model=layout_model,
        block_source=block_source,
    )
    data = middle_doc.to_dict()
    data.setdefault("metadata", {}).update(
        {
            "import_source": "external_document_json",
            "source": source,
            "block_source": block_source,
        }
    )

    if ocr_backend:
        data = merge_external_ocr_into_middle_document(
            data,
            payload,
            backend=ocr_backend,
            source=source,
            model=ocr_model,
            unmatched_policy=unmatched_policy,
            min_containment=min_containment,
        )
        data.setdefault("metadata", {})["import_source"] = "external_document_json"

    data.setdefault("metadata", {})["document_import"] = {
        "layout_backend": layout_backend,
        "layout_model": layout_model,
        "ocr_backend": ocr_backend,
        "ocr_model": ocr_model,
        "source": source,
        "block_source": block_source,
        "unmatched_policy": unmatched_policy if ocr_backend else None,
        "min_containment": min_containment if ocr_backend else None,
    }
    return data

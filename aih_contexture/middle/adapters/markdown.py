from __future__ import annotations

import re
from typing import Any

from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance

_PAGE_ANCHOR_RE = re.compile(r"(?m)^\s*\{(?P<page>\d+)\}\s*$")


def markdown_to_middle_document(
    markdown: str,
    *,
    source_name: str | None = None,
    backend: str = "markdown",
    model: str | None = None,
    page_count: int | None = None,
) -> dict[str, Any]:
    """Build a minimal, auditable Middle document for text-only inputs.

    This is intentionally conservative: it preserves the rendered Markdown as
    text blocks and does not invent layout geometry. It lets every Contexture
    output carry a valid Middle artifact while retaining the original content.
    """
    text = str(markdown or "").strip()
    matches = list(_PAGE_ANCHOR_RE.finditer(text))
    pages: list[MiddlePage] = []
    if matches:
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            page_text = text[start:end].strip()
            # Contexture closes paged Markdown with a final {n} anchor. Match
            # the reading preview: that empty sentinel is not another page.
            if index == len(matches) - 1 and len(matches) > 1 and page_text in {"", "---"}:
                break
            if index == 0 and text[:match.start()].strip():
                page_text = text[:match.start()].strip() + "\n\n" + page_text
            page_index = int(match.group("page"))
            pages.append(_page(page_index, page_text, source_name, backend, model))
    else:
        total = max(1, int(page_count or 1))
        pages.append(_page(0, text, source_name, backend, model))
        for index in range(1, total):
            pages.append(_page(index, "", source_name, backend, model))

    return MiddleDocument(
        pages=pages,
        source_name=source_name,
        backends={"layout": "none", "ocr": backend, "model": model},
        metadata={"synthetic": True, "reason": "text_only_input"},
    ).to_dict()


def _page(index: int, text: str, source_name: str | None, backend: str, model: str | None) -> MiddlePage:
    block = MiddleBlock(
        id=f"page-{index}-text",
        type="Text",
        page_index=index,
        order=0,
        text=text,
        provenance=[MiddleProvenance(backend=backend, stage="text", model=model, source=source_name)],
    )
    return MiddlePage(
        index=index,
        blocks=[block],
        provenance=[MiddleProvenance(backend=backend, stage="document", model=model, source=source_name)],
    )

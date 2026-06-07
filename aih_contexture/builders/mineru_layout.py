from __future__ import annotations

from typing import Any

from aih_contexture.backends.layout.mineru_runtime import MineruCliLayoutRuntime
from aih_contexture.builders.external_layout_sidecar import ExternalLayoutSidecarBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema.document import Document


class MineruLayoutBuilder(ExternalLayoutSidecarBuilder):
    """Pipeline layout builder backed by MinerU CLI middle JSON output."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        runtime: MineruCliLayoutRuntime | None = None,
    ):
        config = dict(config or {})
        config.setdefault("external_layout_backend_name", "mineru_pp_doclayout_v2")
        config.setdefault("external_layout_model", "PP-DocLayoutV2")
        config.setdefault("external_layout_block_source", "para_blocks")
        super().__init__(config)
        self.runtime = runtime or MineruCliLayoutRuntime(config)
        self.last_runtime_result = None

    def __call__(self, document: Document, provider: PdfProvider):
        if self.external_layout_json:
            return super().__call__(document, provider)

        runtime_result = self.runtime.run(provider.filepath)
        self.last_runtime_result = runtime_result
        sidecar_pages = self._load_pages_from_path(runtime_result.middle_json_path)
        layout_results = self._layout_results_for_pages(document.pages, sidecar_pages)
        self._layout_helper.add_blocks_to_pages(document.pages, layout_results)
        self._layout_helper.expand_layout_blocks(document)

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from aih_contexture.backends.layout.mineru_direct_runtime import MineruDirectLayoutRuntime
from aih_contexture.builders.external_layout_sidecar import ExternalLayoutSidecarBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema.document import Document


class MineruDirectLayoutBuilder(ExternalLayoutSidecarBuilder):
    """Pipeline layout builder backed by MinerU PP-DocLayoutV2 only."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        runtime: MineruDirectLayoutRuntime | None = None,
    ):
        config = dict(config or {})
        config.setdefault("external_layout_backend_name", "mineru_pp_doclayout_v2_direct")
        config.setdefault("external_layout_model", "PP-DocLayoutV2")
        config.setdefault("external_layout_block_source", "boxes")
        super().__init__(config)
        self.runtime = runtime or MineruDirectLayoutRuntime(config)
        self.last_runtime_payload = None

    def __call__(self, document: Document, provider: PdfProvider):
        if self.external_layout_json:
            return super().__call__(document, provider)

        with tempfile.TemporaryDirectory(prefix="contexture-mineru-layout-direct-") as temp_dir:
            image_paths, page_sizes = self._save_page_images(document, Path(temp_dir))
            payload = self.runtime.run(image_paths, page_sizes=page_sizes)
            self.last_runtime_payload = payload

            sidecar_pages = self._load_pages_from_payload(payload, source="mineru_layout_direct_runtime")
            layout_results = self._layout_results_for_pages(document.pages, sidecar_pages)
            self._layout_helper.add_blocks_to_pages(document.pages, layout_results)
            self._layout_helper.expand_layout_blocks(document)

    def _save_page_images(self, document: Document, output_dir: Path) -> tuple[list[Path], list[tuple[int, int]]]:
        image_paths: list[Path] = []
        page_sizes: list[tuple[int, int]] = []
        for sequential_index, page in enumerate(document.pages):
            image = page.get_image(highres=False)
            if image is None:
                raise ValueError(f"Cannot run MinerU direct layout: page {sequential_index} has no renderable image.")
            image_path = output_dir / f"page_{sequential_index:06d}.png"
            image.save(image_path)
            image_paths.append(image_path)
            page_sizes.append((int(image.size[0]), int(image.size[1])))
        return image_paths, page_sizes

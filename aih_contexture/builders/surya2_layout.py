from __future__ import annotations

from aih_contexture.builders.vlm_layout import VlmLayoutBuilder
from aih_contexture.services.layout_surya2 import Surya2LayoutService


class Surya2LayoutBuilder(VlmLayoutBuilder):
    """Pipeline layout builder backed by Surya 2 Layout JSON output."""

    def __init__(self, config: dict | None = None):
        super().__init__(Surya2LayoutService(config), config=config)

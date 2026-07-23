from __future__ import annotations

from aih_contexture.builders.vlm_layout import VlmLayoutBuilder
from aih_contexture.services.layout_mineru_vl import MineruVLLayoutService


class MineruVLLayoutBuilder(VlmLayoutBuilder):
    """Pipeline layout builder backed by MinerU-VL Layout Detection."""

    def __init__(self, config: dict | None = None):
        super().__init__(MineruVLLayoutService(config), config=config)

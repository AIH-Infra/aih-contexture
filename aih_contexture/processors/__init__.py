from typing import Optional, Tuple

from pydantic import BaseModel

from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.util import assign_config


class BaseProcessor:
    block_types: Tuple[BlockTypes] | None = None  # What block types this processor is responsible for

    def __init__(self, config: Optional[BaseModel | dict] = None):
        assign_config(self, config)

    def __call__(self, document: Document, *args, **kwargs):
        raise NotImplementedError

import numpy as np

from aih_contexture.logger import get_logger
from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Reference
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.list import ListGroup
from aih_contexture.schema.groups.table import TableGroup
from aih_contexture.schema.registry import get_block_class
from aih_contexture.schema.groups.figure import FigureGroup

logger = get_logger()


class ReferenceProcessor(BaseProcessor):
    """
    A processor for adding references to the document.
    """

    def __init__(self, config):
        super().__init__(config)

    def __call__(self, document: Document):
        ReferenceClass: Reference = get_block_class(BlockTypes.Reference)
        attached_references = 0
        pages_with_refs = 0

        for page in document.pages:
            refs = page.refs
            ref_starts = np.array([ref.coord for ref in refs])

            blocks = []
            for block_id in page.structure:
                block = page.get_block(block_id)
                if isinstance(block, (ListGroup, FigureGroup, TableGroup)):
                    blocks.extend([page.get_block(b) for b in block.structure])
                else:
                    blocks.append(block)
            blocks = [b for b in blocks if not b.ignore_for_output]

            block_starts = np.array([block.polygon.bbox[:2] for block in blocks])

            if not (len(refs) and len(block_starts)):
                continue

            pages_with_refs += 1

            distances = np.linalg.norm(block_starts[:, np.newaxis, :] - ref_starts[np.newaxis, :, :], axis=2)
            for ref_idx in range(len(ref_starts)):
                block_idx = np.argmin(distances[:, ref_idx])
                block = blocks[block_idx]

                ref_block = page.add_full_block(ReferenceClass(
                    ref=refs[ref_idx].ref,
                    polygon=block.polygon,
                    page_id=page.page_id
                ))
                if block.structure is None:
                    block.structure = []
                block.structure.insert(0, ref_block.id)
                attached_references += 1

        logger.info(
            "[ReferenceProcessor] completed: pages_with_refs=%s attached_references=%s",
            pages_with_refs,
            attached_references,
        )

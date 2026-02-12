import pytest

from aih_contexture.schema import BlockTypes
from aih_contexture.processors.equation import EquationProcessor


@pytest.mark.config({"page_range": [0]})
def test_equation_processor(pdf_document, recognition_model):
    processor = EquationProcessor(recognition_model)
    processor(pdf_document)

    for block in pdf_document.pages[0].children:
        if block.block_type == BlockTypes.Equation:
            assert block.html is not None
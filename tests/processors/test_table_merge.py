from unittest.mock import Mock

import pytest

from aih_contexture.processors.llm.llm_table_merge import LLMTableMergeProcessor
from aih_contexture.processors.table import TableProcessor
from aih_contexture.schema import BlockTypes


@pytest.mark.filename("table_ex2.pdf")
def test_llm_table_processor_nomerge(pdf_document, table_rec_model, recognition_model, detection_model, mocker):
    mock_cls = Mock()
    mock_cls.return_value = {
        "merge": "true",
        "direction": "right"
    }

    cell_processor = TableProcessor(recognition_model, table_rec_model, detection_model)
    cell_processor(pdf_document)

    tables = pdf_document.contained_blocks((BlockTypes.Table,))
    assert len(tables) == 3

    processor = LLMTableMergeProcessor(mock_cls, {"use_llm": True, "gemini_api_key": "test"})
    processor(pdf_document)

    tables = pdf_document.contained_blocks((BlockTypes.Table,))
    assert len(tables) == 3
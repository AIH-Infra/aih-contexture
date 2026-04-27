from types import SimpleNamespace

from aih_contexture.processors.page_number import PageNumberProcessor
from aih_contexture.schema import BlockTypes


def _make_region(text: str, alignment: str = "left", margin_distance: float = 1.0):
    return SimpleNamespace(
        zone="header",
        source="typed",
        alignment=alignment,
        margin_distance=margin_distance,
        block=SimpleNamespace(block_type=BlockTypes.PageHeader),
        text=text,
    )


def test_newspaper_header_left_edge_page_number_survives_long_date_header():
    processor = PageNumberProcessor(
        {
            "page_numbering_enabled": True,
            "use_printed_page_number": True,
            "page_number_format": "auto",
        }
    )
    text = "262 THE ILLUSTRATED LONDON NEWS SEPT. 10, 1881"
    region = _make_region(text, alignment="left", margin_distance=1.0)

    candidates = processor._parse_page_number_candidates(text)

    assert [candidate.page_number for candidate in candidates] == ["262"]

    score = processor._score_candidate(candidates[0], region)
    assert score >= processor.min_candidate_score


def test_newspaper_header_right_edge_page_number_survives_long_date_header():
    processor = PageNumberProcessor(
        {
            "page_numbering_enabled": True,
            "use_printed_page_number": True,
            "page_number_format": "auto",
        }
    )
    text = "SUPPLEMENT TO THE ILLUSTRATED LONDON NEWS, SEPT. 10, 1881.—261"
    region = _make_region(text, alignment="right", margin_distance=1.0)

    candidates = processor._parse_page_number_candidates(text)

    assert [candidate.page_number for candidate in candidates] == ["261"]

    score = processor._score_candidate(candidates[0], region)
    assert score >= processor.min_candidate_score


def test_date_fragment_is_not_mistaken_for_page_number():
    processor = PageNumberProcessor(
        {
            "page_numbering_enabled": True,
            "use_printed_page_number": True,
            "page_number_format": "auto",
        }
    )
    text = "NOVEMBER 18, 1843.] THE ILLUSTRATED LONDON NEWS. 327"

    candidates = processor._parse_page_number_candidates(text)

    assert [candidate.page_number for candidate in candidates] == ["327"]

from aih_contexture.postprocess.markdown_engine import MarkdownPostprocessEngine
from aih_contexture.postprocess.markdown_lm import MarkdownLMAdapter
from aih_contexture.postprocess.printed_page_repair import build_review_spans, build_segment_diagnostics, build_segment_review_proposals, infer_sequence_repairs, normalize_candidate
from aih_contexture.processors.llm.llm_printed_page_correction import LLMPrintedPageCorrectionProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox


class FakeSparseService:
    openai_model = "fake-model"
    openai_base_url = "http://fake"
    openai_api_key = "secret"
    timeout = 45
    max_retries = 2

    def __call__(self, prompt, image, block, response_schema, max_retries=None, timeout=None):
        if '"pdf_page": 5' in prompt and '"chosen_value": "2"' not in prompt:
            return {
                "decisions": [
                    {"pdf_page": 5, "action": "fill_null", "chosen_value": "5", "reason": "test_safe_fill"}
                ],
                "analysis": "ok",
            }
        return {
            "decisions": [
                {"pdf_page": 2, "action": "replace", "chosen_value": "2", "reason": "test_sparse_review"}
            ],
            "analysis": "ok",
        }


def _page(page_id: int, printed_page_number: str | None = None) -> PageGroup:
    page = PageGroup(
        polygon=PolygonBox(polygon=[[0, 0], [100, 0], [100, 100], [0, 100]]),
        block_description="page",
        block_type=BlockTypes.Page,
        page_id=page_id,
        children=[],
        structure=[],
    )
    page._internal_metadata = {}
    if printed_page_number is not None:
        page._internal_metadata["printed_page_number"] = printed_page_number
    return page


def test_normalize_candidate_allows_safe_trailing_punctuation_only():
    assert normalize_candidate("305.") == "305"
    assert normalize_candidate("xiv.") == "XIV"
    assert normalize_candidate("p. 305") is None


def test_build_review_spans_limits_far_one_sided_candidates():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\nfoo\n{3}\nbar\n{4}\nbaz\n{5}\nqux\n{6}\nquux\n"""
    spans = build_review_spans(sample)
    reviewed_pages = [page.pdf_page for span in spans for page in span.pages]
    assert 5 not in reviewed_pages
    assert 6 not in reviewed_pages



def test_safe_review_spans_only_include_segment_review_proposals():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\n<!-- Page: 2 -->\nb\n{3}\n<!-- Page: 3 -->\nc\n{4}\n<!-- Page: 4 -->\nd\n{5}\n\ne\n{6}\n<!-- Page: 6 -->\nf\n{7}\n<!-- Page: 7 -->\ng\n{8}\n<!-- Page: 8 -->\nh\n"""
    adapter = MarkdownLMAdapter({}, service=FakeSparseService())
    spans = adapter._build_safe_review_spans(sample)

    reviewed_pages = [page.pdf_page for span in spans for page in span.pages]
    assert reviewed_pages == [5]
    assert spans[0].pages[0].candidates[0].action == "leave_null"
    assert any(candidate.action == "fill_null" and candidate.value == "5" for candidate in spans[0].pages[0].candidates)


def test_segment_diagnostics_detects_roman_arabic_boundary():
    sample = """{1}\n<!-- Page: i -->\na\n{2}\n<!-- Page: ii -->\nb\n{3}\n<!-- Page: 1 -->\nc\n{4}\n<!-- Page: 2 -->\nd\n"""
    diagnostics = build_segment_diagnostics(sample)

    assert diagnostics["kind_histogram"]["roman"] == 2
    assert diagnostics["kind_histogram"]["arabic"] == 2
    assert any(zone["zone_type"] == "main_body_boundary" for zone in diagnostics["query_zones"])
    assert any(segment["dominant_kind"] == "roman" for segment in diagnostics["segments"])
    assert any(segment["dominant_kind"] == "arabic" for segment in diagnostics["segments"])


def test_segment_diagnostics_marks_invalid_cluster_as_anomaly_zone():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\n<!-- Page: abc -->\nb\n{3}\n<!-- Page: def -->\nc\n{4}\n<!-- Page: 4 -->\nd\n"""
    diagnostics = build_segment_diagnostics(sample)

    assert any(obs["is_anomaly_candidate"] for obs in diagnostics["observations"] if obs["pdf_page"] in {2, 3})
    assert any(zone["zone_type"] == "anomaly_cluster" for zone in diagnostics["query_zones"])


def test_segment_review_proposals_abstain_when_target_pages_are_not_in_stable_segment():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\n<!-- Page: 2 -->\nb\n{3}\n<!-- Page: 99 -->\nc\n{4}\n<!-- Page: 4 -->\nd\n{5}\ne\n{6}\n<!-- Page: 6 -->\nf\n"""
    proposals = build_segment_review_proposals(sample)

    assert proposals["status"] == "review_only_proposals"
    assert proposals["proposal_count"] == 0
    assert any(item["pdf_page"] == 3 and item["segment_status"] == "mixed" for item in proposals["abstentions"])
    assert any(item["pdf_page"] == 5 and item["segment_status"] == "mixed" for item in proposals["abstentions"])


def test_segment_diagnostics_marks_restart_boundary_for_large_offset_shift():
    sample = """{1}\n<!-- Page: 498 -->\na\n{2}\n<!-- Page: 499 -->\nb\n{3}\n<!-- Page: 64 -->\nc\n{4}\n<!-- Page: 65 -->\nd\n"""
    diagnostics = build_segment_diagnostics(sample)

    assert any(segment["status"] == "stable" and segment["start_pdf_page"] == 1 and segment["end_pdf_page"] == 2 for segment in diagnostics["segments"])
    assert any(segment["status"] == "stable" and segment["start_pdf_page"] == 3 and segment["end_pdf_page"] == 4 for segment in diagnostics["segments"])


def test_segment_diagnostics_refines_long_mixed_run_by_offset_stability():
    sample = """{100}\n<!-- Page: 75 -->\na\n{101}\n<!-- Page: 76 -->\nb\n{102}\n<!-- Page: 77 -->\nc\n{103}\n<!-- Page: 78 -->\nd\n{104}\n<!-- Page: 79 -->\ne\n{105}\n<!-- Page: 999 -->\nf\n{106}\n<!-- Page: 81 -->\ng\n{107}\n<!-- Page: 82 -->\nh\n{108}\n<!-- Page: 83 -->\ni\n{109}\n<!-- Page: 84 -->\nj\n{110}\n<!-- Page: 85 -->\nk\n{111}\n<!-- Page: 86 -->\nl\n{112}\n<!-- Page: 87 -->\nm\n{113}\n<!-- Page: 88 -->\nn\n{114}\n<!-- Page: 89 -->\no\n{115}\n<!-- Page: 90 -->\np\n{116}\n<!-- Page: 91 -->\nq\n{117}\n<!-- Page: 92 -->\nr\n{118}\n<!-- Page: 93 -->\ns\n{119}\n<!-- Page: 94 -->\nt\n{120}\n<!-- Page: 95 -->\nu\n"""
    diagnostics = build_segment_diagnostics(sample)

    assert any(segment["status"] == "stable" and segment["start_pdf_page"] <= 100 and segment["end_pdf_page"] >= 104 for segment in diagnostics["segments"])
    assert any(segment["status"] == "stable" and segment["start_pdf_page"] <= 106 and segment["end_pdf_page"] >= 120 for segment in diagnostics["segments"])


def test_segment_diagnostics_splits_duplicate_anchor_conflict_window():
    sample = """{248}\n<!-- Page: 223 -->\na\n{249}\n<!-- Page: 224 -->\nb\n{250}\nc\n{250}\n<!-- Page: 225 -->\nd\n{251}\n<!-- Page: 226 -->\ne\n{252}\n<!-- Page: 227 -->\nf\n{253}\n<!-- Page: 228 -->\ng\n{254}\n<!-- Page: 229 -->\nh\n{255}\n<!-- Page: 230 -->\ni\n{256}\n<!-- Page: 231 -->\nj\n{257}\n<!-- Page: 232 -->\nk\n{258}\n<!-- Page: 233 -->\nl\n{259}\n<!-- Page: 234 -->\nm\n{260}\n<!-- Page: 235 -->\nn\n{261}\n<!-- Page: 236 -->\no\n{262}\n<!-- Page: 237 -->\np\n{263}\n<!-- Page: 238 -->\nq\n{264}\n<!-- Page: 239 -->\nr\n{265}\n<!-- Page: 240 -->\ns\n{266}\n<!-- Page: 241 -->\nt\n{267}\n<!-- Page: 242 -->\nu\n{268}\n<!-- Page: 243 -->\nv\n{269}\n<!-- Page: 244 -->\nw\n"""
    diagnostics = build_segment_diagnostics(sample)

    assert any(segment["start_pdf_page"] == 248 and segment["end_pdf_page"] == 250 for segment in diagnostics["segments"])
    assert any(segment["start_pdf_page"] == 250 and segment["end_pdf_page"] >= 268 for segment in diagnostics["segments"])
    assert len([segment for segment in diagnostics["segments"] if segment["start_pdf_page"] == 250]) <= 1



def test_segment_diagnostics_marks_small_middle_run_between_unresolved_regions_as_restart_zone():
    sample = """{524}\n<!-- Page: 499 -->\na\n{525}\nb\n{526}\nc\n{527}\nd\n{528}\n<!-- Page: 64 -->\ne\n{529}\nf\n{530}\n<!-- Page: 66 -->\ng\n{531}\n<!-- Page: bad -->\nh\n"""
    diagnostics = build_segment_diagnostics(sample)

    assert any(zone["zone_type"] == "restart_zone" and zone["start_pdf_page"] <= 524 and zone["end_pdf_page"] >= 530 for zone in diagnostics["query_zones"])
    assert any(segment["status"] == "restart" and segment["start_pdf_page"] <= 524 and segment["end_pdf_page"] >= 530 for segment in diagnostics["segments"])



def test_segment_review_proposals_abstain_on_stable_segment_edge_guard_band():
    sample = """{380}\n<!-- Page: 355 -->\na\n{381}\n<!-- Page: 356 -->\nb\n{382}\n<!-- Page: 357 -->\nc\n{383}\n<!-- Page: 358 -->\nd\n{384}\n<!-- Page: 359 -->\ne\n{385}\n<!-- Page: 360 -->\nf\n{386}\n<!-- Page: 361 -->\ng\n{387}\n<!-- Page: 362 -->\nh\n{388}\n<!-- Page: 363 -->\ni\n{389}\n<!-- Page: 364 -->\nj\n{390}\n<!-- Page: 365 -->\nk\n{391}\n<!-- Page: 366 -->\nl\n{392}\n\n{393}\n<!-- Page: 368 -->\nm\n{394}\n<!-- Page: 369 -->\nn\n{395}\n<!-- Page: 370 -->\no\n{396}\n<!-- Page: 11 -->\np\n{397}\n<!-- Page: 8 -->\nq\n{398}\n<!-- Page: 15 -->\nr\n{399}\n<!-- Page: 374 -->\ns\n{400}\n<!-- Page: 375 -->\nt\n{401}\n<!-- Page: 376 -->\nu\n{402}\n<!-- Page: 377 -->\nv\n{403}\n<!-- Page: 378 -->\nw\n{404}\n<!-- Page: 379 -->\nx\n"""
    proposals = build_segment_review_proposals(sample)

    assert any(item["pdf_page"] == 392 and item["reason"] == "near_guard_band_null_fill" for item in proposals["abstentions"])
    assert not any(item["pdf_page"] == 392 for item in proposals["proposals"])
    assert any(item["pdf_page"] == 394 and item["reason"] == "segment_edge_guard_band" for item in proposals["abstentions"])
    assert not any(item["pdf_page"] == 394 for item in proposals["proposals"])
    assert any(item["pdf_page"] == 399 and item["reason"] == "segment_edge_guard_band" for item in proposals["abstentions"])
    assert not any(item["pdf_page"] == 399 for item in proposals["proposals"])


def test_segment_review_proposals_do_not_emit_changes_for_clean_stable_restart_like_runs():
    sample = """{1}\n<!-- Page: 498 -->\na\n{2}\n<!-- Page: 499 -->\nb\n{3}\n<!-- Page: 64 -->\nc\n{4}\n<!-- Page: 65 -->\nd\n"""
    proposals = build_segment_review_proposals(sample)

    assert proposals["proposal_count"] == 0
    assert proposals["abstain_count"] == 0


def test_engine_summary_includes_segment_diagnostics_and_review_proposals_without_changing_apply_behavior():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\n<!-- Page: 99 -->\nb\n{3}\n<!-- Page: 3 -->\nc\n"""
    engine = MarkdownPostprocessEngine({
        "markdown_postprocess_enable_cleanup": False,
        "markdown_postprocess_enable_printed_page_repair": True,
        "markdown_postprocess_enable_llm": False,
        "markdown_postprocess_review_only": False,
    })

    result = engine.process(sample)
    summary = result.summary()

    assert summary["status"] == "applied"
    assert "segment_diagnostics" in summary["metadata"]
    assert "segment_review_proposals" in summary["metadata"]
    assert summary["metadata"]["segment_diagnostics"]["page_count"] == 3
    assert "segment_review_proposals" in summary["metadata"]
    assert result.markdown == sample


def test_review_mode_keeps_original_markdown_with_sparse_suggestions():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\n<!-- Page: 2 -->\nb\n{3}\n<!-- Page: 3 -->\nc\n{4}\n<!-- Page: 4 -->\nd\n{5}\n\ne\n{6}\n<!-- Page: 6 -->\nf\n{7}\n<!-- Page: 7 -->\ng\n{8}\n<!-- Page: 8 -->\nh\n"""
    config = {
        "markdown_postprocess_enable_cleanup": False,
        "markdown_postprocess_enable_printed_page_repair": False,
        "markdown_postprocess_enable_llm": True,
        "markdown_postprocess_review_only": True,
        "markdown_postprocess_llm_provider": "openai",
        "markdown_postprocess_llm_base_url": "http://fake",
        "markdown_postprocess_llm_model": "fake-model",
    }
    engine = MarkdownPostprocessEngine(config, llm_adapter=MarkdownLMAdapter(config, service=FakeSparseService()))
    result = engine.process(sample)
    summary = result.summary()

    assert result.markdown == sample
    assert summary["mode"] == "review"
    assert summary["status"] == "review_completed_suggestions_only"
    assert summary["suggested_action_count"] == 1
    assert summary["applied_action_count"] == 0
    assert summary["metadata"]["llm"]["span_source"] == "segment_review_proposals"
    assert summary["metadata"]["review_span_count"] == 1


def test_apply_mode_only_changes_page_comment():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\n<!-- Page: 2 -->\nb\n{3}\n<!-- Page: 3 -->\nc\n{4}\n<!-- Page: 4 -->\nd\n{5}\n\ne\n{6}\n<!-- Page: 6 -->\nf\n{7}\n<!-- Page: 7 -->\ng\n{8}\n<!-- Page: 8 -->\nh\n"""
    config = {
        "markdown_postprocess_enable_cleanup": False,
        "markdown_postprocess_enable_printed_page_repair": False,
        "markdown_postprocess_enable_llm": True,
        "markdown_postprocess_review_only": False,
        "markdown_postprocess_llm_provider": "openai",
        "markdown_postprocess_llm_base_url": "http://fake",
        "markdown_postprocess_llm_model": "fake-model",
    }
    engine = MarkdownPostprocessEngine(config, llm_adapter=MarkdownLMAdapter(config, service=FakeSparseService()))
    result = engine.process(sample)

    assert "<!-- Page: 5 -->" in result.markdown
    assert "{5}" in result.markdown
    assert "\ne\n" in result.markdown


def test_llm_no_safe_spans_sets_skipped_status_and_zero_review_span_count():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\n<!-- Page: 99 -->\nb\n{3}\n<!-- Page: 3 -->\nc\n"""
    config = {
        "markdown_postprocess_enable_cleanup": False,
        "markdown_postprocess_enable_printed_page_repair": False,
        "markdown_postprocess_enable_llm": True,
        "markdown_postprocess_review_only": True,
        "markdown_postprocess_llm_provider": "openai",
        "markdown_postprocess_llm_base_url": "http://fake",
        "markdown_postprocess_llm_model": "fake-model",
    }
    engine = MarkdownPostprocessEngine(config, llm_adapter=MarkdownLMAdapter(config, service=FakeSparseService()))
    result = engine.process(sample)
    summary = result.summary()

    assert summary["status"] == "no_safe_segment_proposals"
    assert summary["skipped_reason"] == "no_safe_segment_proposals"
    assert summary["metadata"]["review_span_count"] == 0
    assert summary["metadata"]["llm"]["span_count"] == 0
    assert summary["metadata"]["llm"]["invoked"] is False


def test_pipeline_llm_printed_page_correction_reuses_sparse_engine():
    document = Document(
        filepath="fake.pdf",
        pages=[_page(1, "1"), _page(2, "2"), _page(3, "3"), _page(4, "4"), _page(5), _page(6, "6"), _page(7, "7"), _page(8, "8")],
    )
    processor = LLMPrintedPageCorrectionProcessor(FakeSparseService(), config={})

    processor(document)

    assert document.pages[4]._internal_metadata["printed_page_number"] == "5"
    assert document.pages[4]._internal_metadata["printed_page_number_numeric"] == 5
    assert document.pages[4]._internal_metadata["printed_page_number_corrected"] is True
    assert document._internal_metadata["llm_printed_page_correction_report"]["status"] == "applied"
    assert document._internal_metadata["llm_printed_page_correction_report"]["applied_action_count"] == 1


def test_rule_apply_uses_segment_review_proposals_and_avoids_large_jump_replace():
    sample = """{1}\n<!-- Page: 1 -->\na\n{2}\n<!-- Page: 2 -->\nb\n{3}\n<!-- Page: 99 -->\nc\n{4}\n<!-- Page: 4 -->\nd\n{5}\n\ne\n{6}\n<!-- Page: 6 -->\nf\n"""
    rewritten, actions, warnings = infer_sequence_repairs(sample)

    assert rewritten == sample
    assert actions == []
    assert warnings == ["No conservative printed-page repairs were applied."]


def test_segment_review_proposals_abstain_on_roman_replace():
    sample = """{1}\n<!-- Page: I -->\na\n{2}\n<!-- Page: XV -->\nb\n{3}\n<!-- Page: VII -->\nc\n{4}\n<!-- Page: VIII -->\nd\n{5}\n<!-- Page: IX -->\ne\n"""
    proposals = build_segment_review_proposals(sample)

    assert proposals["proposal_count"] == 0
    assert any(item["reason"] == "roman_replace_abstain" for item in proposals["abstentions"])



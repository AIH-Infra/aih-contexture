from aih_contexture.scripts.ui.pipeline_batch_plan import (
    page_range_to_config_value,
    plan_pipeline_page_ranges,
    should_batch_pages,
    split_page_ranges,
    target_page_ranges,
)


def test_should_batch_pages_respects_process_mode():
    assert should_batch_pages(100, "强制单批", 50) is False
    assert should_batch_pages(10, "强制分批", 50) is True
    assert should_batch_pages(51, "自动", 50) is True
    assert should_batch_pages(50, "自动", 50) is False


def test_target_page_ranges_converts_one_based_inclusive_to_zero_based_exclusive():
    assert target_page_ranges(
        total_pages=100,
        use_page_range=True,
        start_page_1based=2,
        end_page_1based=10,
    ) == [(1, 10)]


def test_target_page_ranges_clamps_end_to_document():
    assert target_page_ranges(
        total_pages=5,
        use_page_range=True,
        start_page_1based=3,
        end_page_1based=99,
    ) == [(2, 5)]


def test_split_page_ranges_splits_only_when_required():
    assert split_page_ranges([(0, 10)], should_batch=False, pages_per_batch=3) == [(0, 10)]
    assert split_page_ranges([(0, 10)], should_batch=True, pages_per_batch=4) == [
        (0, 4),
        (4, 8),
        (8, 10),
    ]


def test_plan_pipeline_page_ranges_matches_auto_batching_behavior():
    assert plan_pipeline_page_ranges(
        total_pages=12,
        process_mode="自动",
        batch_threshold=10,
        pages_per_batch=5,
    ) == [(0, 5), (5, 10), (10, 12)]


def test_plan_pipeline_page_ranges_keeps_small_document_single_batch():
    assert plan_pipeline_page_ranges(
        total_pages=10,
        process_mode="自动",
        batch_threshold=10,
        pages_per_batch=5,
    ) == [(0, 10)]


def test_page_range_to_config_value_uses_inclusive_end():
    assert page_range_to_config_value((5, 10)) == "5-9"

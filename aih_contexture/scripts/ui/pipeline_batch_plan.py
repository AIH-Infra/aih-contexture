from __future__ import annotations


def should_batch_pages(total_pages: int, process_mode: str, batch_threshold: int) -> bool:
    if process_mode == "强制单批":
        return False
    if process_mode == "强制分批":
        return True
    return total_pages > batch_threshold


def target_page_ranges(
    *,
    total_pages: int,
    use_page_range: bool,
    start_page_1based: int | None,
    end_page_1based: int | None,
) -> list[tuple[int, int]]:
    if use_page_range and start_page_1based and end_page_1based:
        start0 = max(0, int(start_page_1based) - 1)
        end0 = min(total_pages - 1, int(end_page_1based) - 1)
        return [(start0, end0 + 1)]
    return [(0, total_pages)]


def split_page_ranges(
    ranges: list[tuple[int, int]],
    *,
    should_batch: bool,
    pages_per_batch: int,
) -> list[tuple[int, int]]:
    page_ranges: list[tuple[int, int]] = []
    batch_size = int(pages_per_batch)
    for range_start, range_end in ranges:
        if (not should_batch) or (range_end - range_start) <= batch_size:
            page_ranges.append((range_start, range_end))
        else:
            current = range_start
            while current < range_end:
                next_end = min(current + batch_size, range_end)
                page_ranges.append((current, next_end))
                current = next_end
    return page_ranges


def plan_pipeline_page_ranges(
    *,
    total_pages: int,
    process_mode: str,
    batch_threshold: int,
    pages_per_batch: int,
    use_page_range: bool = False,
    start_page_1based: int | None = None,
    end_page_1based: int | None = None,
) -> list[tuple[int, int]]:
    should_batch = should_batch_pages(total_pages, process_mode, batch_threshold)
    targets = target_page_ranges(
        total_pages=total_pages,
        use_page_range=use_page_range,
        start_page_1based=start_page_1based,
        end_page_1based=end_page_1based,
    )
    return split_page_ranges(
        targets,
        should_batch=should_batch,
        pages_per_batch=pages_per_batch,
    )


def page_range_to_config_value(page_range: tuple[int, int]) -> str:
    start, end = page_range
    return f"{start}-{end - 1}"

"""Page-specific evidence gaps for classical reading exports.

This is a review report, never a licence to remove numeric source text.
"""
from __future__ import annotations

from typing import Any

from aih_contexture.middle.native_geometry import native_words
from aih_contexture.utils.markdown_regions import markdown_lines


CLASSICAL_REVIEW_KEY = 'classical_marginalia_review'


def classical_review_status(document: dict[str, Any]) -> dict[str, Any]:
    """Describe unresolved native geometry without guessing what digits mean."""
    pages = []
    resolution = (document.get('metadata') or {}).get('classical_marginalia_resolution') or {}
    has_pdf_supplement = bool(resolution.get('with_pdf_supplement'))
    for page in document.get('pages', []):
        regions = []
        blocks_by_id = {b.get('id'): b for b in page.get('blocks', [])}
        analysis = (page.get('attrs') or {}).get('classical_marginalia') or {}
        seen_numeric = set()
        for item in analysis.get('locators', []):
            if item.get('scheme') != 'numeric_margin' or item.get('edition_system') != 'unconfirmed':
                continue
            identity = item.get('block_id'), tuple(item.get('char_range') or [])
            if identity in seen_numeric:
                continue
            seen_numeric.add(identity)
            regions.append({'block_id': item.get('block_id'),
                'block_type': (blocks_by_id.get(item.get('block_id')) or {}).get('type'),
                'char_range': item.get('char_range'), 'reason': 'unconfirmed_numeric_margin'})
        for block in page.get('blocks', []):
            text = str(block.get('text') or '')
            kind = block.get('type')
            if not text.strip() or any(protected for _, protected in markdown_lines(text)):
                continue
            if (block.get('attrs') or {}).get('semantic_role') == 'footnote_definition':
                continue
            if native_words(block, page):
                continue
            reason = None
            if kind in {'Form', 'ComplexRegion'} and any(char.isdigit() for char in text):
                reason = 'numeric_complex_region_without_word_geometry'
            elif kind in {'Text', 'ListItem'} and not has_pdf_supplement:
                reason = 'body_without_word_geometry'
            if reason:
                regions.append({'block_id': block.get('id'), 'block_type': kind, 'reason': reason})
        pages.append({
            'index': page['index'],
            'status': 'needs_review' if regions else 'no_geometry_gap_detected',
            'regions': regions,
        })
    pending = [page['index'] for page in pages if page['status'] == 'needs_review']
    return {
        'version': 'classical-review/2',
        'status': 'needs_review' if pending else 'no_geometry_gap_detected',
        'page_count': len(pages),
        'needs_review_page_count': len(pending),
        'needs_review_pages': pending,
        'pages': pages,
    }


def classical_review_warning(review: dict[str, Any]) -> str | None:
    pending = review.get('needs_review_pages') or []
    if not pending:
        return None
    labels = ', '.join('{' + str(index) + '}' for index in pending[:12])
    remainder = f' 等 {len(pending)} 页' if len(pending) > 12 else ''
    reasons = {r.get('reason') for page in review.get('pages', []) for r in page.get('regions', [])}
    if 'unconfirmed_numeric_margin' in reasons:
        detail = '数字边码的含义未确认'
        if reasons - {'unconfirmed_numeric_margin'}:
            detail += '，部分区域缺少文字级坐标'
        return (f'边码与边注待核：输入页 {labels}{remainder} 的{detail}；'
                '未确认内容已独立保留，请对照原页。输入页从0开始，逐页记录保存在 Middle JSON 中。')
    return (
        f'边码与边注待核：输入页 {labels}{remainder} 的部分区域缺少文字级坐标；'
        '无法确认的数字和文字已保留，已确认区域的处理结果仍有效。'
        '输入页从0开始，逐页记录保存在 Middle JSON 中。'
    )

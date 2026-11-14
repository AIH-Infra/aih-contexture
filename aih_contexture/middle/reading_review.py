"""One page review summary for saved exports and previews, without text copies."""
from __future__ import annotations

from aih_contexture.middle.table_rendering import table_review_records

READING_REVIEW_KEY = 'reading_review'


def reading_review_status(document, tables=None):
    from aih_contexture.middle.storage import decode_middle_storage
    document = decode_middle_storage(document)
    metadata = document.get('metadata') or {}
    metadata = metadata if isinstance(metadata, dict) else {}
    classical = metadata.get('classical_marginalia_review') or {}
    classical = classical if isinstance(classical, dict) else {}
    geometry_pages = {p.get('index'): p for p in classical.get('pages', []) if isinstance(p, dict)}
    tables = table_review_records(document) if tables is None else tables
    from aih_contexture.middle.indra_evidence import indra_review_from_document
    indra_by_page = {}
    for stage, observations in indra_review_from_document(document).get('stages', {}).items():
        for observation in observations:
            reason = 'indra_ocr_low_confidence' if stage == 'ocr' else 'indra_layout_auxiliary_low_confidence'
            if 'missing_text_layer' in observation.get('reasons', []):
                reason = 'indra_missing_text_layer'
            indra_by_page.setdefault(observation['page_index'], []).append({
                'reason': reason,
                'stage': stage, 'mean': observation['mean'], 'min': observation['min'],
            })
    pages = []
    for page in document.get('pages') or []:
        if not isinstance(page, dict):
            continue
        index = page.get('index')
        regions = [dict(r) for r in geometry_pages.get(index, {}).get('regions', []) if isinstance(r, dict)]
        regions.extend(indra_by_page.get(index, []))
        for table in tables:
            if table.get('page_index') == index and table.get('status') == 'needs_review':
                regions.append({k: table[k] for k in ('block_id', 'reason', 'source_sha256') if k in table})
        if (page.get('attrs') or {}).get('logical_page_mapping') == 'needs_review':
            regions.append({'reason': 'logical_page_mapping_unconfirmed'})
        for source in ((page.get('attrs') or {}).get('reading_folio_review') or {}).get('sources', []):
            regions.append({**{k: source[k] for k in ('block_id', 'char_range', 'bbox') if k in source},
                            'reason': 'unconfirmed_page_folio'})
        for block in page.get('blocks') or []:
            if (block.get('attrs') or {}).get('footnote_status') == 'unconfirmed':
                regions.append({'block_id': block.get('id'), 'reason': 'unconfirmed_footnote_marker'})
        pages.append({'index': index, 'status': 'needs_review' if regions else 'no_known_review_issue', 'regions': regions})
    pending = [page['index'] for page in pages if page['status'] == 'needs_review']
    return {'version': 'reading-review/1', 'pages': pages, 'page_count': len(pages),
            'status': 'needs_review' if pending else 'no_known_review_issue',
            'needs_review_pages': pending, 'needs_review_page_count': len(pending)}


def reading_page_warning(review):
    if not review or review.get('status') != 'needs_review':
        return None
    reasons = {r.get('reason') for r in review.get('regions', []) if isinstance(r, dict)}
    if 'indra_missing_text_layer' in reasons:
        return '该页检测到文字区域，但没有可用的 PDF 文字层。内部 OCR 已关闭，请复核版面与文字输出。'
    geometry = {'numeric_complex_region_without_word_geometry', 'body_without_word_geometry'}
    if reasons and reasons <= geometry:
        return '本页边码与边注有待核区域：部分原始文字缺少词级坐标，无法确认的数字和文字仍保留在阅读文件中。'
    labels = []
    if reasons & geometry:
        labels.append('部分文字缺少词级坐标')
    if 'unconfirmed_numeric_margin' in reasons:
        labels.append('数字边码含义未确认')
    if reasons & {'table_group_structure_unconfirmed', 'source_table_structure_missing', 'unresolved_table_structure'}:
        labels.append('表格或复杂区域结构未确认')
    if 'unconfirmed_footnote_marker' in reasons:
        labels.append('脚注标记未确认')
    if 'logical_page_mapping_unconfirmed' in reasons:
        labels.append('逻辑分页未确认')
    if 'unconfirmed_page_folio' in reasons:
        labels.append('页码候选未确认')
    if 'indra_ocr_low_confidence' in reasons:
        labels.append('Indra OCR 行识别置信度偏低')
    if 'indra_layout_auxiliary_low_confidence' in reasons:
        labels.append('Indra 版面辅助识别置信度偏低（不代表最终文字准确率）')
    return '本页待核：' + '；'.join(labels or ['部分内容尚未确认']) + '。原始内容已保留，请对照原页。'

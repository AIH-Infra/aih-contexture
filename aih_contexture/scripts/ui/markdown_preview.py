"""Lazy preview of the exact saved reading Markdown, one input page at a time."""
from __future__ import annotations

import collections
import json
import re
import hashlib
from functools import lru_cache
from pathlib import Path
from aih_contexture.utils.markdown_regions import markdown_lines
from aih_contexture.middle.reading_review import reading_review_status, reading_page_warning
from aih_contexture.middle.reading_pages import manifest_pages, reading_page_slices, reading_text


def reading_page_review(markdown_path: str | Path, page_index: int, *, allow_legacy: bool = False) -> dict | None:
    """Read an explicitly requested, exact adjacent diagnostic artifact."""
    path = Path(markdown_path)
    stems = [path.stem]
    if path.name.endswith('_middle_scholarly.md'):
        stems.insert(0, path.stem.removesuffix('_middle_scholarly'))
    for suffix in ('.page_repaired.review', '.page_repaired', '.review'):
        if path.stem.endswith(suffix):
            stems.insert(0, path.stem.removesuffix(suffix))
    for stem in dict.fromkeys(stems):
        diagnostic_path = path.with_name(stem + '.diagnostics.json')
        try:
            if diagnostic_path.is_file() and diagnostic_path.stat().st_size <= 64 * 1024 * 1024:
                payload = json.loads(diagnostic_path.read_text(encoding='utf-8-sig'))
                artifact = payload.get('reading_artifact') or {}
                if artifact and (artifact.get('name') != path.name or artifact.get('sha256') !=
                                 hashlib.sha256(path.read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest()):
                    continue
                for page in (payload.get('reading_review') or {}).get('pages', []):
                    if isinstance(page, dict) and page.get('index') == page_index:
                        return page
        except (OSError, ValueError, UnicodeError, AttributeError):
            continue
        if not allow_legacy:
            continue
        middle_path = path.with_name(stem + '_middle.json')
        try:
            if not middle_path.is_file() or middle_path.stat().st_size > 64 * 1024 * 1024:
                continue
            data = json.loads(middle_path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError, UnicodeError):
            continue
        metadata = data.get('metadata') if isinstance(data, dict) else None
        review = metadata.get('reading_review') if isinstance(metadata, dict) else None
        if not isinstance(review, dict) or not isinstance(review.get('pages'), list):
            try:
                review = reading_review_status(data)
            except (TypeError, AttributeError, ValueError, KeyError):
                continue
        if not isinstance(review, dict) or not isinstance(review.get('pages'), list):
            continue
        for page in review['pages']:
            if isinstance(page, dict) and page.get('index') == page_index:
                return page
    return None


def split_reading_pages(markdown: str, manifest: dict | None = None) -> list[tuple[str, str]]:
    """Lazy preview of the exact saved reading Markdown, one input page at a time.

    Legacy fallback parsing rules:
    - Anchors inside fenced code blocks (``` or ~~~) are ignored as literals.
    - Discards only empty repeated boundary fragments (repeated batch seams).
    - Preserves genuine blank pages (empty body with distinct following label).
    - Preserves non-empty duplicate pages and assigns unique disambiguated labels.
    - Preserves preamble before the first anchor in the first page.
    - Plain brace literals outside code remain ambiguous without a source page manifest.
    """
    mapped = reading_page_slices(markdown, manifest)
    if mapped is not None:
        return [(f'输入页 {{{index}}}', text) for index, _, text in mapped]
    markdown = reading_text(markdown)
    offset = 0
    anchors = []
    for line, protected in markdown_lines(markdown):
        if not protected:
            m = re.match(r"^\{(\d+)\}[ \t]*(?:\r?\n)?$", line)
            if m:
                anchors.append((offset, offset + len(line), m.group(1)))
        offset += len(line)

    if not anchors:
        return [("全文", markdown)]

    kept = []
    for i, (anchor_start, content_start, label) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(markdown)
        body = markdown[content_start:end]
        empty = re.sub(r"(?m)^\s*---\s*$", "", body).strip() == ""
        if empty and i == len(anchors) - 1:
            continue
        if empty and i + 1 < len(anchors) and label == anchors[i + 1][2]:
            continue
        start = 0 if len(kept) == 0 else anchor_start
        kept.append((label, markdown[start:end]))

    if not kept:
        return [("全文", markdown)]

    counts = collections.Counter(k[0] for k in kept)
    indices = collections.defaultdict(int)
    pages = []
    for label, chunk_text in kept:
        if counts[label] > 1:
            indices[label] += 1
            page_label = f"输入页 {{{label}}} (片段 {indices[label]})"
        else:
            page_label = f"输入页 {{{label}}}"
        pages.append((page_label, chunk_text))
    return pages


@lru_cache(maxsize=8)
def _saved_page_manifest(path: str, size: int, modified_ns: int):
    payload = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return (payload.get('metadata') or payload).get('reading_page_manifest')


def load_reading_page_manifest(markdown_path, markdown, *, middle_path=None):
    """Read only paired operational metadata; diagnostics are not required."""
    path = Path(markdown_path)
    stems = [path.stem]
    if path.name.endswith('_middle_scholarly.md'):
        stems.insert(0, path.stem.removesuffix('_middle_scholarly'))
    for suffix in ('.page_repaired.review', '.page_repaired', '.review'):
        if path.stem.endswith(suffix):
            stems.insert(0, path.stem.removesuffix(suffix))
    candidates = [path.with_name(stem + '_meta.json') for stem in dict.fromkeys(stems)]
    candidates += ([Path(middle_path)] if middle_path else [])
    candidates += [path.with_name(stem + '_middle.json') for stem in dict.fromkeys(stems)]
    for candidate in dict.fromkeys(candidates):
        try:
            if not candidate.is_file() or candidate.stat().st_size > 256 * 1024 * 1024:
                continue
            stat = candidate.stat()
            manifest = _saved_page_manifest(str(candidate.resolve()), stat.st_size, stat.st_mtime_ns)
            if manifest_pages(markdown, manifest) is not None:
                return manifest
        except (OSError, UnicodeError, ValueError, AttributeError, TypeError):
            continue
    return None


def render_markdown_preview(st, processed_files: dict) -> None:
    choices = {}
    records_by_path = {}
    for group, records in processed_files.items():
        for record in records:
            path = record.get("path")
            if record.get("format") in {"markdown", "middle_scholarly"} and path and Path(path).is_file():
                choices[path] = f"{group} · {record.get('name') or Path(path).name}"
                records_by_path[path] = record
    if not choices or not st.checkbox("预览阅读 Markdown", value=False, key="reading_preview_enabled"):
        return
    path = st.selectbox("阅读文件", options=list(choices), format_func=choices.get, key="reading_preview_file")
    if path not in choices:
        return
    try:
        if Path(path).stat().st_size > 128 * 1024 * 1024:
            st.info("文件较大，请下载后查看。")
            return
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        st.error(f"无法读取阅读文件：{exc}")
        return
    manifest = load_reading_page_manifest(path, text, middle_path=records_by_path[path].get('middle_json_path'))
    pages = split_reading_pages(text, manifest)
    # The physical labels must participate in widget identity. Reusing numeric
    # offsets with a changed format_func can leave a previous book's labels in
    # the browser while the server already renders a different page.
    labels = [label for label, _ in pages]
    identity = (path, hashlib.sha256(text.encode('utf-8')).hexdigest())
    previous = st.session_state.get('reading_preview_identity')
    if previous and previous[0] != path:
        st.session_state.pop('reading_preview_page', None)
    st.session_state['reading_preview_identity'] = identity
    if st.session_state.get("reading_preview_page") not in labels:
        st.session_state["reading_preview_page"] = labels[0]
    selected = st.selectbox("输入物理页", options=labels, key="reading_preview_page")
    if selected is None:
        return
    selected_index = labels.index(selected)
    page_number = re.search(r'\{(\d+)\}', selected)
    st.caption("预览显示已保存结果；修改转换设置后需重新生成。定位注释在阅读视图中隐藏。{n} 为从 0 开始的输入物理页索引，Page 表示印刷页码；定位范围若无 … 延展标记，不能据此认定为闭区间。")
    st.markdown(
        '<style>.st-key-reading_preview_body {max-width:90ch; margin-inline:auto;}'
        '.st-key-reading_preview_body [data-testid="stMarkdownContainer"] '
        '{overflow-x:auto;}</style>',
        unsafe_allow_html=True,
    )
    with st.container(key="reading_preview_body"):
        st.markdown(pages[selected_index][1], unsafe_allow_html=True)
    with st.expander("本页 Markdown 源码", expanded=False):
        st.code(pages[selected_index][1], language="markdown")
    if st.checkbox('查看诊断信息', value=False, key='reading_preview_diagnostics'):
        with st.expander('诊断信息', expanded=True):
            review = reading_page_review(path, int(page_number[1]), allow_legacy=True) if page_number else None
            warning = reading_page_warning(review)
            if warning:
                st.warning(warning)
            elif review is None:
                st.info('没有配对的诊断信息；生成时可勾选“输出诊断信息”。')
            else:
                st.caption('本页没有已记录的待核事项。')

"""One preparation contract for UI and headless Middle re-rendering."""
from __future__ import annotations

from aih_contexture.middle.storage import decode_middle_storage

from dataclasses import dataclass
from typing import Any

from aih_contexture.middle.classical_capabilities import classical_marginalia_capabilities
from aih_contexture.middle.geometry_profile import is_lean_middle
from aih_contexture.middle.classical_review import (
    CLASSICAL_REVIEW_KEY, classical_review_status, classical_review_warning,
)
from aih_contexture.middle.scholarly_markdown import render_middle_scholarly_markdown
from aih_contexture.middle.semantics import resolve_middle_for_rendering
from aih_contexture.middle.semantics.classical_marginalia import (
    normalize_classical_marginalia_mode,
    normalize_classical_text_marginalia_mode,
    resolve_classical_marginalia,
)
from aih_contexture.middle.table_rendering import table_review_records
from aih_contexture.middle.validation import require_middle_for_publication
from aih_contexture.utils.gc_pause import with_paused_gc


@dataclass
class MiddleRerender:
    document: dict[str, Any]
    markdown: str
    validation: dict[str, Any]
    options: dict[str, Any]
    warnings: list[str]
    tables: list[dict[str, Any]]
    diagnostics: dict[str, Any]


CANONICAL_READING_DEFAULTS: dict[str, Any] = {
    'include_provenance_comments': False,
    'include_printed_page_comments': True,
    'include_page_header_comments': True,
    'include_page_footer_comments': True,
    'include_margin_comments': True,
    'include_page_separators': True,
    'include_blockquote_markers': True,
    'footnote_enabled': True,
    'superscript_policy': 'footnote_safe',
    'equation_output_mode': 'humanities_safe',
    'marginal_output_mode': None,
    'classical_marginalia_mode': 'off',
    'classical_text_marginalia_mode': 'separate',
    'generic_line_output_mode': 'drop',
}

READING_OPTION_ALIASES: dict[str, tuple[str, ...]] = {
    'include_provenance_comments': (
        'middle_rerender_include_provenance',
        'middle_rerender_include_provenance_comments',
    ),
    'include_printed_page_comments': ('middle_rerender_include_printed_page_comments',),
    'include_page_header_comments': ('middle_rerender_include_page_header_comments',),
    'include_page_footer_comments': ('middle_rerender_include_page_footer_comments',),
    'include_margin_comments': ('middle_rerender_include_margin_comments',),
    'include_page_separators': ('middle_rerender_include_page_separators',),
    'include_blockquote_markers': ('middle_rerender_include_blockquote_markers',),
    'footnote_enabled': ('middle_rerender_footnote_enabled',),
    'superscript_policy': ('middle_rerender_superscript_policy',),
    'equation_output_mode': ('middle_rerender_equation_output_mode',),
    'marginal_output_mode': ('middle_rerender_marginal_output_mode',),
    'classical_marginalia_mode': ('middle_rerender_classical_marginalia_mode',),
    'classical_text_marginalia_mode': ('middle_rerender_classical_text_marginalia_mode',),
    'generic_line_output_mode': ('middle_rerender_generic_line_output_mode',),
}

BOOLEAN_READING_KEYS = {
    'include_provenance_comments',
    'include_printed_page_comments',
    'include_page_header_comments',
    'include_page_footer_comments',
    'include_margin_comments',
    'include_page_separators',
    'include_blockquote_markers',
    'footnote_enabled',
}


def _normalize_option_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in BOOLEAN_READING_KEYS:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'true', '1', 'yes', 'on'}:
                return True
            if normalized in {'false', '0', 'no', 'off'}:
                return False
        elif isinstance(value, (bool, int, float)) and value in (0, 1):
            return bool(value)
        raise ValueError(f'Invalid boolean reading option {key}: {value!r}')
    if key == 'classical_marginalia_mode':
        return normalize_classical_marginalia_mode(value)
    if key == 'classical_text_marginalia_mode':
        return normalize_classical_text_marginalia_mode(value)
    if key == 'generic_line_output_mode':
        normalized = str(value).strip().lower().replace('-', '_')
        if normalized not in {'drop', 'page_comments'}:
            raise ValueError(f'Invalid generic line output mode: {value!r}')
        return normalized
    if key in {'equation_output_mode', 'superscript_policy', 'marginal_output_mode'}:
        return str(value).strip().lower().replace('-', '_')
    return value


def normalize_reading_render_options(
    explicit: dict[str, Any] | None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize reading render options with priority: explicit > snapshot > legacy defaults.

    Distinguishes unset (None or omitted) from explicit False / 'off'.
    Raises ValueError on conflicting explicit aliases.
    Excludes business inference / pipeline execution parameters from snapshot.
    """
    config = explicit or {}
    clean_snapshot: dict[str, Any] = {}
    if isinstance(snapshot, dict):
        for key in CANONICAL_READING_DEFAULTS:
            if key in snapshot and snapshot[key] is not None:
                clean_snapshot[key] = snapshot[key]
            else:
                for alias in READING_OPTION_ALIASES.get(key, ()):
                    if alias in snapshot and snapshot[alias] is not None:
                        clean_snapshot[key] = snapshot[alias]
                        break

    resolved: dict[str, Any] = {}
    for key, default_val in CANONICAL_READING_DEFAULTS.items():
        explicit_candidates: list[tuple[str, Any]] = []
        if key in config and config[key] is not None:
            explicit_candidates.append((key, _normalize_option_value(key, config[key])))

        for alias in READING_OPTION_ALIASES.get(key, ()):
            if alias in config and config[alias] is not None:
                explicit_candidates.append((alias, _normalize_option_value(key, config[alias])))

        if len(explicit_candidates) > 1:
            first_name, first_norm = explicit_candidates[0]
            for other_name, other_norm in explicit_candidates[1:]:
                if first_norm != other_norm:
                    raise ValueError(
                        f"Conflicting explicit options for '{key}': "
                        f"{first_name}={config[first_name]!r} vs {other_name}={config[other_name]!r}"
                    )

        if explicit_candidates:
            resolved[key] = explicit_candidates[0][1]
        elif key in clean_snapshot:
            resolved[key] = _normalize_option_value(key, clean_snapshot[key])
        else:
            resolved[key] = default_val

    if resolved['marginal_output_mode'] in {'line_markers', 'margin_comments', 'plain', 'drop'}:
        resolved['include_margin_comments'] = resolved['marginal_output_mode'] in {'line_markers', 'margin_comments'}

    return resolved


def effective_reading_options(
    data: Any,
    config: dict[str, Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Options a re-render of ``data`` will use: explicit > stored snapshot > defaults."""
    effective_config = config or {}
    if snapshot is None:
        doc_metadata = data.get("metadata") if isinstance(data, dict) and isinstance(data.get("metadata"), dict) else {}
        snapshot = doc_metadata.get("reading_render_options") or doc_metadata.get('effective_render_options')
        if snapshot is None and isinstance(effective_config, dict):
            snapshot = effective_config.get("reading_render_options") or effective_config.get("reading_options_snapshot")
    return normalize_reading_render_options(effective_config, snapshot=snapshot)


@with_paused_gc
def prepare_middle_rerender(
    data: dict[str, Any],
    config: dict[str, Any] | None = None,
    *,
    snapshot: dict[str, Any] | None = None,
    _render_markdown: bool = True,
) -> MiddleRerender:
    """Validate before publishing, retain source blocks, and share effective options."""
    data = decode_middle_storage(data)
    require_middle_for_publication(data)
    effective_config = config or {}

    options = effective_reading_options(data, effective_config, snapshot=snapshot)
    document = resolve_middle_for_rendering(data, {**effective_config, **options})

    # Save canonical reading options snapshot into document metadata before analysis
    if 'metadata' not in document or not isinstance(document['metadata'], dict):
        document['metadata'] = {}
    document['metadata']['reading_render_options'] = {
        k: options[k] for k in CANONICAL_READING_DEFAULTS
    }

    warnings: list[str] = []
    if 'historical_superscript_source_unavailable' in (document.get('metadata', {}).get('semantic_resolution', {}).get('warnings') or []):
        warnings.append('旧 Middle 已移除部分上标标签且没有保留原始文本，无法完整恢复；请从原始识别 JSON 重新导出。')
    requested = options['classical_marginalia_mode']
    if requested != 'off':
        capability = classical_marginalia_capabilities(document)
        if is_lean_middle(document):
            # Block boxes alone would pass the geometry check, but classical
            # analysis needs the word layer a lean Middle does not carry.
            capability = {**capability, 'status': 'unavailable', 'geometry_profile': 'lean'}
        if capability['status'] == 'unavailable':
            warnings.append('古典边码提取未执行：输入缺少可靠版面坐标，已保留原输出；请使用带坐标的 Middle 或原页复核。')
            options['classical_marginalia_mode'] = 'off'
            if options.get('marginal_output_mode') == 'drop':
                options['marginal_output_mode'] = 'plain'
            document = resolve_classical_marginalia(
                document,
                config={**effective_config, 'classical_marginalia_mode': requested},
                pdf_words_by_page=effective_config.get('classical_pdf_words_by_page'),
                evidence=effective_config.get('classical_evidence'),
            )
            if 'metadata' in document and isinstance(document['metadata'], dict):
                resolution = document['metadata'].setdefault('classical_marginalia_resolution', {})
                if isinstance(resolution, dict):
                    resolution['capabilities'] = capability
        else:
            if capability['status'] == 'partial':
                warnings.append(f"古典边码提取：{capability['geometry_pages']}/{capability['page_count']} 页具备版面坐标，其余页需复核。")
            document = resolve_classical_marginalia(
                document,
                config={**effective_config, **options},
                pdf_words_by_page=effective_config.get('classical_pdf_words_by_page'),
                evidence=effective_config.get('classical_evidence'),
            )

        review = classical_review_status(document)
        document.setdefault('metadata', {})[CLASSICAL_REVIEW_KEY] = review
        warning = classical_review_warning(review)
        if warning:
            warnings.append(warning)
    else:
        # A saved report must not keep an earlier enabled mode's review state.
        document.get('metadata', {}).pop(CLASSICAL_REVIEW_KEY, None)

    report = require_middle_for_publication(document)
    validation = {
        'ok': report.ok, 'summary': report.summary,
        'errors': [{'path': issue.path, 'message': issue.message} for issue in report.errors],
        'warnings': [{'path': issue.path, 'message': issue.message} for issue in report.warnings],
    }
    warnings.extend(f'{issue.path}: {issue.message}' for issue in report.warnings)
    tables = table_review_records(document)
    from aih_contexture.middle.reading_review import READING_REVIEW_KEY, reading_review_status
    reading_review = reading_review_status(document, tables)
    document.setdefault('metadata', {})[READING_REVIEW_KEY] = reading_review
    if any(region.get('reason') == 'unconfirmed_page_folio'
           for page in reading_review['pages'] for region in page.get('regions', [])):
        warnings.append('页码候选未确认：相关数字仍保留在正文中；请对照原页及 Middle 中的逐页核查记录。')
    if any(row['status'] == 'needs_review' for row in tables):
        warnings.append('部分表格或复杂区域的结构、合并关系未确认；请对照原页及核查记录复核。原始信息保留在 Middle 中。')

    markdown = ''
    if _render_markdown:
        from aih_contexture.middle.scholarly_markdown import _RESOLVED_RENDER_TOKEN
        token = (_RESOLVED_RENDER_TOKEN if requested == 'off'
                 and effective_config.get('marginal_detection_enabled', True)
                 and effective_config.get('semantic_profile', 'humanities') == 'humanities'
                 else None)
        page_manifest = {}
        markdown = render_middle_scholarly_markdown(
            document, **{**options, 'classical_marginalia_mode': requested},
            classical_pdf_words_by_page=effective_config.get('classical_pdf_words_by_page'),
            classical_evidence=effective_config.get('classical_evidence'),
            page_manifest_out=page_manifest, _resolved_token=token,
        )
        document.setdefault('metadata', {})['reading_page_manifest'] = page_manifest
    else:
        document.setdefault('metadata', {}).pop('reading_page_manifest', None)
    document['metadata'].pop('reading_postprocess', None)
    from aih_contexture.runtime.reading_diagnostics import (
        build_reading_diagnostics, _publication_document_owned, reading_diagnostics_enabled,
    )
    warnings = list(dict.fromkeys(warnings))
    diagnostics = build_reading_diagnostics(document, validation, warnings, tables)
    return MiddleRerender(_publication_document_owned(document), markdown, validation, options,
                          warnings if reading_diagnostics_enabled(effective_config) else [],
                          tables, diagnostics)

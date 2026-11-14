"""Optional lean Middle: keep block geometry, omit per-word spans.

``full`` (default) keeps every word span, which classical marginalia, span
overlays and full JSON need. ``lean`` drops word spans before semantic
resolution, so save, re-render and storage no longer scale with the number of
words. Block text, bbox, attributes and page structure are untouched.

Lean is only applied where nothing requested depends on word geometry; any
such request keeps ``full``. A lean Middle records ``geometry_profile: lean``
in its metadata, so later re-renders know the word layer is absent.
"""
from __future__ import annotations

from typing import Any

CONFIG_KEY = 'middle_geometry_profile'
METADATA_KEY = 'geometry_profile'
FULL = 'full'
LEAN = 'lean'


def normalize_geometry_profile(value: Any) -> str:
    if value is None or value == '':
        return FULL
    normalized = str(value).strip().lower()
    if normalized in {FULL, LEAN}:
        return normalized
    raise ValueError(f'Invalid Middle geometry profile: {value!r}')


def lean_blockers(
    options: dict[str, Any],
    *,
    emit_span_overlay: bool = False,
    emit_middle_full_json: bool = False,
) -> list[str]:
    """Requests that need word spans; any of them keeps the full profile."""
    reasons = []
    if (options.get('classical_marginalia_mode') or 'off') != 'off':
        reasons.append('classical_marginalia_mode')
    if emit_span_overlay:
        reasons.append('emit_span_overlay')
    if emit_middle_full_json:
        reasons.append('emit_middle_full_json')
    return reasons


def is_lean_middle(data: Any) -> bool:
    metadata = data.get('metadata') if isinstance(data, dict) else None
    return isinstance(metadata, dict) and metadata.get(METADATA_KEY) == LEAN


def strip_word_spans(data: dict[str, Any]) -> dict[str, Any]:
    """Return a lean view without mutating ``data``.

    Pages and blocks are shallow-copied without ``spans`` (or their encoded
    ``span_storage`` form); every other value is shared with the source.
    """
    from aih_contexture.middle.storage import STORAGE_SCHEMA

    def block_view(block):
        view = {key: value for key, value in block.items() if key not in ('spans', 'span_storage')}
        children = block.get('children')
        if isinstance(children, list):
            view['children'] = [block_view(child) if isinstance(child, dict) else child for child in children]
        return view

    result = dict(data)
    if result.get('schema_version') == STORAGE_SCHEMA and isinstance(result.get('storage_encoding'), dict):
        # Only spans are ever encoded; without them the document is canonical.
        result['schema_version'] = result['storage_encoding'].get('middle_schema_version')
        result.pop('storage_encoding')
    pages = []
    for page in data.get('pages') or []:
        if isinstance(page, dict):
            page = dict(page)
            if isinstance(page.get('blocks'), list):
                page['blocks'] = [block_view(b) if isinstance(b, dict) else b for b in page['blocks']]
        pages.append(page)
    result['pages'] = pages
    metadata = dict(result.get('metadata') or {}) if isinstance(result.get('metadata'), dict) else {}
    metadata[METADATA_KEY] = LEAN
    result['metadata'] = metadata
    return result

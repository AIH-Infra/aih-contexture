"""The numeric projection shared by persisted evidence and its consumers."""
from __future__ import annotations

import copy

STORAGE_DECIMALS = 4
COORDINATE_QUANTUM = 10 ** -STORAGE_DECIMALS

# Exact JSON leaf types returned unchanged. Subclasses take the general path.
_LEAF_TYPES = frozenset({str, int, bool, type(None)})


def storage_number(value):
    return round(value, STORAGE_DECIMALS) if isinstance(value, float) else value


def storage_numbers(value):
    """Copy JSON evidence without dropping empty fields or changing source text.

    Exact dict/list/float/leaf types are dispatched by ``type`` and leaves are
    handled inline, because this runs over every word span of a book. Any
    other type keeps the original ``isinstance`` semantics.
    """
    kind = type(value)
    if kind is dict:
        return {key: item if type(item) in _LEAF_TYPES
                else round(item, STORAGE_DECIMALS) if type(item) is float
                else storage_numbers(item)
                for key, item in value.items()}
    if kind is list:
        return [item if type(item) in _LEAF_TYPES
                else round(item, STORAGE_DECIMALS) if type(item) is float
                else storage_numbers(item)
                for item in value]
    if kind is float:
        return round(value, STORAGE_DECIMALS)
    if kind in _LEAF_TYPES:
        return value
    return _storage_numbers_general(value)


def _storage_numbers_general(value):
    if isinstance(value, float):
        return storage_number(value)
    if isinstance(value, list):
        return [storage_numbers(item) for item in value]
    if isinstance(value, dict):
        return {key: storage_numbers(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(storage_numbers(item) for item in value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return copy.deepcopy(value)

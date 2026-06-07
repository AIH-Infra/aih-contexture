from __future__ import annotations

"""Read-only backend capability catalog.

The catalog is intentionally descriptive in the 0.5 baseline: it reports
implemented/planned backend capabilities and optional diagnostics. Builder
selection still lives in ``aih_contexture.backends.pipeline``. Registry
``builder_factory`` fields are reserved for a future factory refactor and are
not exposed by this catalog API.
"""

from dataclasses import asdict
from typing import Any

from aih_contexture.backends.layout import default_layout_registry
from aih_contexture.backends.ocr import default_ocr_registry
from aih_contexture.backends.vlm import default_vlm_registry
from aih_contexture.backends.diagnostics import layout_backend_status, ocr_backend_status, vlm_backend_status


def list_layout_backends(
    implemented_only: bool = True,
    *,
    include_status: bool = False,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    backends = []
    for name in default_layout_registry.names(implemented_only=implemented_only):
        data = asdict(default_layout_registry.capabilities(name))
        if include_status:
            data["status"] = layout_backend_status(name, config=config).to_dict()
        backends.append(data)
    return backends


def list_ocr_backends(
    implemented_only: bool = True,
    *,
    include_status: bool = False,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    backends = []
    for name in default_ocr_registry.names(implemented_only=implemented_only):
        data = asdict(default_ocr_registry.capabilities(name))
        if include_status:
            data["status"] = ocr_backend_status(name, config=config).to_dict()
        backends.append(data)
    return backends


def list_vlm_backends(
    implemented_only: bool = True,
    *,
    include_status: bool = False,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    backends = []
    for name in default_vlm_registry.names(implemented_only=implemented_only):
        data = asdict(default_vlm_registry.capabilities(name))
        if include_status:
            data["status"] = vlm_backend_status(name, config=config).to_dict()
        backends.append(data)
    return backends


def backend_catalog(
    implemented_only: bool = True,
    *,
    include_status: bool = False,
    config: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "layout": list_layout_backends(
            implemented_only=implemented_only,
            include_status=include_status,
            config=config,
        ),
        "ocr": list_ocr_backends(
            implemented_only=implemented_only,
            include_status=include_status,
            config=config,
        ),
        "vlm": list_vlm_backends(
            implemented_only=implemented_only,
            include_status=include_status,
            config=config,
        ),
    }

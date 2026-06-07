from __future__ import annotations

from typing import Any

from aih_contexture.config.parser import ConfigParser
from aih_contexture.runtime.job import ContextureJob, normalize_page_range
from aih_contexture.runtime.ui_config import build_config_dict


def config_from_cli_options(options: dict[str, Any]) -> dict[str, Any]:
    parser = ConfigParser(dict(options))
    return parser.generate_config_dict()


def config_from_ui_params(params: dict[str, Any]) -> dict[str, Any]:
    return build_config_dict(dict(params))


def config_from_api_request(request: dict[str, Any]) -> dict[str, Any]:
    payload = dict(request)
    config = dict(payload.pop("config", {}) or {})
    config.update({k: v for k, v in payload.items() if v is not None})
    if "page_range" in config:
        config["page_range"] = normalize_page_range(config["page_range"])
    return config


def job_from_payload(payload: dict[str, Any]) -> ContextureJob:
    return ContextureJob.from_dict(payload)

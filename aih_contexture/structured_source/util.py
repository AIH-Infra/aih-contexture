from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_slug(value: str, fallback: str = "document") -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return value[:100] or fallback


def local_name(tag: Any) -> str:
    value = str(tag)
    return value.rsplit("}", 1)[-1] if "}" in value else value.rsplit(":", 1)[-1]


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_zip_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return bool(normalized) and not path.is_absolute() and ".." not in path.parts and not re.match(r"^[A-Za-z]:", normalized)


def path_record(path: Path, records: int | None = None, sorting: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    result: dict[str, Any] = {"path": path.name, "sha256": sha256_bytes(data), "bytes": len(data)}
    if records is not None:
        result["records"] = records
    if sorting:
        result["sorting"] = sorting
    return result

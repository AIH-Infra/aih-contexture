"""Safe reuse of completed file conversions.

Only results carrying a completion manifest written after a successful save can
be reused. Legacy files without a manifest remain available on disk, but are
never treated as proof that a conversion succeeded.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REUSE_MANIFEST_NAME = ".contexture_reuse.json"
REUSE_SCHEMA_VERSION = 1
_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
    "cookie",
)
_SECRET_QUERY_PARTS = ("key", "token", "secret", "password", "auth", "credential")
_NON_CONTENT_CONFIG_KEYS = {
    "output_dir",
    "skip_existing",
    "workers",
    "total_torch_threads",
    "chunk_idx",
    "num_chunks",
    "max_files",
    "max_tasks_per_worker",
    "debug_print",
    "disable_tqdm",
}


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_reuse_identity(
    source_path: str | os.PathLike[str],
    *,
    source_name: str | os.PathLike[str] | None,
    config: Mapping[str, Any],
    output_formats: Iterable[str],
) -> dict[str, Any]:
    """Build a deterministic identity without persisting credential values."""
    source_name_value = Path(os.fspath(source_name or source_path)).name
    formats = [str(value).strip().lower() for value in output_formats]
    relevant_config = reuse_config(config)
    fingerprint_payload = {
        "source": {"name": source_name_value, "sha256": sha256_file(source_path)},
        "configuration": _config_for_fingerprint(relevant_config),
        "output_formats": formats,
    }
    serialized = _canonical_json(fingerprint_payload)
    return {
        "source": fingerprint_payload["source"],
        "configuration": _config_for_manifest(relevant_config),
        "config_sha256": hashlib.sha256(
            _canonical_json(fingerprint_payload["configuration"]).encode("utf-8")
        ).hexdigest(),
        "output_formats": formats,
        "fingerprint": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }


def reuse_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Remove scheduling and presentation controls that do not change content."""
    return {
        str(key): value
        for key, value in config.items()
        if str(key).lower() not in _NON_CONTENT_CONFIG_KEYS
    }


def _config_for_fingerprint(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_key(key_text):
                normalized[key_text] = {"secret_sha256": _hash_value(item)}
            else:
                normalized[key_text] = _config_for_fingerprint(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_config_for_fingerprint(item) for item in value]
    if isinstance(value, set):
        return sorted((_config_for_fingerprint(item) for item in value), key=_canonical_json)
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "size_bytes": len(value)}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _config_for_manifest(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized = {}
        for key, item in value.items():
            key_text = str(key)
            normalized[key_text] = "[REDACTED]" if _is_secret_key(key_text) else _config_for_manifest(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_config_for_manifest(item) for item in value]
    if isinstance(value, set):
        return sorted((_config_for_manifest(item) for item in value), key=_canonical_json)
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "size_bytes": len(value)}
    if isinstance(value, str):
        return _redact_url_credentials(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _is_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in _SECRET_KEY_PARTS)


def _hash_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(_config_for_fingerprint(value)).encode("utf-8")).hexdigest()


def _redact_url_credentials(value: str) -> str:
    if "://" not in value:
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.netloc:
        return value
    hostname = parts.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = parts.port
    except ValueError:
        # Invalid ports should not make manifest creation fail, and should not
        # preserve a possibly credential-bearing original URL verbatim.
        port = None
    if port is not None:
        hostname = f"{hostname}:{port}"
    query = [
        (key, "[REDACTED]" if any(part in key.lower() for part in _SECRET_QUERY_PARTS) else item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, hostname, parts.path, urlencode(query), parts.fragment))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def find_reusable_result(
    output_root: str | os.PathLike[str],
    *,
    identity: Mapping[str, Any],
    expected_primary_names: Iterable[str],
) -> dict[str, Any] | None:
    """Find the newest intact success whose complete identity matches."""
    root = Path(output_root)
    if not root.is_dir():
        return None

    expected_names = {str(name) for name in expected_primary_names}
    matches: list[tuple[float, Path, list[str]]] = []
    # Document outputs are direct children of output_root. Keep lookup bounded
    # so a large output tree with many page resources is cheap to scan.
    for manifest_path in root.glob(f"*/{REUSE_MANIFEST_NAME}"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        if manifest.get("schema_version") != REUSE_SCHEMA_VERSION or manifest.get("status") != "succeeded":
            continue
        if manifest.get("fingerprint") != identity.get("fingerprint"):
            continue
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        verified: list[str] = []
        valid = True
        for item in artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                valid = False
                break
            artifact = _contained_artifact(manifest_path.parent, item["path"])
            if artifact is None or not artifact.is_file():
                valid = False
                break
            try:
                if artifact.stat().st_size != int(item.get("size_bytes", -1)):
                    valid = False
                    break
                if sha256_file(artifact) != item.get("sha256"):
                    valid = False
                    break
            except (OSError, TypeError, ValueError):
                valid = False
                break
            verified.append(os.fspath(artifact))
        if not valid:
            continue
        primary_names = manifest.get("primary_names")
        if (
            not isinstance(primary_names, list)
            or any(not isinstance(name, str) for name in primary_names)
            or not expected_names.issubset(set(primary_names))
        ):
            continue
        if not expected_names.issubset({Path(path).name for path in verified}):
            continue
        try:
            modified = manifest_path.stat().st_mtime
        except OSError:
            continue
        matches.append((modified, manifest_path.parent, verified))

    if not matches:
        return None
    _, output_dir, files = max(matches, key=lambda match: (match[0], os.fspath(match[1])))
    return {"output_dir": os.fspath(output_dir), "files": sorted(files)}


def result_is_reusable(result: Any) -> bool:
    """Return False for runtime results that are explicitly partial or failed."""
    if getattr(result, "failed_pages", None):
        return False
    if bool(getattr(result, "partial", False)):
        return False
    metadata = getattr(result, "metadata", None)
    if isinstance(metadata, Mapping):
        if metadata.get("partial") is True or str(metadata.get("status", "")).lower() in {
            "failed",
            "partial",
            "cancelled",
        }:
            return False
    diagnostics = getattr(result, "diagnostics", None)
    if isinstance(diagnostics, list) and any(
        isinstance(item, Mapping) and item.get("ok") is False for item in diagnostics
    ):
        return False
    return True


def expected_image_paths(result: Any, output_dir: str | os.PathLike[str]) -> list[str] | None:
    """Return relative image paths, or None if a requested image was not saved."""
    root = Path(output_dir).resolve()
    images = getattr(result, "images", None) or {}
    if not isinstance(images, Mapping):
        return None
    names: list[str] = []
    for raw_name in images:
        name = Path(os.fspath(raw_name))
        if name.is_absolute() or ".." in name.parts:
            return None
        candidate = (root / name).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        names.append(relative)
    return names


def write_reuse_manifest(
    output_dir: str | os.PathLike[str],
    *,
    identity: Mapping[str, Any],
    primary_names: Iterable[str],
    required_paths: Iterable[str] = (),
    source_path: str | os.PathLike[str] | None = None,
    status: str = "succeeded",
) -> str:
    """Atomically mark a completed result reusable after verifying its outputs."""
    root = Path(output_dir).resolve()
    artifacts = _artifact_records(root)
    primary_names_list = sorted({str(name) for name in primary_names})
    artifact_paths = {item["path"] for item in artifacts}
    artifact_names = {Path(item["path"]).name for item in artifacts}
    required_paths_list = sorted({Path(path).as_posix() for path in required_paths})
    if status != "succeeded":
        raise ValueError("Only successful results can be marked reusable")
    if source_path is not None:
        expected_source_hash = (identity.get("source") or {}).get("sha256")
        if not expected_source_hash or sha256_file(source_path) != expected_source_hash:
            raise ValueError("Cannot mark result reusable: source changed during conversion")
    if not primary_names_list or not set(primary_names_list).issubset(artifact_names):
        raise ValueError("Cannot mark result reusable: a requested primary artifact is missing")
    if not set(required_paths_list).issubset(artifact_paths):
        raise ValueError("Cannot mark result reusable: a required artifact is missing")
    manifest = {
        "schema_version": REUSE_SCHEMA_VERSION,
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "fingerprint": identity["fingerprint"],
        "source": identity["source"],
        "configuration": identity["configuration"],
        "config_sha256": identity["config_sha256"],
        "output_formats": list(identity["output_formats"]),
        "primary_names": primary_names_list,
        "required_paths": required_paths_list,
        "artifacts": artifacts,
    }
    target = root / REUSE_MANIFEST_NAME
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return os.fspath(target)


def primary_artifact_name(base_name: str, output_format: str) -> str:
    normalized_format = str(output_format).strip().lower()
    extension = {"markdown": "md", "html": "html", "json": "json", "chunks": "json"}.get(normalized_format)
    if extension is None:
        raise ValueError(f"Unsupported output format for result reuse: {output_format}")
    return f"{base_name}.{extension}"


def _artifact_records(root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == REUSE_MANIFEST_NAME or path.name.endswith(".tmp"):
            continue
        try:
            relative = path.resolve().relative_to(root).as_posix()
            stat = path.stat()
            digest = sha256_file(path)
        except (OSError, ValueError):
            continue
        records.append({"path": relative, "size_bytes": stat.st_size, "sha256": digest})
    return records


def _contained_artifact(root: Path, relative_name: str) -> Path | None:
    relative = Path(relative_name)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    root_resolved = root.resolve()
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    return candidate

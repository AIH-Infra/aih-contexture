from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .errors import StructuredSourceError
from .renderer import render_scholarly_html, render_scholarly_markdown
from .util import path_record, sha256_bytes, stable_slug
from .validation import ARRAY_KEYS, assert_valid_source_document


TRANSFORM_VERSION = "contexture-structured-source/0.2.1"


def _json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    return text.encode("utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]], emit_index: bool) -> tuple[int, Path | None]:
    offsets: list[int] = []
    count = 0
    with path.open("wb") as stream:
        for record in records:
            offsets.append(stream.tell())
            stream.write(_json_bytes(record))
            count += 1
        stream.flush()
        os.fsync(stream.fileno())
    index_path = None
    if emit_index and offsets:
        index_path = path.with_suffix(path.suffix + ".idx")
        _write_bytes(index_path, "".join(f"{offset}\n" for offset in offsets).encode("ascii"))
    return count, index_path


def write_source_package(
    document: dict[str, Any],
    output_dir: str | os.PathLike[str],
    *,
    source_data: bytes,
    source_name: str,
    raw_artifacts: dict[str, bytes] | None = None,
    emit_line_indexes: bool = False,
    markdown: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    assert_valid_source_document(document)
    destination_root = Path(output_dir).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    stem = stable_slug(Path(source_name).stem)
    version_payload = f"{document['source']['sha256']}|{document['source']['profile']}|{TRANSFORM_VERSION}".encode("utf-8")
    document_version_sha = sha256_bytes(version_payload)
    version = document_version_sha[:12]
    destination = destination_root / f"{stem}.source.{version}"
    if destination.exists():
        return destination, validate_source_package(destination)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{stem}.source.", dir=destination_root))
    try:
        components: dict[str, dict[str, Any]] = {}
        metadata_payload = {
            "document_id": document["id"], "source": document["source"], "identity": document["identity"],
            "metadata": document["metadata"], "raw_metadata": document["raw_metadata"],
            "resources": document["resources"], "provenance": document["provenance"],
            "extensions": document["extensions"],
        }
        metadata_path = temp_dir / "metadata.json"
        _write_bytes(metadata_path, _json_bytes(metadata_payload, pretty=True))
        components["metadata"] = path_record(metadata_path, 1, "object_keys")

        for key in ARRAY_KEYS:
            component_path = temp_dir / f"{key}.jsonl"
            records = list(document[key])
            count, index_path = _write_jsonl(component_path, records, emit_line_indexes)
            sorting = "order" if key in {"blocks", "anchors"} else "preorder" if key == "structures" else "sequence"
            components[key] = path_record(component_path, count, sorting)
            if index_path:
                components[f"{key}_index"] = path_record(index_path, count, "record_number")

        markdown_path = temp_dir / "document.md"
        _write_bytes(markdown_path, (markdown if markdown is not None else render_scholarly_markdown(document)).encode("utf-8"))
        components["markdown"] = path_record(markdown_path, None, "reading_order")

        document_json_path = temp_dir / "document.json"
        _write_bytes(document_json_path, _json_bytes(document, pretty=True))
        components["document_json"] = path_record(document_json_path, 1, "object_keys")

        html_path = temp_dir / "document.html"
        _write_bytes(html_path, render_scholarly_html(document).encode("utf-8"))
        components["html"] = path_record(html_path, None, "reading_order")

        original_suffix = Path(source_name).suffix.lower() or ".bin"
        original_path = temp_dir / f"original{original_suffix}"
        _write_bytes(original_path, source_data)
        components["original"] = path_record(original_path, 1, "source_bytes")
        for name, content in sorted((raw_artifacts or {}).items()):
            raw_path = temp_dir / stable_slug(name, "raw-metadata.bin")
            _write_bytes(raw_path, content)
            components[f"raw:{raw_path.name}"] = path_record(raw_path, 1, "source_order")

        ingest_manifest = {
            "schema_version": "contexture-source-ingest/0.1", "adapter": document["source"]["profile"],
            "transform_version": TRANSFORM_VERSION,
            "source_sha256": document["source"]["sha256"], "warnings": [],
            "statistics": {key: len(document[key]) for key in ARRAY_KEYS},
        }
        ingest_path = temp_dir / "ingest_manifest.json"
        _write_bytes(ingest_path, _json_bytes(ingest_manifest, pretty=True))
        components["ingest_manifest"] = path_record(ingest_path, 1, "object_keys")

        manifest = {
            "package_schema": "contexture-source-package/0.1", "document_schema": document["schema_version"],
            "document_id": document["id"], "document_version_id": f"sha256:{document_version_sha}",
            "source_sha256": document["source"]["sha256"], "components": components,
            "ordering": {"blocks": "order", "structures": "preorder", "others": "sequence"},
        }
        manifest_path = temp_dir / "source_document.json"
        _write_bytes(manifest_path, _json_bytes(manifest, pretty=True))
        validate_source_package(temp_dir)
        if destination.exists():
            shutil.rmtree(temp_dir)
            return destination, validate_source_package(destination)
        try:
            os.replace(temp_dir, destination)
        except (FileExistsError, PermissionError):
            if not destination.exists():
                raise
            shutil.rmtree(temp_dir, ignore_errors=True)
            return destination, validate_source_package(destination)
        return destination, manifest
    except BaseException:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def validate_source_package(package_dir: str | os.PathLike[str]) -> dict[str, Any]:
    root = Path(package_dir)
    manifest_path = root / "source_document.json"
    if not manifest_path.is_file():
        raise StructuredSourceError("Package manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_schema") != "contexture-source-package/0.1":
        raise StructuredSourceError("Unsupported package schema")
    original = manifest.get("components", {}).get("original") or {}
    if original.get("sha256") != manifest.get("source_sha256"):
        raise StructuredSourceError("Original artifact does not match source_sha256")
    for name, spec in manifest.get("components", {}).items():
        path = root / spec["path"]
        if not path.is_file():
            raise StructuredSourceError(f"Missing package component: {name}")
        data = path.read_bytes()
        if sha256_bytes(data) != spec.get("sha256") or len(data) != spec.get("bytes"):
            raise StructuredSourceError(f"Package component checksum mismatch: {name}")
        if path.suffix == ".jsonl":
            lines = data.splitlines()
            if any(not line.strip() for line in lines):
                raise StructuredSourceError(f"Blank JSONL record: {name}")
            for line in lines:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise StructuredSourceError(f"Non-object JSONL record: {name}")
            if len(lines) != spec.get("records"):
                raise StructuredSourceError(f"JSONL record count mismatch: {name}")
    return manifest

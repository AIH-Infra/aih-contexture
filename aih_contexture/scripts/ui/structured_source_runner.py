from __future__ import annotations

import os
import shutil
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from aih_contexture.middle.adapters.markdown import markdown_to_middle_document
from aih_contexture.runtime.run_summary import ensure_processing_id, utc_now_iso, write_document_summary
from aih_contexture.scripts.ui.batch_inputs import input_file_objects
from aih_contexture.runtime.output_contract import document_output_basename
from aih_contexture.scripts.ui.task_outputs import get_output_folder, record_processed_outputs, register_document_summary
from aih_contexture.structured_source import StructuredSourceConverter
from aih_contexture.structured_source.util import stable_slug


def materialize_readable_outputs(result, source_name: str, output_root: str | os.PathLike[str] | None = None) -> list[str]:
    """Expose reader-facing artifacts with the complete source-derived basename.

    The versioned ``*.source.<hash>`` directory remains an internal package
    implementation detail; the document output directory contains readable,
    complete-name artifacts for users.
    """
    package = Path(result.package_path)
    destination_root = Path(output_root) if output_root is not None else package.parent
    destination_root.mkdir(parents=True, exist_ok=True)
    base = document_output_basename(source_name)
    paths: list[str] = []
    for suffix, component in (("json", "document.json"), ("md", "document.md"), ("html", "document.html")):
        destination = destination_root / f"{base}.{suffix}"
        shutil.copyfile(package / component, destination)
        paths.append(os.fspath(destination))
    if output_root is not None:
        middle_path = destination_root / f"{base}_middle.json"
        middle = markdown_to_middle_document(result.markdown, source_name=source_name, backend="structured_source")
        middle_path.write_text(json.dumps(middle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(os.fspath(middle_path))
        manifest_path = destination_root / f"{base}_source_document.json"
        shutil.copyfile(package / "source_document.json", manifest_path)
        paths.append(os.fspath(manifest_path))
    return paths


def run_structured_source_batch(
    *, st, uploaded_files, upload_mode: str, output_dir: str, emit_line_indexes: bool,
    max_workers: int, cancel, ctx: dict,
) -> list[str]:
    processing_id = ensure_processing_id(ctx, output_dir)
    ctx["mode"] = "structured_source"
    ctx.setdefault("batch_started_at", utc_now_iso())
    file_objects = input_file_objects(upload_mode, uploaded_files, ctx)
    all_outputs: list[str] = []

    def convert_one(item, file_index: int):
        content, name = item
        started_clock = time.perf_counter()
        started_at = utc_now_iso()
        file_output_dir = get_output_folder(output_dir, name, file_index=file_index)
        converter = StructuredSourceConverter({"output_dir": file_output_dir, "emit_line_indexes": emit_line_indexes})
        try:
            if isinstance(content, (str, os.PathLike)):
                result = converter(os.fspath(content))
            else:
                result = converter.convert_bytes(bytes(content), name)
        except Exception as exc:
            # P1-7: 失败文件也要留下 run_summary.json。
            summary_path = write_document_summary(
                output_dir=file_output_dir, source_name=name, processing_id=processing_id,
                file_index=file_index + 1, mode="structured_source", strategy="source_ingest",
                models={}, config={"emit_line_indexes": emit_line_indexes},
                started_at=started_at, finished_at=utc_now_iso(),
                elapsed_seconds=time.perf_counter() - started_clock, status="failed",
                page_count=None, output_paths=[], errors=[f"{type(exc).__name__}: {exc}"],
                source_path=(content if isinstance(content, (str, os.PathLike)) else None),
            )
            raise
        readable_outputs = materialize_readable_outputs(result, name, file_output_dir)
        package = Path(result.package_path)
        archive_base = Path(file_output_dir) / f"{document_output_basename(name)}.source_package"
        archive = shutil.make_archive(os.fspath(archive_base), "zip", root_dir=package)
        document = result.document or {}
        summary_path = write_document_summary(
            output_dir=file_output_dir, source_name=name, processing_id=processing_id,
            file_index=file_index + 1, mode="structured_source", strategy="source_ingest",
            models={}, config={"emit_line_indexes": emit_line_indexes},
            started_at=started_at, finished_at=utc_now_iso(),
            elapsed_seconds=time.perf_counter() - started_clock, status="succeeded",
            page_count=None,
            extra_result={
                "structure_count": len(document.get("structures", []) or []),
                "block_count": len(document.get("blocks", []) or []),
            },
            output_paths=[archive, *readable_outputs], source_path=(content if isinstance(content, (str, os.PathLike)) else None),
        )
        return name, result, archive, readable_outputs, summary_path


    workers = max(1, min(int(max_workers), len(file_objects), 16))
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(convert_one, item, file_index): item[1]
            for file_index, item in enumerate(file_objects)
        }
        completed = 0
        for future in as_completed(futures):
            if cancel.is_set():
                ctx["status"] = "cancelled"
                break
            name = futures[future]
            try:
                _, result, archive, readable_outputs, summary_path = future.result()
                paths = [archive, *readable_outputs]
                all_outputs.extend(paths)
                record_processed_outputs(ctx, name, paths)
                register_document_summary(ctx, summary_path)
                stats = result.package_manifest["components"]
                st.success(f"{name}: {stats['blocks']['records']} blocks, {stats['structures']['records']} structures")
            except Exception as exc:
                failures.append((name, str(exc)))
                st.error(f"{name}: {exc}")
            completed += 1
            ctx["progress"] = completed / len(file_objects)
    if failures:
        st.warning(f"结构化源导入完成，但 {len(failures)} 个文件失败")
    elif ctx.get("status") != "cancelled":
        st.success(f"结构化源导入完成：{len(file_objects)} 个文件")
    return all_outputs

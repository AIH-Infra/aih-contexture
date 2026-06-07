from __future__ import annotations

import gc
import io
import os
import tempfile
import time
from typing import Iterable

from pypdf import PdfReader


UPLOAD_MODE = "上传文件"


def input_file_objects(upload_mode: str, uploaded_files: Iterable, ctx: dict | None = None) -> list[tuple[object, str]]:
    if upload_mode == UPLOAD_MODE:
        if ctx is not None and ctx.get("_preread_files") is not None:
            return list(ctx["_preread_files"])
        return [(file_obj.getvalue(), file_obj.name) for file_obj in uploaded_files]
    return [(os.fspath(file_obj), os.path.basename(os.fspath(file_obj))) for file_obj in uploaded_files]


def materialize_pdf_batch(batch_objects: Iterable[tuple[object, str]], upload_mode: str) -> tuple[list[tuple[str, str]], list[str]]:
    batch_file_list: list[tuple[str, str]] = []
    batch_temp_files: list[str] = []

    for file_content, file_name in batch_objects:
        if upload_mode == UPLOAD_MODE:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                content = file_content if isinstance(file_content, bytes) else file_content.getvalue()
                tmp.write(content)
                tmp.flush()
                os.fsync(tmp.fileno())
                batch_file_list.append((tmp.name, file_name))
                batch_temp_files.append(tmp.name)
        else:
            batch_file_list.append((os.fspath(file_content), file_name))

    return batch_file_list, batch_temp_files


def check_file_accessible(file_path: str | os.PathLike[str]) -> bool:
    try:
        with open(file_path, "rb") as f:
            f.read(1024)
        return True
    except (PermissionError, OSError):
        return False


def pdf_page_count(pdf_source) -> int:
    return len(PdfReader(pdf_source).pages)


def validate_single_page_batch(
    file_objects: Iterable[tuple[object, str]],
    upload_mode: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, int]]]:
    invalid_files: list[tuple[str, str]] = []
    multi_page_files: list[tuple[str, int]] = []

    for file_content, file_name in file_objects:
        try:
            pdf_source = io.BytesIO(file_content) if upload_mode == UPLOAD_MODE else file_content
            page_count = pdf_page_count(pdf_source)
        except Exception as exc:
            invalid_files.append((file_name, str(exc)))
            continue

        if page_count != 1:
            multi_page_files.append((file_name, page_count))

    return invalid_files, multi_page_files


def safe_cleanup_temp_files(temp_files: Iterable[str], max_retries: int = 3, delay: float = 1.0) -> list[str]:
    gc.collect()

    failed_files: list[str] = []
    for tmp_path in temp_files:
        if not os.path.exists(tmp_path):
            continue

        success = False
        for attempt in range(max_retries):
            try:
                os.unlink(tmp_path)
                success = True
                break
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    gc.collect()
            except Exception:
                break

        if not success and os.path.exists(tmp_path):
            failed_files.append(tmp_path)

    return failed_files

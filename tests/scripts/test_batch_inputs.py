from pathlib import Path

from pypdf import PdfWriter

from aih_contexture.scripts.ui.batch_inputs import (
    check_file_accessible,
    input_file_objects,
    materialize_pdf_batch,
    pdf_page_count,
    safe_cleanup_temp_files,
    validate_single_page_batch,
)


class UploadedFile:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content

    def getvalue(self):
        return self._content


def test_input_file_objects_uses_preread_uploads_when_available():
    ctx = {"_preread_files": [(b"pdf", "doc.pdf")]}

    result = input_file_objects("上传文件", [UploadedFile("ignored.pdf", b"ignored")], ctx)

    assert result == [(b"pdf", "doc.pdf")]


def test_input_file_objects_reads_uploads_without_preread_context():
    result = input_file_objects("上传文件", [UploadedFile("doc.pdf", b"pdf")], {})

    assert result == [(b"pdf", "doc.pdf")]


def test_input_file_objects_uses_paths_for_folder_mode(tmp_path: Path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"pdf")

    result = input_file_objects("选择文件夹", [path], {})

    assert result == [(str(path), "doc.pdf")]


def test_materialize_pdf_batch_writes_upload_bytes_and_cleanup_removes_them():
    batch_file_list, batch_temp_files = materialize_pdf_batch([(b"pdf-bytes", "doc.pdf")], "上传文件")

    try:
        assert batch_file_list == [(batch_temp_files[0], "doc.pdf")]
        assert Path(batch_temp_files[0]).read_bytes() == b"pdf-bytes"
    finally:
        failed = safe_cleanup_temp_files(batch_temp_files, delay=0)

    assert failed == []
    assert not Path(batch_temp_files[0]).exists()


def test_materialize_pdf_batch_keeps_folder_paths_without_temp_files(tmp_path: Path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"pdf")

    batch_file_list, batch_temp_files = materialize_pdf_batch([(path, "doc.pdf")], "选择文件夹")

    assert batch_file_list == [(str(path), "doc.pdf")]
    assert batch_temp_files == []


def _write_blank_pdf(path: Path, page_count: int) -> None:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    with open(path, "wb") as f:
        writer.write(f)


def test_check_file_accessible_returns_true_for_readable_file(tmp_path: Path):
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"pdf")

    assert check_file_accessible(path) is True


def test_pdf_page_count_reads_pdf_path(tmp_path: Path):
    path = tmp_path / "doc.pdf"
    _write_blank_pdf(path, 3)

    assert pdf_page_count(path) == 3


def test_validate_single_page_batch_reports_multi_page_and_invalid_uploads(tmp_path: Path):
    single = tmp_path / "single.pdf"
    multi = tmp_path / "multi.pdf"
    _write_blank_pdf(single, 1)
    _write_blank_pdf(multi, 2)

    invalid_files, multi_page_files = validate_single_page_batch(
        [
            (single.read_bytes(), "single.pdf"),
            (multi.read_bytes(), "multi.pdf"),
            (b"not a pdf", "broken.pdf"),
        ],
        "上传文件",
    )

    assert invalid_files and invalid_files[0][0] == "broken.pdf"
    assert multi_page_files == [("multi.pdf", 2)]


def test_validate_single_page_batch_accepts_folder_paths(tmp_path: Path):
    single = tmp_path / "single.pdf"
    _write_blank_pdf(single, 1)

    invalid_files, multi_page_files = validate_single_page_batch(
        [(str(single), "single.pdf")],
        "选择文件夹",
    )

    assert invalid_files == []
    assert multi_page_files == []

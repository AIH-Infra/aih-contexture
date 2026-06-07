from aih_contexture.scripts.ui.task_state import (
    attach_preread_files,
    initial_proc_context,
    preread_uploaded_files,
    sync_proc_context_to_session,
)


class Upload:
    def __init__(self, name, data):
        self.name = name
        self._data = data

    def getvalue(self):
        return self._data


def test_initial_proc_context_preserves_status_and_ocr_resume_fields():
    ctx = initial_proc_context(
        status="running",
        ocr_paused=True,
        ocr_pause_info={"batch": 2},
        ocr_resume_batch_start=10,
    )

    assert ctx["status"] == "running"
    assert ctx["progress"] == 0.0
    assert ctx["processed_files"] == {}
    assert ctx["ocr_paused"] is True
    assert ctx["ocr_pause_info"] == {"batch": 2}
    assert ctx["ocr_resume_batch_start"] == 10


def test_preread_uploaded_files_and_attach_to_context():
    uploads = [Upload("a.pdf", b"a"), Upload("b.pdf", b"b")]
    ctx = {}

    assert preread_uploaded_files(uploads) == [(b"a", "a.pdf"), (b"b", "b.pdf")]
    assert attach_preread_files(ctx, uploads) == [(b"a", "a.pdf"), (b"b", "b.pdf")]
    assert ctx["_preread_files"] == [(b"a", "a.pdf"), (b"b", "b.pdf")]


def test_sync_proc_context_to_session_merges_outputs_and_resume_state():
    session = {"processed_files": {"old": [{"path": "old.md"}]}}
    ctx = {
        "last_zip_path": "bundle.zip",
        "last_zip_name": "bundle.zip",
        "processed_files": {"new": [{"path": "new.md"}]},
        "ocr_paused": True,
        "ocr_pause_info": {"error": "crash"},
        "ocr_resume_batch_start": 5,
    }

    sync_proc_context_to_session(ctx, session)

    assert session["last_zip_path"] == "bundle.zip"
    assert session["last_zip_name"] == "bundle.zip"
    assert session["processed_files"]["old"] == [{"path": "old.md"}]
    assert session["processed_files"]["new"] == [{"path": "new.md"}]
    assert session["ocr_paused"] is True
    assert session["ocr_pause_info"] == {"error": "crash"}
    assert session["ocr_resume_batch_start"] == 5

import threading

from aih_contexture.scripts.ui.task_thread import (
    patch_streamlit_thread_log,
    run_proc_body_with_streamlit_log,
    streamlit_log_message,
)


class FakeStreamlit:
    def __init__(self):
        self.original_calls = []

    def write(self, *args, **kwargs):
        self.original_calls.append(("write", args, kwargs))

    def error(self, *args, **kwargs):
        self.original_calls.append(("error", args, kwargs))

    def success(self, *args, **kwargs):
        self.original_calls.append(("success", args, kwargs))

    def info(self, *args, **kwargs):
        self.original_calls.append(("info", args, kwargs))

    def warning(self, *args, **kwargs):
        self.original_calls.append(("warning", args, kwargs))


def test_streamlit_log_message_matches_existing_ui_thread_format():
    assert streamlit_log_message("write", ("a", 1, "b")) == "a 1 b"
    assert streamlit_log_message("error", ("bad", "ignored")) == "bad"
    assert streamlit_log_message("info", tuple()) == ""


def test_patch_streamlit_thread_log_captures_active_thread_and_restores_methods():
    fake_st = FakeStreamlit()
    original_write_func = fake_st.write.__func__
    log = []

    with patch_streamlit_thread_log(fake_st, log):
        fake_st.write("hello", "world")
        fake_st.error("bad")

    assert log == [("write", "hello world"), ("error", "bad")]
    assert fake_st.original_calls == []
    assert fake_st.write.__func__ is original_write_func
    fake_st.write("after")
    assert fake_st.original_calls == [("write", ("after",), {})]


def test_patch_streamlit_thread_log_delegates_other_thread_calls():
    fake_st = FakeStreamlit()
    log = []
    other_thread_id = threading.get_ident() + 99999

    with patch_streamlit_thread_log(fake_st, log, thread_id=other_thread_id):
        fake_st.warning("goes original")

    assert log == []
    assert fake_st.original_calls == [("warning", ("goes original",), {})]


def test_run_proc_body_with_streamlit_log_marks_done_and_logs_messages():
    fake_st = FakeStreamlit()
    ctx = {"status": "running", "log": []}

    def proc_body(ctx, cancel, output_dir):
        fake_st.info(f"out={output_dir}")
        ctx["progress"] = 1.0

    run_proc_body_with_streamlit_log(
        st=fake_st,
        ctx=ctx,
        cancel=object(),
        output_dir="out",
        proc_body=proc_body,
    )

    assert ctx["status"] == "done"
    assert ctx["progress"] == 1.0
    assert ctx["log"] == [("info", "out=out")]
    assert fake_st.original_calls == []


def test_run_proc_body_with_streamlit_log_records_exceptions():
    fake_st = FakeStreamlit()
    ctx = {"status": "running", "log": []}

    def proc_body(ctx, cancel, output_dir):
        raise RuntimeError("boom")

    run_proc_body_with_streamlit_log(
        st=fake_st,
        ctx=ctx,
        cancel=object(),
        output_dir="out",
        proc_body=proc_body,
    )

    assert ctx["status"] == "error"
    assert ctx["log"][0] == ("error", "处理异常: boom")
    assert "RuntimeError: boom" in ctx["log"][1][1]

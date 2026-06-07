from io import StringIO

from aih_contexture.runtime.subprocess_stream import _format_progress_line_for_console, _is_progress_line, _tee_pipe


def test_progress_line_detection_matches_tqdm_output():
    assert _is_progress_line("Recognizing Layout:  37%|###       | 74/200 [00:16<00:22,  5.56it/s]\n")
    assert _is_progress_line("Layout Predict: 100%|##########| 11/11 [00:03<00:00,  3.64it/s]\n")
    assert not _is_progress_line("2026-05-10 14:06:45,989 [INFO] build_document completed\n")


def test_tee_pipe_compacts_progress_display_but_keeps_raw_chunks(monkeypatch):
    monkeypatch.setenv("CONTEXTURE_COMPACT_SUBPROCESS_PROGRESS", "true")
    pipe = StringIO(
        "Recognizing Layout:   0%|          | 0/200 [00:00<?, ?it/s]\n"
        "Recognizing Layout:  37%|###       | 74/200 [00:16<00:22,  5.56it/s]\n"
        "done\n"
    )
    sink = StringIO()
    chunks: list[str] = []

    _tee_pipe(pipe, sink, chunks)

    assert "".join(chunks).startswith("Recognizing Layout:")
    rendered = sink.getvalue()
    assert "\rRecognizing Layout:" in rendered
    assert rendered.count("\n") == 2
    assert rendered.endswith("done\n")


def test_progress_line_is_redrawn_without_original_tqdm_bar_noise():
    sink = StringIO()

    rendered = _format_progress_line_for_console(
        "Recognizing Layout:  37%|��������      | 74/200 [00:16<00:22,  5.56it/s]\n",
        sink,
    )

    assert rendered.startswith("Recognizing Layout: [")
    assert "37% 74/200" in rendered
    assert "��������" not in rendered

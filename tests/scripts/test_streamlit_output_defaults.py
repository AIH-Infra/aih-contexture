from pathlib import Path


APP_SOURCE = Path("aih_contexture/scripts/streamlit_app.py").read_text(encoding="utf-8")


def test_streamlit_vlm_generalized_defaults_include_html():
    assert 'default=["markdown", "json", "html"]' in APP_SOURCE


def test_streamlit_vlm_specialized_defaults_match_backend_matrix():
    assert 'options=["markdown", "json", "html"],\n                    default=["markdown", "json", "html"]' in APP_SOURCE
    assert 'options=["markdown", "xml", "json", "html"],\n                    default=["markdown", "xml", "json", "html"]' in APP_SOURCE

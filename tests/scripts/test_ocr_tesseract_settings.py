from aih_contexture.scripts.ui.ocr_tesseract_settings import _language_options_for_profile, _sync_profile_defaults


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}


def test_profile_change_resets_language_and_preprocess_defaults():
    st = FakeStreamlit()
    st.session_state["_tesseract_last_profile"] = "printed_latin"
    st.session_state["tesseract_lang_multi"] = ["eng"]
    st.session_state["ocr_crop_preprocess"] = "otsu"

    _sync_profile_defaults(
        st,
        "printed_chinese_simplified",
        "chi_sim+eng",
        "none",
        ["eng", "chi_sim", "deu"],
    )

    assert st.session_state["tesseract_lang_multi"] == ["chi_sim", "eng"]
    assert st.session_state["ocr_crop_preprocess"] == "none"
    assert st.session_state["tesseract_psm"] == 7
    assert st.session_state["_tesseract_last_profile"] == "printed_chinese_simplified"


def test_same_profile_does_not_overwrite_manual_language_choice():
    st = FakeStreamlit()
    st.session_state["_tesseract_last_profile"] = "printed_chinese_simplified"
    st.session_state["tesseract_lang_multi"] = ["eng"]

    _sync_profile_defaults(
        st,
        "printed_chinese_simplified",
        "chi_sim+eng",
        "none",
        ["eng", "chi_sim"],
    )

    assert st.session_state["tesseract_lang_multi"] == ["eng"]


def test_language_options_are_filtered_by_profile():
    installed = [
        "eng",
        "chi_sim",
        "chi_tra",
        "jpn",
        "deu_frak",
        "frk",
        "lat",
        "script/Fraktur",
        "script/HanS",
    ]

    simplified = _language_options_for_profile("printed_chinese_simplified", installed)
    historical = _language_options_for_profile("historical_latin", installed)
    custom = _language_options_for_profile("custom", installed)

    assert simplified == ["chi_sim", "eng", "script/HanS"]
    assert "deu_frak" not in simplified
    assert historical == ["deu_frak", "frk", "script/Fraktur", "lat", "eng"]
    assert "chi_sim" not in historical
    assert custom == installed

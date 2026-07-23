from __future__ import annotations

from aih_contexture.builders.ocr_line_crops import (
    DEFAULT_OCR_CROP_PADDING_FRAC,
    DEFAULT_OCR_CROP_PADDING_PX,
    DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT,
)
from aih_contexture.services.ocr_tesseract import TesseractOcrService


TESSERACT_PROFILE_DEFAULTS = {
    "printed_latin": {"label": "印刷拉丁文本", "lang": "eng", "psm": 7, "preprocess": "otsu"},
    "printed_chinese_simplified": {"label": "简体中文 + 英文", "lang": "chi_sim+eng", "psm": 7, "preprocess": "none"},
    "printed_chinese_traditional": {"label": "繁体中文 + 英文", "lang": "chi_tra+eng", "psm": 7, "preprocess": "none"},
    "mixed_cjk_latin": {"label": "CJK/拉丁混排", "lang": "chi_sim+eng", "psm": 7, "preprocess": "none"},
    "historical_latin": {"label": "欧洲历史文本", "lang": "deu_frak+frk+lat+eng", "psm": 7, "preprocess": "otsu"},
    "custom": {"label": "自定义", "lang": "eng", "psm": 7, "preprocess": "otsu"},
}

TESSERACT_PROFILE_LANGUAGES = {
    "printed_latin": [
        "eng", "enm", "lat",
        "deu", "fra", "spa", "ita", "por", "nld",
        "dan", "fin", "nor", "swe",
        "ces", "pol", "ron", "slk", "slv",
        "tur", "vie",
        "script/Latin",
    ],
    "printed_chinese_simplified": [
        "chi_sim", "chi_sim_vert", "eng", "script/HanS", "script/HanS_vert", "script/Latin",
    ],
    "printed_chinese_traditional": [
        "chi_tra", "chi_tra_vert", "eng", "script/HanT", "script/HanT_vert", "script/Latin",
    ],
    "mixed_cjk_latin": [
        "chi_sim", "chi_sim_vert", "chi_tra", "chi_tra_vert",
        "jpn", "jpn_vert", "kor",
        "eng", "script/HanS", "script/HanT", "script/Japanese", "script/Hangul", "script/Latin",
    ],
    "historical_latin": [
        "deu_frak", "frk", "script/Fraktur",
        "lat", "eng", "enm",
        "deu", "deu_latf",
        "fra", "frm",
        "ita", "ita_old",
        "spa", "spa_old",
        "nld", "por", "grc", "script/Latin",
    ],
}

TESSERACT_PROFILE_LANGUAGE_HINTS = {
    "printed_latin": "现代拉丁字母语种；适用于英文、德法西意葡荷等普通印刷文本。",
    "printed_chinese_simplified": "简体中文相关语言包；默认只混合英文，不混入日/韩/繁体。",
    "printed_chinese_traditional": "繁体中文相关语言包；默认只混合英文，不混入日/韩/简体。",
    "mixed_cjk_latin": "中日韩与拉丁混排；范围更宽，但识别歧义和耗时也会增加。",
    "historical_latin": "欧洲历史文本相关语言包；包含 Fraktur、拉丁、旧体意/西、古典语等。",
    "custom": "显示全部已安装语言包；适用于手动组合特殊 tessdata。",
}


def render_tesseract_ocr_settings(st, *, description: str) -> dict[str, object]:
    st.info(description)

    service = TesseractOcrService({})
    status = _status_payload(service)
    if status["available"]:
        st.success(f"已发现 Tesseract: {status['version']}")
        st.caption(f"路径: {status['command']}")
    else:
        st.warning("未发现 Tesseract。可先继续配置；运行前需要安装 Tesseract 或填写可执行文件路径。")
        st.caption("可设置 CONTEXTURE_TESSERACT_CMD，或在高级设置中填写 tesseract.exe。")

    profile = st.selectbox(
        "识别预设",
        options=list(TESSERACT_PROFILE_DEFAULTS.keys()),
        format_func=lambda key: TESSERACT_PROFILE_DEFAULTS[key]["label"],
        index=0,
        key="tesseract_profile",
        help="预设会联动语言包、PSM 和预处理；高级设置仍可覆盖。",
    )
    defaults = TESSERACT_PROFILE_DEFAULTS[profile]

    languages = status.get("languages") or []
    profile_languages = _language_options_for_profile(profile, languages)
    default_lang = str(defaults["lang"])
    _sync_profile_defaults(st, profile, default_lang, str(defaults["preprocess"]), profile_languages)
    if languages:
        if not profile_languages:
            st.warning("当前预设没有匹配到已安装的语言包。可切换到“自定义”，或安装对应 tessdata。")
            profile_languages = languages
        st.caption(TESSERACT_PROFILE_LANGUAGE_HINTS.get(profile, ""))
        hidden_count = max(0, len(languages) - len(profile_languages))
        if profile != "custom" and hidden_count:
            st.caption(f"已按预设筛选语言包：显示 {len(profile_languages)} 个，隐藏 {hidden_count} 个。")
        default_parts = [part for part in default_lang.split("+") if part in profile_languages]
        selected = st.multiselect(
            "语言包",
            options=profile_languages,
            default=default_parts or ([profile_languages[0]] if profile_languages else []),
            key="tesseract_lang_multi",
            help="多语言会以 eng+deu 格式传入。语言越多，速度越慢，也更容易混淆。",
        )
        tesseract_lang = "+".join(selected) if selected else default_lang
    else:
        tesseract_lang = st.text_input(
            "语言表达式",
            value=default_lang,
            key="tesseract_lang",
            help="例如 eng、chi_sim+eng、deu+eng。安装后会自动读取可用语言包。",
        )

    preprocess = st.selectbox(
        "行图像预处理",
        options=["otsu", "none", "adaptive"],
        index=["otsu", "none", "adaptive"].index(str(defaults["preprocess"])),
        format_func=lambda value: {"otsu": "Otsu 二值化", "none": "不处理", "adaptive": "自适应二值化"}[value],
        key="ocr_crop_preprocess",
        help="泛黄纸张可先试 Otsu；CJK 细笔画可先保持不处理。",
    )
    force_ocr = True

    with st.expander("裁线保护", expanded=False):
        st.caption("当 b/h、m/rn、页边脚注等容易误识别时，优先调这里。")
        crop_col_a, crop_col_b = st.columns(2)
        with crop_col_a:
            ocr_crop_padding_px = st.number_input(
                "裁线 padding（px）",
                min_value=0,
                max_value=80,
                value=DEFAULT_OCR_CROP_PADDING_PX,
                key="ocr_crop_padding_px",
                help="向外扩展行框，避免字母边缘、升部和降部被裁掉。",
            )
        with crop_col_b:
            ocr_crop_padding_frac = st.number_input(
                "裁线 padding（比例）",
                min_value=0.0,
                max_value=0.5,
                value=DEFAULT_OCR_CROP_PADDING_FRAC,
                step=0.01,
                key="ocr_crop_padding_frac",
                help="按行框尺寸额外扩展；版面线框偏紧时提高到 0.16-0.20。",
            )
        ocr_crop_upscale_min_height = st.number_input(
            "行图最小高度放大到（px，0 为关闭）",
            min_value=0,
            max_value=256,
            value=DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT,
            key="ocr_crop_upscale_min_height",
            help="低分辨率行图可放大后再识别；通常 32-48 比较稳。",
        )

    with st.expander("高级设置", expanded=False):
        tesseract_cmd = st.text_input(
            "Tesseract 可执行文件",
            value="",
            key="tesseract_cmd",
            help="留空时按配置、环境变量、PATH 和常见安装路径自动发现。",
        )
        tesseract_tessdata_prefix = st.text_input(
            "TESSDATA_PREFIX",
            value="",
            key="tesseract_tessdata_prefix",
            help="仅当语言包不在默认位置时填写。",
        )
        col_engine, col_psm = st.columns(2)
        with col_engine:
            tesseract_oem = st.selectbox(
                "OCR 引擎模式",
                options=[1, 3, 0, 2],
                index=0,
                format_func=lambda value: {
                    1: "1 - LSTM only（默认）",
                    3: "3 - Tesseract default",
                    0: "0 - Legacy only",
                    2: "2 - Legacy + LSTM",
                }[value],
                key="tesseract_oem",
            )
        with col_psm:
            tesseract_psm = st.selectbox(
                "页面分割模式",
                options=[7, 6, 13],
                index=[7, 6, 13].index(int(defaults["psm"])),
                format_func=lambda value: {
                    7: "7 - 单行（默认）",
                    6: "6 - 单块文本",
                    13: "13 - 原始单行",
                }[value],
                key="tesseract_psm",
            )

        line_col_a, line_col_b = st.columns(2)
        with line_col_a:
            tesseract_line_psm = st.selectbox(
                "行检测 PSM",
                options=[1, 6, 4, 3, 11],
                index=0,
                format_func=lambda value: {
                    1: "1 - 自动分割 + OSD（默认，整页 hOCR）",
                    6: "6 - 单块文本",
                    4: "4 - 单列文本",
                    3: "3 - 自动分割",
                    11: "11 - 稀疏文本",
                }[value],
                key="tesseract_line_psm",
                help="用于整页 hOCR 行框检测；hOCR 失败时才回退到旧的分块 TSV 行检测。",
            )
        with line_col_b:
            tesseract_thresholding_method = st.selectbox(
                "Tesseract 阈值算法",
                options=["auto", "adaptive-otsu", "sauvola"],
                index=0,
                format_func=lambda value: {
                    "auto": "auto / Otsu",
                    "adaptive-otsu": "adaptive Otsu",
                    "sauvola": "Sauvola",
                }[value],
                key="tesseract_thresholding_method",
                help="对应 OCRmyPDF 的 Tesseract thresholding_method；Tesseract 5+ 支持。",
            )

        timeout_col, omp_col = st.columns(2)
        with timeout_col:
            tesseract_timeout = st.number_input("单行超时（秒）", min_value=5, max_value=300, value=30, key="tesseract_timeout")
        with omp_col:
            tesseract_omp_thread_limit = st.number_input("OMP 线程限制", min_value=1, max_value=16, value=1, key="tesseract_omp_thread_limit")

        tesseract_line_upscale_min_height = st.number_input(
            "行检测图最小高度放大到（px，0 为关闭）",
            min_value=0,
            max_value=512,
            value=0,
            key="tesseract_line_upscale_min_height",
        )

        tesseract_user_words = st.text_input("user words 文件", value="", key="tesseract_user_words")
        tesseract_user_patterns = st.text_input("user patterns 文件", value="", key="tesseract_user_patterns")
        tesseract_extra_config = st.text_input("额外 Tesseract 参数", value="", key="tesseract_extra_config")

        if tesseract_oem in (0, 2):
            st.warning("Legacy OEM 需要语言包包含 legacy 组件；很多现代 traineddata 不兼容。")
        if "+" in tesseract_lang:
            st.caption("多语言会增加运行时间和识别歧义；只选择确实需要的语言。")

    return {
        "tesseract_profile": profile,
        "tesseract_cmd": tesseract_cmd,
        "tesseract_lang": tesseract_lang,
        "tesseract_oem": tesseract_oem,
        "tesseract_psm": tesseract_psm,
        "tesseract_line_psm": tesseract_line_psm,
        "tesseract_line_preprocess": preprocess,
        "tesseract_line_upscale_min_height": tesseract_line_upscale_min_height,
        "tesseract_thresholding_method": tesseract_thresholding_method,
        "tesseract_timeout": tesseract_timeout,
        "tesseract_omp_thread_limit": tesseract_omp_thread_limit,
        "tesseract_tessdata_prefix": tesseract_tessdata_prefix,
        "tesseract_user_words": tesseract_user_words,
        "tesseract_user_patterns": tesseract_user_patterns,
        "tesseract_extra_config": tesseract_extra_config,
        "ocr_crop_padding_px": ocr_crop_padding_px,
        "ocr_crop_padding_frac": ocr_crop_padding_frac,
        "ocr_crop_preprocess": preprocess,
        "ocr_crop_upscale_min_height": ocr_crop_upscale_min_height,
        "force_ocr": True,
        "use_llm": False,
        "ocr_batch_size": 32,
    }


def _status_payload(service: TesseractOcrService) -> dict[str, object]:
    try:
        info = service.resolve_command()
        return {
            "available": True,
            "command": info.command,
            "version": info.version or "",
            "languages": service.list_languages(),
        }
    except Exception:
        return {"available": False, "command": "", "version": "", "languages": []}


def _language_options_for_profile(profile: str, installed_languages: list[str]) -> list[str]:
    if profile == "custom":
        return installed_languages
    allowed = TESSERACT_PROFILE_LANGUAGES.get(profile, [])
    installed = set(installed_languages)
    return [lang for lang in allowed if lang in installed]


def _sync_profile_defaults(st, profile: str, default_lang: str, default_preprocess: str, languages: list[str]) -> None:
    """When the preset changes, reset dependent fields before their widgets render."""
    previous = st.session_state.get("_tesseract_last_profile")
    if previous == profile:
        return

    default_parts = [part for part in default_lang.split("+") if not languages or part in languages]
    if languages:
        st.session_state["tesseract_lang_multi"] = default_parts
    else:
        st.session_state["tesseract_lang"] = "+".join(default_parts) or default_lang
    st.session_state["ocr_crop_preprocess"] = default_preprocess
    st.session_state["tesseract_psm"] = int(TESSERACT_PROFILE_DEFAULTS[profile]["psm"])
    st.session_state["_tesseract_last_profile"] = profile

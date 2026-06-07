from aih_contexture.processors.printed_page_correction import PrintedPageNumberCorrector


def test_printed_page_corrector_repairs_missing_and_outlier_sequence_values():
    extracted = {
        0: 4,
        1: None,
        2: 35,
        3: 36,
        4: 37,
        5: 38,
        6: 39,
        7: 40,
        8: None,
        9: 310,
        10: 4,
        11: 44,
        12: 45,
        13: 46,
        14: 47,
        15: 48,
        16: 49,
    }

    corrector = PrintedPageNumberCorrector(min_confidence=0.7)
    pattern = corrector._select_best_pattern(corrector._identify_patterns(extracted))
    corrected = corrector._apply_pattern(extracted, pattern)

    assert corrected[0] == "33"
    assert corrected[1] == "34"
    assert corrected[8] == "41"
    assert corrected[9] == "42"
    assert corrected[10] == "43"
    assert corrected[16] == "49"

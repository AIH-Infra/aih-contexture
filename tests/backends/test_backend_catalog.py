from aih_contexture.backends.catalog import (
    backend_catalog,
    list_layout_backends,
    list_ocr_backends,
    list_vlm_backends,
)


def test_backend_catalog_exports_layout_and_ocr_capabilities():
    catalog = backend_catalog()

    assert sorted(catalog.keys()) == ["layout", "ocr", "vlm"]
    assert [backend["name"] for backend in catalog["layout"]] == [
        "external_layout_sidecar",
        "mineru_pp_doclayout_v2",
        "mineru_pp_doclayout_v2_direct",
        "paddle_pp_doclayout_plus_l",
        "paddle_pp_doclayout_v3",
        "surya",
        "vlm_layout",
    ]
    assert [backend["name"] for backend in catalog["ocr"]] == [
        "calamari",
        "paddle_ocr_v5",
        "paddleocr_vl_ocr",
        "surya",
        "tesseract",
        "vlm_ocr",
    ]
    assert [backend["name"] for backend in catalog["vlm"]] == [
        "chandra",
        "churro",
        "mineru_vl",
        "paddleocr_vl",
        "vlm_generalized",
    ]
    assert catalog["layout"][0]["kind"] == "layout"
    assert catalog["ocr"][0]["kind"] == "ocr"
    assert catalog["vlm"][0]["kind"] == "vlm"


def test_backend_catalog_helpers_are_read_only_snapshots():
    layout_backends = list_layout_backends()
    ocr_backends = list_ocr_backends()
    vlm_backends = list_vlm_backends()

    layout_backends[0]["name"] = "mutated"
    ocr_backends[0]["name"] = "mutated"
    vlm_backends[0]["name"] = "mutated"

    assert list_layout_backends()[0]["name"] == "external_layout_sidecar"
    assert list_ocr_backends()[0]["name"] == "calamari"
    assert list_vlm_backends()[0]["name"] == "chandra"


def test_backend_catalog_does_not_expose_builder_factories():
    catalog = backend_catalog(implemented_only=False)

    for group in catalog.values():
        for backend in group:
            assert "builder_factory" not in backend


def test_backend_catalog_can_include_planned_backends():
    catalog = backend_catalog(implemented_only=False)

    layout_names = [backend["name"] for backend in catalog["layout"]]
    ocr_names = [backend["name"] for backend in catalog["ocr"]]
    vlm_names = [backend["name"] for backend in catalog["vlm"]]

    assert "mineru_pp_doclayout_v2" in layout_names
    assert "mineru_pp_doclayout_v2_direct" in layout_names
    assert "paddle_pp_doclayout_v3" in layout_names
    assert "paddle_ocr_v5" in ocr_names
    assert "paddleocr_vl_ocr" in ocr_names
    assert "tesseract" in ocr_names
    assert "mineru_pytorch_paddle_ocr" in ocr_names
    assert "paddleocr_vl" in vlm_names
    assert "mineru_vl" in vlm_names


def test_backend_catalog_status_is_optional_and_non_intrusive(tmp_path):
    catalog = backend_catalog(include_status=True, config={"mineru_command": str(tmp_path / "missing-mineru")})
    layout_by_name = {backend["name"]: backend for backend in catalog["layout"]}
    vlm_by_name = {backend["name"]: backend for backend in catalog["vlm"]}

    assert "status" not in backend_catalog()["layout"][0]
    assert layout_by_name["external_layout_sidecar"]["status"]["available"] is True
    assert layout_by_name["mineru_pp_doclayout_v2"]["status"]["level"] == "missing_dependency"
    assert layout_by_name["mineru_pp_doclayout_v2"]["status"]["details"]["command"].endswith("missing-mineru")
    assert vlm_by_name["vlm_generalized"]["status"]["level"] == "requires_configuration"
    assert vlm_by_name["paddleocr_vl"]["status"]["level"] == "requires_configuration"

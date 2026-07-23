import os

from aih_contexture.runtime.model_lifecycle import LazyModelDict


os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = (
    "1"  # Transformers uses .isin for an op, which is not supported on MPS
)


def create_model_dict(
    device=None, dtype=None, attention_implementation: str | None = None
) -> LazyModelDict:
    return LazyModelDict(
        {
            "layout_model": lambda: _create_layout_model(device, dtype, attention_implementation),
            "recognition_model": lambda: _create_recognition_model(device, dtype, attention_implementation),
            "table_rec_model": lambda: _create_table_rec_model(device, dtype),
            "detection_model": lambda: _create_detection_model(device, dtype),
            "ocr_error_model": lambda: _create_ocr_error_model(device, dtype),
        }
    )


def create_eager_model_dict(
    device=None, dtype=None, attention_implementation: str | None = None
) -> dict:
    return create_model_dict(device, dtype, attention_implementation).materialize_all()


def _create_foundation(checkpoint: str, device=None, dtype=None, attention_implementation: str | None = None):
    from surya.foundation import FoundationPredictor

    return FoundationPredictor(
        checkpoint=checkpoint,
        attention_implementation=attention_implementation,
        device=device,
        dtype=dtype,
    )


def _create_layout_model(device=None, dtype=None, attention_implementation: str | None = None):
    from surya.layout import LayoutPredictor
    from surya.settings import settings as surya_settings

    return LayoutPredictor(
        _create_foundation(
            surya_settings.LAYOUT_MODEL_CHECKPOINT,
            device=device,
            dtype=dtype,
            attention_implementation=attention_implementation,
        )
    )


def _create_recognition_model(device=None, dtype=None, attention_implementation: str | None = None):
    from surya.recognition import RecognitionPredictor
    from surya.settings import settings as surya_settings

    return RecognitionPredictor(
        _create_foundation(
            surya_settings.RECOGNITION_MODEL_CHECKPOINT,
            device=device,
            dtype=dtype,
            attention_implementation=attention_implementation,
        )
    )


def _create_table_rec_model(device=None, dtype=None):
    from surya.table_rec import TableRecPredictor

    return TableRecPredictor(device=device, dtype=dtype)


def _create_detection_model(device=None, dtype=None):
    from surya.detection import DetectionPredictor

    return DetectionPredictor(device=device, dtype=dtype)


def _create_ocr_error_model(device=None, dtype=None):
    from surya.ocr_error import OCRErrorPredictor

    return OCRErrorPredictor(device=device, dtype=dtype)

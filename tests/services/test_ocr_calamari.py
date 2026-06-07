from PIL import Image

from aih_contexture.services.ocr_calamari import CalamariOcrService


def test_ocr_page_splits_large_batches_with_global_indices(monkeypatch):
    service = CalamariOcrService(
        {
            "calamari_batch_size": 2,
            "calamari_split_large_batches": True,
            "calamari_sequential_mode": False,
        }
    )
    calls = []

    def fake_batch(images, global_start_index):
        calls.append((len(images), global_start_index))
        return [f"text-{global_start_index + i}" for i in range(len(images))]

    monkeypatch.setattr(service, "_ocr_batch_single", fake_batch)

    images = [Image.new("RGB", (10, 10), "white") for _ in range(5)]
    texts = service.ocr_page(images, global_start_index=10)

    assert calls == [(2, 10), (2, 12), (1, 14)]
    assert texts == ["text-10", "text-11", "text-12", "text-13", "text-14"]


def test_ocr_page_can_keep_single_logical_batch(monkeypatch):
    service = CalamariOcrService(
        {
            "calamari_batch_size": 2,
            "calamari_split_large_batches": False,
            "calamari_sequential_mode": False,
        }
    )
    calls = []

    def fake_batch(images, global_start_index):
        calls.append((len(images), global_start_index))
        return ["ok"] * len(images)

    monkeypatch.setattr(service, "_ocr_batch_single", fake_batch)

    images = [Image.new("RGB", (10, 10), "white") for _ in range(5)]
    texts = service.ocr_page(images, global_start_index=10)

    assert calls == [(5, 10)]
    assert texts == ["ok"] * 5

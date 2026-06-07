import threading
import time

from PIL import Image

from aih_contexture.services.layout_base import LayoutResult
from aih_contexture.services.layout_vlm import VlmLayoutService


def test_vlm_layout_service_reads_max_concurrent_from_config():
    service = VlmLayoutService({"vlm_layout_max_concurrent": 3})

    assert service.vlm_layout_max_concurrent == 3


def test_vlm_layout_service_detect_layout_preserves_order_with_concurrency(monkeypatch):
    service = VlmLayoutService({"vlm_layout_max_concurrent": 2})
    images = [
        Image.new("RGB", (10 + idx, 20), "white")
        for idx in range(4)
    ]
    lock = threading.Lock()
    active = 0
    max_active = 0

    monkeypatch.setattr(service, "get_client", lambda: object())

    def fake_detect(client, img):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return LayoutResult(image_bbox=[0, 0, img.size[0], img.size[1]], bboxes=[], sliced=False)

    monkeypatch.setattr(service, "_detect_single_image", fake_detect)

    results = service.detect_layout(images)

    assert [result.image_bbox[2] for result in results] == [10, 11, 12, 13]
    assert 1 < max_active <= 2

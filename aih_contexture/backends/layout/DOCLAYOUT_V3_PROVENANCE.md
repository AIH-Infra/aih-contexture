# Native PP-DocLayoutV3 ONNX component

The inference wrapper is maintained by Contexture. It uses the official
`PaddlePaddle/PP-DocLayoutV3_onnx` model at Hugging Face snapshot
`46bbdf188bb0a772c08aed74882ce7e51a8f1ea6`, containing `inference.onnx` and
`inference.yml`. Model weights are optional resources, not shipped in the package.

`doclayout_postprocess.py` derives from PaddleX's
`inference/models/layout_analysis/processors.py` in the local PaddleOCR 3.7.0
reference environment. `doclayout_box_ops.py` contains the `iou`, `nms`,
`is_contained`, and `check_containment` helpers from
`inference/models/object_detection/processors.py` in the same environment.

Changes are limited to imports and removal of SDK timing/dependency decorators.
The operations use standard OpenCV functions already provided by Contexture's
headless OpenCV dependency; the separate contrib wheel is not required. The
source's reading-order, mask-to-polygon and filtering algorithms are retained.
Paddle/PaddleX framework modules and Transformers are not imported.

The wrapper converts RGB, resizes to 800 x 800 with bicubic interpolation,
rescales by 1/255, supplies resized image shape and scale factors, and splits
the ONNX outputs by the per-page detection counts. Final list order is used
for Pipeline's total block order; upstream text-only order is preserved as
`native_order`. Original multipoint contours are retained as `polygon_points`;
the Pipeline's quadrilateral schema receives a minimum-area enclosing quad.

Original copyright/Apache-2.0 headers are retained. The full Apache-2.0 license
is included at `aih_contexture/vendor/licenses/paddlex-layout-LICENSE`.

Upstream: https://github.com/PaddlePaddle/PaddleX

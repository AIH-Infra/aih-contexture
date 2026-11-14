# Native Paddle OCR Torch component

This directory contains inference code derived from the locally maintained
MinerU reference snapshot labelled `MinerU-mineru-3.4.2-released`, collected on
2026-10-30. That reference includes local PP-OCRv6 safetensors and inference
precision changes; it is not an unmodified upstream release. Its original
sources are `mineru/model/utils/pytorchocr`, `mineru/model/utils/tools/infer`,
`mineru/utils/ocr_utils.py`, `mineru/utils/bbox_utils.py`, and the seal crop/warp
helpers under `mineru/model/ocr`.

The v5 dictionaries additionally come from the local reference snapshot labelled
`MinerU-mineru-3.2.1-released`. Model/language profiles for v5 and v6 live in the
sibling `../resources/paddle_torch_models_v5.yml` and `paddle_torch_models_v6.yml`.
The v5 `ch` profile explicitly uses v5 recognition weights, rather than the
reference snapshot's v4 document recognizer. The v5 `seal` profiles retain their
v4 specialist weights. The actual filenames are included in OCR result metadata.

Contexture modifications:

- Internal imports and resource paths replace MinerU package references.
- `engine.py` and the lazy public factory own device/model selection and RGB
  image orchestration. No MinerU downloader, configuration file, CLI, or service
  is needed. Downloads and cache discovery are handled by Contexture separately.
- Only text OCR model architectures are included; formula generation heads and
  their Transformers dependencies are excluded. Decoding is limited to the CTC
  path used by these models; training and Python 2 support are excluded.
- The seal warp helper uses standard Python logging instead of Loguru.
- PyTorch weight loading uses `weights_only=True`; the obsolete older-Torch
  fallback is removed. Non-finite recognition confidence raises an error instead
  of silently becoming an empty line.
- Original model math, preprocessing, postprocessing and copyright headers are
  retained. Model weights are not included in the source package.

Upstream: https://github.com/opendatalab/MinerU

The complete source snapshot license is preserved at
`aih_contexture/vendor/licenses/mineru-ocr-LICENSE.md`. Individual PaddlePaddle
copyright and Apache-2.0 notices remain in their original files. Model weights
have their own applicable licenses; including inference code does not replace
those terms.

# AIH-Contexture 0.7.0

AIH-Contexture 0.7.0 focuses on more reliable scholarly document conversion,
broader OCR/layout backend support, and a more portable local installation.

## What’s new

- Added a unified runtime for Pipeline, generalized VLM, specialized VLM, and
  Markdown post-processing tasks.
- Added Middle JSON as the common intermediate representation for structured
  document data.
- Expanded Scholarly Markdown output with physical-page anchors, printed-page
  references, footnotes, marginal notes, and stable numbered paragraphs.
- Added Surya2 VLM layout and OCR integration.
- Added MinerU OCR/layout sidecars and MinerU-VL compatibility.
- Added PaddleOCR, PaddleOCR-VL, Tesseract, and Chrome ScreenAI integration
  improvements.
- Added backend discovery, diagnostics, sidecar configuration, and optional
  external-runtime support.
- Improved batch processing by staging uploads and temporary results on disk,
  reducing memory usage during multi-file jobs.
- Improved Windows, macOS, and Linux installation and startup scripts.

## What’s improved

- Printed-page detection now validates page-number sequences before producing
  citation anchors.
- Isolated page-number noise is filtered instead of becoming misleading page
  references.
- Numbered scholarly paragraphs are escaped correctly in Markdown and no longer
  render as unintended lists.
- Footnote and superscript formatting is preserved more consistently across
  Pipeline and VLM output paths.
- Pipeline subprocesses can use the project virtual environment automatically,
  making local installation and backend execution more consistent.

## Installation

Use the platform-specific `install` script, then run the matching `start`
script. Optional model services and external OCR/layout backends are configured
separately by the user.

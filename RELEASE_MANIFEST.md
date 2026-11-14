# AIH-Contexture 0.9.0 Release Manifest

This directory is a clean, standalone source release intended for installation
on a new computer.

Included:

- Public root documents: `README.md`, `CHANGELOG.md`, `RELEASE_MANIFEST.md`, `MIDDLE_JSON_SCHOLARLY_MARKDOWN_CONTRACT.md`, and `OUTPUT_LAYOUT.md`
- Runtime package: `aih_contexture/`
- Root application entry points: `contexture_app.py`, `contexture_server.py`, and the documented CLI wrappers
- Streamlit UI, Pipeline CLI, VLM generalized/specialized CLI, structured-source CLI, and local FastAPI entry points
- Windows, macOS, and Linux install/start scripts; `repair_windows_runtime.bat` reruns the standard Windows installer
- Dependency manifests, public configuration templates, UI assets, and license files, including `LICENSE`, `NOTICE`, `MODEL_LICENSE`, and `aih_contexture/vendor/locro/LICENSE`
- Pipeline, generalized VLM, specialized VLM, structured-source import, text-layer fast path, and Markdown post-processing code
- The five UI workflows: Pipeline, VLM generalized, VLM specialized, structured-source import, and Markdown post-processing

Intentionally excluded:

- Git history and development-tool configuration
- Tests, test fixtures, manual test directories, and conversion samples
- Development plans, internal acceptance/engineering reports, benchmark artifacts, and local audit output
- Generated output, logs, temporary files, Python bytecode, virtual environments,
  and downloaded model caches
- Local API profiles, `_app_settings.json`, API keys, tokens, passwords, and machine-specific runtime settings
- The stale `poetry.lock`; the install scripts use `requirements.txt` and validate the selected PyTorch profile
- Model weights and Chrome ScreenAI native libraries/model files

First-run behavior:

1. Install with the platform-appropriate `install` script.
2. Start with the matching `start` script.
3. Optional cloud and local VLM backends must be configured by the new user.
4. Some local OCR/layout backends download their public model weights on first use.

0.9.0 runtime defaults:

- The default OCR stack uses Surya OCR 0.17.1, Transformers 4.57.6, pdftext 0.6.3, and pypdfium2 4.30.0. Python 3.10 uses NumPy 2.2.x and scikit-learn 1.6.x; Python 3.11/3.12 use NumPy 2.3+ and scikit-learn 1.8+.
- Chrome ScreenAI uses 4 workers by default.
- The embedded-text fast path uses 4 file subprocesses by default (range 1–16 in the UI).
- `contexture_vlm_generalized` and `contexture_vlm_specialized` can call an LM Studio-compatible service through explicit CLI configuration.
- Generalized VLM resumes matching successful pages from its page checkpoint; specialized VLM can resume at a failed UI batch while retaining outputs from completed batches. Neither is a durable service job queue or full task-resume system.
- The local UI is single-user. This release does not include a public authenticated service queue or distributed worker system.

The application creates `configs/api_profiles/` and
`configs/_app_settings.json` locally as needed. Do not copy those runtime files
into a distributable package.

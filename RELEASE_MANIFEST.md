# AIH-Contexture 1.0.0 Release Manifest

This directory is a clean, standalone source release intended for installation
on a new computer.

Included:

- Runtime package: `aih_contexture/`
- Streamlit UI, five workflows (Pipeline, two VLM modes, structured-source import, Markdown post-processing), CLI, and FastAPI local entry points
- Windows, macOS, and Linux install/start scripts
- Dependency manifests, public configuration templates, UI assets, and licenses
- Pipeline, generalized VLM, specialized VLM, text-layer fast path, and Markdown post-processing code

Intentionally excluded:

- Git history and development-tool configuration
- Tests, test fixtures, manual test directories, and conversion samples
- Generated output, logs, temporary files, Python bytecode, virtual environments,
  and downloaded model caches
- Local API profiles, API keys, tokens, passwords, and machine-specific settings

First-run behavior:

1. Install with the platform-appropriate `install` script.
2. Start with the matching `start` script.
3. Optional cloud and local VLM backends must be configured by the new user.
4. Some local OCR/layout backends download their public model weights on first use.

Dependency baseline:

- The platform install scripts read `requirements.txt`; PyTorch is installed separately by the selected platform profile.
- `pyproject.toml` declares the package and optional extras; no Poetry lock file is included.
- Compatible core versions are Surya OCR 0.17.1, Transformers 4.57.6, PDFText 0.6.3, and pypdfium2 4.30.0.
- Python 3.10 uses NumPy 2.2.x and scikit-learn 1.6.x; Python 3.11–3.12 use the newer dependency ranges in the manifests.

Optional extras (not installed by default; weights are never bundled):

- `.[indra]` Indra OCR (CPU); `.[paddle-layout]` built-in PP-DocLayoutV3 ONNX; `.[paddle-torch]` Paddle OCR Torch.
- Model folders are supplied by the user; downloads happen only when the matching `*_allow_download` option is enabled.

1.0.0 runtime defaults:

- Chrome ScreenAI uses 4 workers by default.
- The embedded-text fast path uses 4 file subprocesses by default (range 1–16 in the UI).
- `contexture_vlm_generalized` and `contexture_vlm_specialized` can call an LM Studio-compatible service through explicit CLI configuration.

The application creates `configs/api_profiles/` and
`configs/_app_settings.json` locally as needed. Do not copy those runtime files
into a distributable package.

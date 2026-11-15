# AIH-Contexture 1.1.1 Release Manifest

This directory is a clean, standalone source release intended for installation
on a new computer.

Included:

- Runtime package: `aih_contexture/`
- Streamlit UI, Pipeline CLI, VLM generalized/specialized CLI, FastAPI local entry points, and the optional LAN gateway
- Windows, macOS, and Linux install/start scripts
- Root public documentation: `README.md`, `CHANGELOG.md`, `RELEASE_MANIFEST.md`, `MIDDLE_JSON_SCHOLARLY_MARKDOWN_CONTRACT.md`, `MIDDLE_STORAGE.md`, `OUTPUT_LAYOUT.md`, `READING_COMPATIBILITY.md`, and `READING_DIAGNOSTICS.md`
- Root legal notices: `LICENSE`, `NOTICE`, and `MODEL_LICENSE`; also retain vendored license and provenance files under `aih_contexture/`
- Optional gateway documentation and sources: `deploy/cluster/README.md`, `deploy/cluster/Dockerfile`, `deploy/cluster/gateway.dockerignore`, `deploy/cluster/native-constraints.txt`, `deploy/cluster/gateway_backup.py`, and the gateway/worker modules under `aih_contexture/`
- Public configuration examples and UI assets
- Pipeline, generalized VLM, specialized VLM, text-layer fast path, and Markdown post-processing code
- Optional LAN gateway source and its Docker, worker, and backup deployment files; the gateway is configured and started separately

Intentionally excluded:

- Git history and development-tool configuration
- Tests, test fixtures, manual test directories, and conversion samples
- Historical acceptance records, internal deployment patches/configurations, private integration artifacts, development plans, research notes, benchmark data, and local evaluation outputs
- Standalone design or comparison notes that are not part of the public user or format contracts, including `STRUCTURED_SOURCE_IMPORT_DESIGN.md` and `UPSTREAM_COMPARISON.md`
- Generated output, logs, temporary files, Python bytecode, virtual environments,
  and downloaded model caches
- Local API profiles, API keys, tokens, passwords, and machine-specific settings
- `poetry.lock` until it is regenerated from the release dependency metadata; use the install scripts and `requirements.txt` for this release
- Machine-specific runtime constraint files such as the root `rocm_constraints.txt`
- `deploy/cluster/knowledge_pdf.patch`, which is an integration patch for a separate knowledge-service repository

First-run behavior:

1. Install with the platform-appropriate `install` script.
2. Start with the matching `start` script.
3. Optional cloud and local VLM backends must be configured by the new user.
4. Some local OCR/layout backends download their public model weights on first use.

Optional extras (not installed by default; weights are never bundled):

- `.[indra]` Indra OCR (CPU); `.[paddle-layout]` built-in PP-DocLayoutV3 ONNX; `.[paddle-torch]` Paddle OCR Torch.
- Model folders are supplied by the user; downloads happen only when the matching `*_allow_download` option is enabled.

1.1.1 runtime defaults and boundaries:

- The default local backend uses Surya OCR 0.17.1 with Transformers 4.57.6.
- Pipeline UI defaults to 100 pages per batch; CLI automatic mode may adjust that count to available resources. Files within the selected page count run whole; longer files split at that count. Consecutive short files use resource-planned warm processes that reuse models; long-file batch parallelism is scheduled separately.
- Chrome ScreenAI uses 4 workers by default.
- ScreenAI can remove PDF annotations, marks, stamps, and links before recognition while retaining visible page content and form values. Hidden-text cleanup and rasterization are selectable preprocessing modes; the rebuilt page DPI controls clarity and output size.
- When both Indra layout and OCR are selected, the CPU direct route accepts PDF input and Markdown/Middle JSON output. UI page selections form one Indra job, with inner parallelism controlled by the CPU-core setting.
- `contexture_vlm_generalized` and `contexture_vlm_specialized` can call an LM Studio-compatible service through explicit CLI configuration.
- Generalized VLM checkpoints reuse successful pages only when source, page selection, model, endpoint, and effective configuration match. Specialized VLM recovery restarts at a failed batch and keeps outputs from completed batches; it is not page-level or durable task recovery.
- The optional LAN gateway provides Bearer-authenticated APIs, a persistent queue, native workers, task status, and result downloads. It is not started by the local UI installer.

The application creates `configs/api_profiles/` and
`configs/_app_settings.json` locally as needed. Do not copy those runtime files
or private gateway configuration into a distributable package.

# AIH-Contexture 0.7.0 Release Manifest

This directory is a clean, standalone source release intended for installation
on a new computer.

Included:

- Runtime package: `aih_contexture/`
- Streamlit UI entry points and command-line entry points
- Windows, macOS, and Linux install/start scripts
- Dependency manifests, public configuration templates, UI assets, and licenses
- Pipeline, generalized VLM, specialized VLM, and Markdown post-processing code

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

The application creates `configs/api_profiles/` and
`configs/_app_settings.json` locally as needed. Do not copy those runtime files
into a distributable package.

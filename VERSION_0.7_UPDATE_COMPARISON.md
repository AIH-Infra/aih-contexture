# AIH-Contexture 0.7.0 Update Comparison

Report date: 2026-07-13

Baseline: AIH-Contexture 0.5.0 original release

Current release: AIH-Contexture 0.7.0 standalone runtime package

## 1. Release Position

Version 0.7 is not a redesign of the 0.5 architecture. It preserves the
original Runtime / Middle / Backend boundaries and incorporates the current
working implementation on top of that baseline. Its release focus is:

- preserve the complete runtime capability while removing development residue;
- improve scholarly Markdown compatibility for page anchors, footnotes, and
  numbered paragraphs;
- expand local and sidecar backend integration without embedding private model
  environments or credentials;
- make the directory portable to a new computer through the platform install
  and start scripts.

The release remains a local, single-user application. It does not claim to
provide a multi-user queue, authentication, public task API, distributed worker
pool, or full checkpoint/resume service.

## 2. Scope and Size

| Item | 0.5 original release | 0.7 runtime release | Interpretation |
| --- | ---: | ---: | --- |
| Runtime source files under `aih_contexture/` | 320 | 348 | 28 runtime modules added; none removed. |
| Existing runtime files changed | - | 89 | Current implementation extends the 0.5 source rather than replacing it. |
| Delivered files | 583 | 375 | 0.7 intentionally excludes tests, fixtures, sample conversions, output, caches, virtual environments, Git history, and development-only documents. |
| Python support contract | 3.10+ | 3.10-3.12 | 0.7 matches the installer and tested dependency range. |

The lower delivery-file count is a packaging change, not a reduction of runtime
modules. Tests were deliberately excluded from this runnable distribution; they
must remain in the development source tree used to maintain future releases.

## 3. Code and Architecture Continuity

0.7 follows the original project conventions:

- package-level separation of runtime, middle representation, backends,
  converters, processors, services, renderers, and UI helpers;
- typed data models and Pydantic schemas where a stable document or processor
  contract exists;
- Click-based CLI entry points and platform-specific launch scripts;
- optional backends represented through catalog, registry, diagnostics, and
  explicit configuration rather than mandatory dependencies;
- Middle JSON remains the interchange boundary; scholarly Markdown remains the
  human-review boundary.

The release also retains the original boundary between the main application
environment and heavyweight external model environments. `Surya` belongs to the
main installation. MinerU and Paddle can run in their own sidecar environments.
Cloud and local VLM services are configured at runtime and are never bundled
with credentials.

## 4. Functional Changes Since 0.5

### Scholarly Markdown and page semantics

- Printed page candidates are now sequence-validated, support multiple
  independent page-number sequences, and no longer synthesize negative page
  numbers for unverified front matter.
- Isolated page-number noise is omitted rather than rendered as a plausible
  citation anchor.
- Scholarly numbered paragraphs and notes are normalized to escaped Markdown
  forms such as `201\.` and `8\.` so they do not become visually indented
  Markdown lists.
- Footnote definitions and references now preserve `<sup>n</sup>` semantics
  across the common renderer path and VLM final-formatting paths.
- Churro XML visual superscripts, including emphasis and addition forms, are
  mapped to inline superscript references while bottom-margin definitions remain
  definitions.

### Backend and conversion integration

- Added MinerU OCR sidecar support and reusable sidecar process pooling.
- Added MinerU-VL layout compatibility and Surya 2 VLM layout/OCR integration
  points.
- Added Chrome ScreenAI local OCR preprocessing and searchable-PDF feedback
  flow through the Pipeline path.
- Expanded backend diagnostics from simple import/path checks to configured
  sidecar interpreter checks for Paddle and MinerU.
- Pipeline execution now uses the project `.venv` automatically when present.

### UI and batch execution

- Uploaded files are staged immediately to a task temporary directory. Batch
  state keeps paths instead of retaining all uploaded PDF objects in memory.
- Task completion, cancellation, and failure clean the staged upload directory.
- Pipeline/VLM paths share more of the Markdown final-formatting and Middle JSON
  rendering behavior.

## 5. Portability and External Runtime Discovery

After `install.bat` / `install.sh` / `install.command`, the core local path is
usable without a second virtual environment: the project creates `.venv`, and
Pipeline child processes select that interpreter automatically.

Optional external runtimes use controlled discovery:

| Backend family | Discovery order | What 0.7 does not do |
| --- | --- | --- |
| MinerU | `CONTEXTURE_MINERU_PYTHON`, `CONTEXTURE_MINERU_COMMAND`, `CONTEXTURE_MINERU_SOURCE_ROOT`; then `PATH`; then documented sibling checkout patterns | Does not scan arbitrary disks or install MinerU automatically. |
| Paddle | `CONTEXTURE_PADDLE_PYTHON`; then documented sibling Paddle checkout patterns | Does not install Paddle/PaddleOCR automatically. |
| Tesseract | `PATH` and standard Windows installation locations | Does not bundle the system OCR executable. |
| VLM services | Explicit endpoint, model, and user-supplied credential/profile | Does not discover or trust arbitrary network services. |
| Chrome ScreenAI | Existing Chrome Screen AI component or local `locro` component directory | Does not download the component automatically when it is absent. |

The backend doctor reports missing or unconfigured optional capabilities before
they are selected. A configured sidecar can still fail later if its own model
weights or Python dependencies are incomplete.

## 6. Security and Release Hygiene

0.7 removes local API profiles, application state, private filesystem paths,
logs, outputs, model caches, virtual environments, and generated bytecode.

The release package contains only empty or environment-variable-based API
configuration surfaces. Public model, package, and documentation URLs remain
where required for installation and backend documentation.

The final release audit found no obvious secret, private path, or cache residue.
A conservative secondary scanner reports only generic platform discovery code
and diagnostic strings; it found no high-risk credential material.

## 7. Verification Performed

- Compiled the runtime source and imported the primary application entry path.
- Checked the POSIX install/start scripts with `bash -n`.
- Built `aih_contexture-0.7.0-py3-none-any.whl` with Python 3.12 and verified
  that it contains the runtime package but no tests, bytecode, or API profiles.
- Ran two final sensitive-information audits and verified that the release has
  no tests, caches, outputs, virtual environment, or generated runtime state.

The full installer was not re-run from an empty machine because it downloads
the declared Python dependencies and public OCR model weights. The installation
scripts, dependency manifests, source build, and runtime imports were verified.

## 8. Known Architecture Debt

The original 0.5 architecture review remains materially relevant. The following
items are intentionally not presented as solved in 0.7:

- `runtime/runner.py` still dispatches runtime modes with an explicit `if`
  chain rather than a mode registry.
- The processor chain still relies on ordering rather than declared processor
  dependencies and topological validation.
- Runtime error types remain shallow; backend timeout, authentication, resource,
  and page-level conversion errors are not yet a complete hierarchy.
- Mode-wide configuration is still largely dictionary-driven instead of using
  one validated Pydantic model per mode.
- Chrome ScreenAI has local discovery behavior but no dedicated backend-doctor
  diagnostic yet.

These are maintainability and service-evolution risks, not blockers for the
current local single-user release. Future feature work should address them
before claiming a multi-user or service-oriented deployment model.

# Middle storage and rendering performance

Ordinary Middle saves encode large span lists with `zlib-json-spans/1` when
encoding is smaller. Block text, block order, page identity, metadata and resources
remain ordinary JSON. The encoding restores every compact span value exactly;
it does not derive words from paragraph offsets or estimate coordinates.

Encoded files declare `schema_version: contexture-middle-storage/1` and a
`storage_encoding` header containing the original canonical schema version.
Each encoded block has `span_storage` instead of `spans`, including its count,
uncompressed byte length, SHA-256 and base64 zlib payload. Smaller span lists
remain unchanged. Files without encoded lists keep the canonical schema.

Use `aih_contexture.middle.storage.load_middle_json(path)` or
`decode_middle_storage(payload)` before traversing spans yourself. Current
rendering, validation, UI postprocessing, CLI, evaluation, overlays, external
OCR merge and external layout loading entry points decode supported storage.
Canonical historical files continue to work. Unknown or damaged encoding fails
explicitly rather than silently dropping evidence.

Older applications and third-party scripts that expect the canonical schema
cannot consume encoded spans directly. For that interchange, set
`middle_storage_compression: false` in the save render configuration, or request
the existing `emit_middle_full_json` artifact. Full exports remain plain JSON
and retain rich source span details. Native recognition JSON, XML and HTML
retain their existing protocols. Existing source files are not rewritten.

The codec changes storage size, not the canonical in-memory geometry size.
Decoding has an additional cost; repeated decodes are avoided after entering
the canonical processing path.

Rendering builds page and footnote indexes only within `Document.render`.
They expire on success or failure, are absent from serialized models, and are
rebuilt for the next render. The private resolved-render token reuses work only
inside the same preparation transaction with supported semantics. Classical
projection still performs the required semantic pass after changing text.
Public calls continue to isolate source objects and validate changed options.

Saving without a reading export skips discarded Markdown generation and omits
its obsolete page manifest. Actual reading exports still generate and bind the
manifest. Diagnostics remain opt-in separate artifacts and add no reading text.

Save, re-render and load pause the cyclic garbage collector for the duration of
the transaction (`aih_contexture.utils.gc_pause`). A whole-book Middle holds
millions of small objects that the collector would otherwise traverse
repeatedly. Reference counting still frees garbage immediately; outputs and
peak memory are unchanged.

## Lean geometry profile (fast mode)

`middle_geometry_profile: lean` (CLI `--middle_geometry_profile lean`, UI
"快速模式") drops per-word spans before semantic resolution. Block text, bbox,
attributes, order and page structure are kept. Saving and re-rendering no longer
scale with word count, and the stored Middle is typically a quarter of the
full size. The default is `full`.

Lean is not applied, and the full profile is used with a log warning, when any
effective request needs word geometry: `classical_marginalia_mode` other than
`off` (explicit or from the stored `reading_render_options`), span overlays, or
`emit_middle_full_json`.

A lean Middle records `metadata.geometry_profile: lean`. Re-rendering it with
classical marginalia reports the analysis as unavailable, the same path used for
inputs without reliable coordinates, rather than running it on block boxes.
Re-saving a lean Middle keeps it lean; to recover word geometry, export again
from the original recognition output.

Lean output can differ from full where word geometry confirms a decision. One
example: a bare page number that the full profile confirms and removes stays in
the body text, because unconfirmed folios are never deleted.

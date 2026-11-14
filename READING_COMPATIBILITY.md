# Reading compatibility

Reading artifacts preserve source wording when semantic evidence is insufficient.
Diagnostics remain separate, opt-in artifacts; they are not required for pagination.

## Page identity and navigation

`metadata.reading_page_manifest` is optional operational metadata (version 1).
It binds page slices to the SHA-256 of the final Markdown after BOM removal and
LF newline normalization. Offsets count Unicode code points, not UTF-8 bytes or
UTF-16 units. Every source page has a distinct input index; historical slices
retain nonconsecutive indices. The terminal anchor does not add an input page.

The renderer produces slices directly while joining pages. Readers validate the
digest, ranges and identities before using them. Missing or stale metadata uses
the compatible Markdown parser. Code and mathematical structures retain their
protection. An unpaired prose delimiter cannot claim all following pages.

## Numeric evidence

Semantic analysis, fingerprints and compact storage share a four-decimal numeric
projection. Original recognition JSON remains unchanged. Candidate removal at
geometric thresholds requires a margin exceeding the quantization uncertainty;
ambiguous candidates retain their source text. Meaningful source edits and
configuration changes invalidate derived decisions.

## Reading and native formats

The native protocol JSON/XML/HTML remains available with its existing semantics.
An explicitly requested scholarly Markdown uses the shared Middle rendering
contract. When both scholarly output and HTML are requested in the VLM saver,
`_middle_scholarly.html` is derived from that exact saved scholarly Markdown.
This preserves the native HTML contract while providing a matching reading pair.

Prose literals are escaped without stripping the surrounding text. Explicit
mathematics, code, links and supported structural HTML retain their syntax.
Plain multi-letter abbreviations cannot establish footnote identifiers solely
because they end in a period. Explicit superscripts and supported numeric,
single-letter, roman and symbolic note calls remain supported.

## Postprocessing

Source Middle blocks remain the recognition record. A final postprocessed reading
has its own content-bound page manifest and `reading_postprocess` lineage hashes.
The lineage is not an instruction to invoke a model. Re-rendering starts from the
recorded source; applying the same explicit postprocessing operation reproduces
the derived result. Arbitrary prose edits are not projected into word geometry
or silently substituted for the recognition record. Ambiguous boundary edits
invalidate the derived index rather than retaining stale offsets.

The UI reads saved text, validates paired metadata, resets incompatible state on
file switches, and retains the same input page when it still exists after a
re-render. No additional explanatory text is inserted into the reading body.

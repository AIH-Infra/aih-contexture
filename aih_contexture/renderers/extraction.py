from pydantic import BaseModel

from aih_contexture.extractors.document import DocumentExtractionSchema
from aih_contexture.renderers import BaseRenderer


class ExtractionOutput(BaseModel):
    analysis: str
    document_json: str
    original_markdown: str


class ExtractionRenderer(BaseRenderer):
    def __call__(
        self, output: DocumentExtractionSchema, markdown: str
    ) -> ExtractionOutput:
        # We definitely want to do more complex stuff here soon, so leave it in
        return ExtractionOutput(
            analysis=output.analysis,
            document_json=output.document_json,
            original_markdown=markdown,
        )

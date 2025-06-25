from pydantic import BaseModel

from marker.extractors.document import DocumentExtractionSchema
from marker.renderers import BaseRenderer


class ExtractionOutput(BaseModel):
    analysis: str
    document_json: str


class ExtractionRenderer(BaseRenderer):
    def __call__(self, output: DocumentExtractionSchema) -> ExtractionOutput:
        # We definitely want to do more complex stuff here soon, so leave it in
        return ExtractionOutput(
            analysis=output.analysis, document_json=output.document_json
        )

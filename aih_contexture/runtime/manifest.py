from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

JobStatus = Literal["queued", "running", "partial", "succeeded", "failed", "cancelled", "retryable"]

@dataclass(slots=True)
class JobManifest:
    job_id: str
    mode: str
    input_name: str | None = None
    status: JobStatus = "queued"
    completed_pages: list[int] = field(default_factory=list)
    failed_pages: list[int] = field(default_factory=list)
    retryable_pages: list[int] = field(default_factory=list)
    backends: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def mark_page_completed(self, page: int) -> None:
        if page not in self.completed_pages:
            self.completed_pages.append(page)
        self.failed_pages = [p for p in self.failed_pages if p != page]
        self.retryable_pages = [p for p in self.retryable_pages if p != page]

    def mark_page_failed(self, page: int, error: str, *, retryable: bool = True) -> None:
        if page not in self.failed_pages:
            self.failed_pages.append(page)
        if retryable and page not in self.retryable_pages:
            self.retryable_pages.append(page)
        self.errors.append({"page": page, "message": error, "retryable": retryable})
        self.status = "retryable" if retryable else "partial"

    def retry_pages(self) -> list[int]:
        return sorted(set(self.retryable_pages) - set(self.completed_pages))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobManifest":
        return cls(**data)

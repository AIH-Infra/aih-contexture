from dataclasses import dataclass, field
from typing import Any


@dataclass
class PrintedPageAction:
    pdf_page: int
    action: str
    raw_candidate: str | None = None
    final_printed_page: str | None = None
    confidence: float | None = None
    reason_tag: str | None = None
    source: str | None = None


@dataclass
class MarkdownPostprocessResult:
    markdown: str
    changed: bool = False
    warnings: list[str] = field(default_factory=list)
    actions: list[PrintedPageAction] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        llm_meta = self.metadata.get("llm", {}) if isinstance(self.metadata, dict) else {}
        review_only = bool(self.metadata.get("review_only")) if isinstance(self.metadata, dict) else False
        applied_action_count = sum(1 for action in self.actions if action.source != "rule" or not review_only)
        suggested_action_count = len(llm_meta.get("suggested_actions", [])) if isinstance(llm_meta, dict) else 0
        error_count = len(llm_meta.get("errors", [])) if isinstance(llm_meta, dict) else 0
        status = llm_meta.get("status") if isinstance(llm_meta, dict) and llm_meta.get("status") else (
            "review_only" if review_only else "applied"
        )
        return {
            "changed": self.changed,
            "status": status,
            "mode": "review" if review_only else "apply",
            "warnings": self.warnings,
            "action_count": len(self.actions),
            "applied_action_count": llm_meta.get("applied_action_count", applied_action_count),
            "suggested_action_count": suggested_action_count,
            "error_count": error_count,
            "skipped_reason": llm_meta.get("skipped_reason") if isinstance(llm_meta, dict) else None,
            "actions": [
                {
                    "pdf_page": action.pdf_page,
                    "action": action.action,
                    "raw_candidate": action.raw_candidate,
                    "final_printed_page": action.final_printed_page,
                    "confidence": action.confidence,
                    "reason_tag": action.reason_tag,
                    "source": action.source,
                }
                for action in self.actions
            ],
            "metadata": self.metadata,
        }
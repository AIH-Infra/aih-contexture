import json
from types import SimpleNamespace

from aih_contexture.postprocess.markdown_config import MarkdownPostprocessConfig
from aih_contexture.postprocess.printed_page_repair import (
    PrintedPageCandidate,
    PrintedPageReviewPage,
    PrintedPageReviewSpan,
    build_segment_review_proposals,
    parse_markdown_pages,
    _replace_block_comment,
    _roman_to_int,
)
from aih_contexture.postprocess.reporting import MarkdownPostprocessResult, PrintedPageAction


class MarkdownLMAdapter:
    def __init__(self, config: MarkdownPostprocessConfig | dict | None = None, service=None):
        if isinstance(config, dict):
            self.config = MarkdownPostprocessConfig(**{
                key: value for key, value in config.items() if key in MarkdownPostprocessConfig.__dataclass_fields__
            })
        else:
            self.config = config or MarkdownPostprocessConfig()
        self.service = service

    def _build_safe_review_spans(self, markdown: str) -> list[PrintedPageReviewSpan]:
        proposal_payload = build_segment_review_proposals(markdown)
        proposals = proposal_payload.get("proposals", []) if isinstance(proposal_payload, dict) else []
        if not proposals:
            return []

        pages = parse_markdown_pages(markdown)
        page_lookup = {page.pdf_page: page for page in pages}
        review_pages: list[PrintedPageReviewPage] = []

        for proposal in proposals:
            pdf_page = proposal.get("pdf_page")
            action = proposal.get("action")
            proposed_value = proposal.get("proposed_value")
            if not isinstance(pdf_page, int) or action not in {"replace", "fill_null", "delete_to_null"}:
                continue
            page = page_lookup.get(pdf_page)
            if page is None:
                continue
            segment_kind = proposal.get("segment_kind") or page.candidate_kind
            if segment_kind not in {"arabic", "roman"}:
                continue

            candidates: list[PrintedPageCandidate] = []
            seen: set[tuple[str | None, str]] = set()

            def add_candidate(value: str | None, candidate_action: str, reason_tag: str, confidence: float):
                key = (value, candidate_action)
                if key in seen:
                    return
                seen.add(key)
                candidates.append(
                    PrintedPageCandidate(
                        value=value,
                        action=candidate_action,
                        reason_tag=reason_tag,
                        confidence=confidence,
                    )
                )

            if page.normalized_candidate is not None:
                add_candidate(page.normalized_candidate, "keep", "current_value", 0.9)
            else:
                add_candidate(None, "leave_null", "current_value", 0.9)

            reason_tag = str(proposal.get("reason_tag") or "segment_review_proposal")
            confidence = float(proposal.get("confidence") or 0.9)
            add_candidate(proposed_value, action, reason_tag, confidence)

            if action != "delete_to_null":
                add_candidate(None, "leave_null", "conservative_null", 0.7)
                if page.raw_candidate is not None and page.normalized_candidate is None:
                    add_candidate(None, "delete_to_null", "conservative_null", 0.7)

            review_pages.append(
                PrintedPageReviewPage(
                    pdf_page=pdf_page,
                    current_value=page.normalized_candidate,
                    current_kind=page.candidate_kind,
                    segment_kind=segment_kind,
                    candidates=candidates,
                )
            )

        if not review_pages:
            return []

        spans: list[PrintedPageReviewSpan] = []
        current_pages: list[PrintedPageReviewPage] = []
        current_segment = review_pages[0].segment_kind

        def flush_span() -> None:
            if not current_pages:
                return
            first_pdf = current_pages[0].pdf_page
            last_pdf = current_pages[-1].pdf_page
            left_anchor = None
            right_anchor = None
            for page in pages:
                if page.pdf_page < first_pdf and page.candidate_kind == current_segment and page.normalized_candidate is not None:
                    left_anchor = page.normalized_candidate
                if page.pdf_page > last_pdf and page.candidate_kind == current_segment and page.normalized_candidate is not None:
                    right_anchor = page.normalized_candidate
                    break
            spans.append(
                PrintedPageReviewSpan(
                    start_pdf_page=first_pdf,
                    end_pdf_page=last_pdf,
                    pages=list(current_pages),
                    left_anchor_value=left_anchor,
                    right_anchor_value=right_anchor,
                    segment_kind=current_segment,
                )
            )

        for review_page in review_pages:
            contiguous = current_pages and review_page.pdf_page == current_pages[-1].pdf_page + 1
            same_segment = review_page.segment_kind == current_segment
            if current_pages and not (contiguous and same_segment):
                flush_span()
                current_pages = []
                current_segment = review_page.segment_kind
            if not current_pages:
                current_segment = review_page.segment_kind
            current_pages.append(review_page)

        flush_span()
        return spans

    def _build_openai_service(self):
        base_url = (self.config.markdown_postprocess_llm_base_url or "").strip()
        model = (self.config.markdown_postprocess_llm_model or "").strip()
        api_key = self.config.markdown_postprocess_llm_api_key
        if not base_url or not model:
            return None
        from aih_contexture.services.openai import OpenAIService

        return OpenAIService({
            "openai_base_url": base_url,
            "openai_model": model,
            "openai_api_key": api_key or "lm-studio",
            "timeout": self.config.markdown_postprocess_llm_timeout,
            "max_retries": self.config.markdown_postprocess_llm_max_retries,
            "max_output_tokens": 4096,
            "vlm_response_mode": "json",
        })

    def _build_lmstudio_native_service(self):
        base_url = (self.config.markdown_postprocess_llm_base_url or "").strip()
        model = (self.config.markdown_postprocess_llm_model or "").strip()
        api_key = self.config.markdown_postprocess_llm_api_key
        if not base_url or not model:
            return None
        from aih_contexture.services.lmstudio_native import LMStudioNativeService

        service = LMStudioNativeService()
        service.lmstudio_base_url = base_url
        service.lmstudio_model = model
        service.lmstudio_api_key = api_key or "lm-studio"
        service.timeout = int(self.config.markdown_postprocess_llm_timeout)
        service.max_retries = int(self.config.markdown_postprocess_llm_max_retries)
        return service

    def _ensure_service(self):
        if self.service is not None:
            return self.service
        provider = (self.config.markdown_postprocess_llm_provider or "").strip().lower()
        if provider == "openai":
            self.service = self._build_openai_service()
        elif provider == "lmstudio_native":
            self.service = self._build_lmstudio_native_service()
        return self.service

    def _build_review_prompt(self, span) -> str:
        payload = {
            "segment_kind": span.segment_kind,
            "start_pdf_page": span.start_pdf_page,
            "end_pdf_page": span.end_pdf_page,
            "left_anchor_value": span.left_anchor_value,
            "right_anchor_value": span.right_anchor_value,
            "pages": [
                {
                    "pdf_page": page.pdf_page,
                    "current_value": page.current_value,
                    "current_kind": page.current_kind,
                    "segment_kind": page.segment_kind,
                    "candidates": [
                        {
                            "value": candidate.value,
                            "action": candidate.action,
                            "reason_tag": candidate.reason_tag,
                            "confidence": candidate.confidence,
                        }
                        for candidate in page.candidates
                    ],
                }
                for page in span.pages
            ],
        }
        return (
            "You are reviewing printed page-number repair candidates for one local markdown span. "
            "Return strict JSON only. Do not output prose outside JSON. Do not rewrite markdown. "
            "Only choose from the provided candidates for each page.\n\n"
            "Return JSON with keys: decisions, analysis.\n"
            "decisions must be a list of sparse actions.\n"
            "Each decision item must contain: pdf_page, action, chosen_value, reason.\n"
            "Use chosen_value null for leave_null/delete_to_null.\n"
            "If no change is needed for a page, omit it from decisions.\n"
            "Be conservative: if uncertain, prefer omitting the page or choosing leave_null/delete_to_null.\n\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _extract_review_payload(self, response, service):
        parsed = response
        if isinstance(response, dict) and isinstance(response.get("decisions"), list):
            return response
        if hasattr(service, "_extract_json_any"):
            raw_text = None
            if isinstance(response, dict):
                raw_text = response.get("_raw_text")
            if raw_text:
                reparsed = service._extract_json_any(raw_text)
                if reparsed is not None:
                    parsed = reparsed
            else:
                reparsed = service._extract_json_any(json.dumps(response, ensure_ascii=False))
                if reparsed is not None:
                    parsed = reparsed
        return parsed

    def _validate_decision(self, page_lookup, decision, span):
        if not isinstance(decision, dict):
            return None, "decision_not_object"
        pdf_page = decision.get("pdf_page")
        if not isinstance(pdf_page, int):
            return None, "missing_pdf_page"
        review_page = page_lookup.get(pdf_page)
        if review_page is None:
            return None, "pdf_page_outside_span"

        action = str(decision.get("action") or "").strip()
        if action not in {"replace", "fill_null", "leave_null", "delete_to_null", "keep"}:
            return None, "invalid_action"

        chosen_value = decision.get("chosen_value")
        if chosen_value is not None:
            chosen_value = str(chosen_value).strip() or None

        candidate_keys = {(candidate.value, candidate.action) for candidate in review_page.candidates}
        if action == "keep":
            return None, None
        if (chosen_value, action) not in candidate_keys:
            return None, "decision_not_in_candidates"

        if action in {"leave_null", "delete_to_null"} and chosen_value is not None:
            return None, "null_action_requires_null_value"
        if action in {"replace", "fill_null"} and chosen_value is None:
            return None, "value_action_requires_value"

        segment_kind = span.segment_kind
        if segment_kind == "arabic" and chosen_value is not None and not chosen_value.isdigit():
            return None, "segment_kind_mismatch"
        if segment_kind == "roman" and chosen_value is not None and chosen_value.isdigit():
            return None, "segment_kind_mismatch"

        return {
            "pdf_page": pdf_page,
            "action": action,
            "chosen_value": chosen_value,
            "reason": str(decision.get("reason") or "").strip() or "llm_sparse_review",
        }, None

    def _validate_span_continuity(self, pages_by_pdf, span, accepted_decisions: list[dict]):
        decision_map = {decision["pdf_page"]: decision for decision in accepted_decisions}
        numeric_values: list[int] = []

        for review_page in span.pages:
            page = pages_by_pdf.get(review_page.pdf_page)
            if page is None:
                continue
            final_value = page.normalized_candidate
            decision = decision_map.get(review_page.pdf_page)
            if decision is not None:
                final_value = decision["chosen_value"]
            if final_value is None:
                continue
            if span.segment_kind == "arabic":
                if not str(final_value).isdigit():
                    return False, "span_continuity_kind_mismatch"
                numeric_values.append(int(final_value))
            else:
                numeric = _roman_to_int(str(final_value))
                if numeric is None:
                    return False, "span_continuity_kind_mismatch"
                numeric_values.append(numeric)

        if len(numeric_values) < 2:
            return True, None

        deltas = [b - a for a, b in zip(numeric_values, numeric_values[1:])]
        if any(delta < 0 for delta in deltas):
            return False, "span_continuity_regression"
        if sum(1 for delta in deltas if delta not in {0, 1}) >= 2:
            return False, "span_continuity_large_jumps"
        return True, None

    def _apply_sparse_decisions(self, result: MarkdownPostprocessResult, accepted_decisions: list[dict]):
        if not accepted_decisions:
            return result, 0

        rewritten = result.markdown
        pages = {page.pdf_page: page for page in parse_markdown_pages(result.markdown)}
        applied = 0

        for decision in accepted_decisions:
            page = pages.get(decision["pdf_page"])
            if page is None:
                continue
            final_value = decision["chosen_value"]
            original = page.normalized_candidate
            if final_value == original:
                continue
            new_block = _replace_block_comment(page.raw_block, final_value)
            rewritten = rewritten.replace(page.raw_block, new_block, 1)
            pages[page.pdf_page] = SimpleNamespace(**{**page.__dict__, "raw_block": new_block, "normalized_candidate": final_value})
            result.actions.append(
                PrintedPageAction(
                    pdf_page=page.pdf_page,
                    action=decision["action"],
                    raw_candidate=original,
                    final_printed_page=final_value,
                    confidence=0.9,
                    reason_tag=decision["reason"],
                    source="llm",
                )
            )
            applied += 1

        if applied:
            result.markdown = rewritten
            result.changed = True
        return result, applied

    def enhance(self, markdown: str, result: MarkdownPostprocessResult) -> MarkdownPostprocessResult:
        result.metadata.setdefault("llm", {})
        llm_meta = result.metadata["llm"]
        llm_meta["provider"] = self.config.markdown_postprocess_llm_provider
        llm_meta["base_url"] = self.config.markdown_postprocess_llm_base_url
        llm_meta["model"] = self.config.markdown_postprocess_llm_model
        llm_meta["invoked"] = False
        llm_meta["mode"] = "sparse_page_repair"
        llm_meta["status"] = "pending"

        service = self._ensure_service()
        if service is None:
            llm_meta["skipped_reason"] = "llm_not_configured"
            return result

        spans = self._build_safe_review_spans(result.markdown)
        llm_meta["span_source"] = "segment_review_proposals"
        llm_meta["span_count"] = len(spans)
        llm_meta["configured_model"] = getattr(service, "openai_model", None) or getattr(service, "lmstudio_model", None)
        llm_meta["configured_base_url"] = getattr(service, "openai_base_url", None) or getattr(service, "lmstudio_base_url", None)

        if not spans:
            llm_meta["span_count"] = 0
            llm_meta["status"] = "no_safe_segment_proposals"
            llm_meta["skipped_reason"] = "no_safe_segment_proposals"
            return result

        llm_meta["invoked"] = True
        llm_meta["reviews"] = []
        accepted_decisions: list[dict] = []
        validator_rejections: list[dict] = []
        raw_payloads: list[str] = []

        response_schema = type(
            "MarkdownSparsePageRepairResponse",
            (),
            {
                "model_json_schema": staticmethod(
                    lambda: {
                        "type": "object",
                        "properties": {
                            "decisions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "pdf_page": {"type": "integer"},
                                        "action": {"type": "string"},
                                        "chosen_value": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                        "reason": {"type": "string"},
                                    },
                                    "required": ["pdf_page", "action", "chosen_value", "reason"],
                                },
                            },
                            "analysis": {"type": "string"},
                        },
                        "required": ["decisions", "analysis"],
                    }
                )
            },
        )

        for span in spans:
            prompt = self._build_review_prompt(span)
            try:
                response = service(prompt=prompt, image=None, block=None, response_schema=response_schema)
                parsed = self._extract_review_payload(response, service)
                review_record = {
                    "span": {
                        "start_pdf_page": span.start_pdf_page,
                        "end_pdf_page": span.end_pdf_page,
                        "segment_kind": span.segment_kind,
                    },
                    "review": parsed,
                }
                if isinstance(response, dict) and response.get("_raw_text"):
                    raw_payloads.append(response["_raw_text"])
                    review_record["raw_response_text"] = response.get("_raw_text")

                decisions = parsed.get("decisions") if isinstance(parsed, dict) else None
                if not isinstance(decisions, list):
                    review_record["skipped_reason"] = "invalid_decisions"
                    llm_meta["reviews"].append(review_record)
                    continue

                page_lookup = {page.pdf_page: page for page in span.pages}
                valid_for_span: list[dict] = []
                span_rejections: list[dict] = []
                for decision in decisions:
                    accepted, reject_reason = self._validate_decision(page_lookup, decision, span)
                    if accepted is not None:
                        valid_for_span.append(accepted)
                    elif reject_reason:
                        span_rejections.append({"decision": decision, "reason": reject_reason})

                continuity_ok, continuity_reason = self._validate_span_continuity(
                    {page.pdf_page: page for page in parse_markdown_pages(result.markdown)},
                    span,
                    valid_for_span,
                )
                if not continuity_ok and valid_for_span:
                    continuity_rejections = [
                        {"decision": decision, "reason": continuity_reason}
                        for decision in valid_for_span
                    ]
                    span_rejections.extend(continuity_rejections)
                    valid_for_span = []

                if span_rejections:
                    validator_rejections.extend(span_rejections)
                    review_record["validator_rejections"] = span_rejections
                review_record["accepted_decisions"] = valid_for_span
                accepted_decisions.extend(valid_for_span)
                llm_meta["reviews"].append(review_record)
            except Exception as exc:
                llm_meta.setdefault("errors", []).append(
                    {
                        "span_start_pdf_page": span.start_pdf_page,
                        "span_end_pdf_page": span.end_pdf_page,
                        "error": str(exc),
                    }
                )

        llm_meta["accepted_decision_count"] = len(accepted_decisions)
        llm_meta["validator_rejections"] = validator_rejections
        llm_meta["suggested_actions"] = accepted_decisions
        if raw_payloads:
            llm_meta["raw_response_texts"] = raw_payloads

        if not accepted_decisions:
            llm_meta["status"] = "review_completed_no_actions"
            if validator_rejections:
                llm_meta["skipped_reason"] = "all_decisions_rejected"
            elif llm_meta.get("errors"):
                llm_meta["skipped_reason"] = "llm_review_failed"
            return result

        if self.config.markdown_postprocess_review_only:
            llm_meta["status"] = "review_completed_suggestions_only"
            llm_meta["applied_action_count"] = 0
            llm_meta["suggested_actions"] = accepted_decisions
            return result

        result, applied_count = self._apply_sparse_decisions(result, accepted_decisions)
        llm_meta["applied_action_count"] = applied_count
        llm_meta["status"] = "applied" if applied_count else "review_completed_no_effective_actions"
        if applied_count == 0:
            llm_meta["skipped_reason"] = "no_effective_sparse_actions"
        return result

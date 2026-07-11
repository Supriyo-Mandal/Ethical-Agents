from __future__ import annotations

import json
import math
import re
from typing import Any

from app.config import THRESHOLD
from app.services.fireworks_client import call_fireworks
from app.services.knowledge_repository import append_new_fields, load_prompt, load_repository

# ── Document-level governance signals ─────────────────────────────────
# These patterns distinguish responsible AI documents (which explicitly
# describe safeguards) from irresponsible ones (which dismiss safeguards).
#
# The governance multiplier is computed by scanning the raw document text.
# Positive docs will have many governance affirmations and few dismissals.
# Negative/irresponsible docs have many dismissals and use governance words
# only in dismissal context ("validation is unnecessary", etc.).

# Phrases that appear in responsible AI documents as positive features.
# Important: these are multi-word so they are less likely to appear in
# dismissal context.  Single words like "validation" are NOT included
# because irresponsible docs also mention them ("validation is unnecessary").
_GOVERNANCE_PHRASES: list[str] = [
    # Human oversight — explicit positive statements
    "human review", "human oversight", "human in the loop", "human approval",
    "human decision", "human supervision", "human-in-the-loop",
    "operator review", "expert review", "reviewed by",
    "requires human", "human operator", "human experts",
    # Audit / traceability
    "audit trail", "audit log", "audit record", "traceable audit",
    "transparent reasoning", "explainable reasoning",
    "traceability", "traceable decision",
    # Explainability as a feature
    "explainable ai", "explainable recommendation", "explainable decision",
    "explainability is", "includes explainability", "provides explainability",
    # Phased / validated deployment
    "phased deployment", "phased rollout", "phased approach",
    "pilot deployment", "pilot testing", "prototype testing",
    "proof of concept", "incremental deployment",
    # Validation as an actual activity (not "validation is unnecessary")
    "continuous validation", "clinical validation", "model validation",
    "validated by", "validation process", "validation strategy",
    "tested and validated", "rigorous validation",
    # Governance / compliance as implemented controls
    "data governance", "governance framework", "ethical governance",
    "compliance officer", "regulatory compliance framework",
    "privacy by design", "privacy protection framework",
    "responsible ai", "trustworthy ai",
    # Consent as an implemented mechanism
    "informed consent", "explicit consent", "consent mechanism",
    "consent management process", "data subject consent",
    # Access controls as implemented
    "access control", "role-based access", "authentication",
    "encryption at rest", "end-to-end encryption",
    # Does not replace humans
    "does not replace", "augments human", "assists rather than replac",
    "complement human", "supports human", "human expertise remains",
    "human judgment", "human remains responsible",
    # Bias / fairness as implemented
    "bias mitigation", "fairness evaluation", "bias detection",
    "bias testing", "algorithmic fairness",
    # Risk management as implemented
    "risk mitigation strategy", "risk management framework",
    "risk assessment process", "risk management plan",
    # Feedback loops as implemented
    "human feedback", "operator feedback", "expert feedback",
    "feedback incorporated", "feedback loop",
    # Safety testing as implemented
    "safety testing", "security testing", "penetration testing",
    "cybersecurity assessment", "vulnerability assessment",
]

# Phrases that indicate dismissal of safeguards.  These are characteristic
# of irresponsible AI proposals that skip validation, oversight, and ethics.
_DISMISSAL_PHRASES: list[str] = [
    # Explicit dismissal of safety mechanisms
    "no human review", "human review is unnecessary", "human review is optional",
    "no human oversight", "no longer require", "no longer need",
    "not necessary", "not required", "is unnecessary", "are unnecessary",
    "no need for", "no validation", "validation is unnecessary",
    "testing is unnecessary", "no testing required", "no testing is",
    "no regulatory", "regulatory approval is unnecessary",
    "no clinical trial", "clinical trial is optional", "clinical trial is unnecessary",
    "clinical testing is unnecessary", "no verification",
    "verification is unnecessary", "additional verification is unnecessary",
    # Replacing all humans
    "replace all", "replace every", "replace scientists", "replace doctors",
    "replace engineers", "replace researchers", "replace teachers",
    "replace every", "replacing every",
    "no longer require", "eliminates the need for",
    # Impossible guarantees
    "perfect accuracy", "100% accuracy", "guaranteed to be correct",
    "guaranteed to remain at 100", "always correct", "never incorrect",
    "zero errors", "zero mistakes", "always provides the correct",
    "cannot be wrong", "impossible to be wrong",
    # Self-improving magic
    "automatically correct", "automatically becomes smarter",
    "automatically improves itself", "automatically solve",
    "automatically becomes more intelligent",
    "automatically recognize truth", "automatically becomes correct",
    "automatically reach perfect", "automatically retries until",
    # Ignoring privacy / consent
    "privacy is not", "privacy concerns are not", "privacy is not considered",
    "privacy considerations are not", "permission is not",
    "permission requirements are not", "data ownership is not",
    "patient permission is assumed", "permission to use",
    "assumed because", "is assumed because",
    # No implementation planning
    "no prototype", "no pilot", "no testing planned",
    "no backup plan", "backup plan is unnecessary",
    "no preprocessing", "no data cleaning", "no quality control",
    "no explanation is necessary", "no explanation is provided",
    "no additional verification", "no further analysis",
    # Infinite / unlimited claims
    "unlimited intelligence", "infinite intelligence", "unlimited scalability",
    "infinite scalability", "infinite knowledge", "unlimited knowledge",
    "infinite computational", "unlimited computational",
    # Dismissing governance entirely
    "governance is unnecessary", "ethics is unnecessary",
    "ethical review is unnecessary", "no risk", "no significant risk",
    # Explicit absence of safeguards (short-form negations in risky docs)
    "no audit trail", "no audit log", "no encryption",
    "no access control", "no human review", "no explainability",
    "no data retention", "no gdpr", "no compliance", "no consent",
    "without any human", "fully automated decision", "fully automated",
    "no human oversight", "fully automated without",
]


def _governance_multiplier(text: str) -> float:
    """
    Compute a multiplier in [0.15, 1.0] that scales raw risk scores.

    - Responsible AI documents (many governance hits, few dismissals)
      get a multiplier close to 0.15, collapsing their scores significantly.
    - Irresponsible documents (many dismissals, few real governance phrases)
      get a multiplier close to 1.0, preserving their full risk score.

    Governance phrases are only counted when NOT preceded by negation
    words ("no", "without", "lacking", "absence of") within 40 characters,
    to avoid counting "no human review" or "without audit trail" as positive.

    Formula:
        gov_hits     = distinct governance phrase matches (capped at 20)
        dismiss_hits = distinct dismissal phrase matches  (capped at 20)
        net          = dismiss_hits - gov_hits * 0.6
        multiplier   = sigmoid(net / 4) scaled to [0.15, 1.0]
    """
    lower = text.lower()

    # Negation words that invalidate a governance phrase that follows them
    _NEGATORS = ("no ", "no\n", "without ", "lacking ", "absence of ",
                 "no\t", "not ", "never ")

    def _positive_hit(phrase: str) -> bool:
        """Return True if phrase appears in text NOT preceded by a negator."""
        idx = 0
        while True:
            pos = lower.find(phrase, idx)
            if pos == -1:
                return False
            # Check the 45 chars before this match for negation
            prefix = lower[max(0, pos - 45): pos]
            # Strip to last sentence boundary so we don't look too far back
            for sep in ("\n", ". ", "? ", "! "):
                last = prefix.rfind(sep)
                if last != -1:
                    prefix = prefix[last + 1:]
            negated = any(neg in prefix for neg in _NEGATORS)
            if not negated:
                return True
            idx = pos + 1

    gov_hits     = min(20, sum(1 for p in _GOVERNANCE_PHRASES if _positive_hit(p)))
    dismiss_hits = min(20, sum(1 for p in _DISMISSAL_PHRASES  if p in lower))

    net = dismiss_hits - gov_hits * 0.6
    # sigmoid: net=-12 → ~0.0, net=0 → 0.5, net=+12 → ~1.0
    sig = 1.0 / (1.0 + math.exp(-net / 4.0))
    # Scale to [0.15, 1.0]
    multiplier = 0.15 + 0.85 * sig
    return round(multiplier, 4)


class BaseAgent:
    """
    Domain risk agent following the three-phase evaluation workflow:

    Phase 1 – REASONING
        Load the Domain Knowledge Repository (DKR), read the document,
        compare the two, and identify which existing fields are relevant.

    Phase 2 – ANALYSIS
        Score only the relevant fields and generate an explanation for
        every field whose score meets or exceeds the threshold.

    Phase 3 – LEARNING
        After analysis is complete, call the LLM to check whether the
        document introduces a new reusable risk concept not already in
        the DKR. New fields are only created here, never during scoring.
    """

    def __init__(self, name: str, threshold: float = THRESHOLD) -> None:
        self.name = name
        self.threshold = threshold
        self.agent_key = name.lower()

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #

    def evaluate(
        self,
        document_payload: str | dict[str, Any],
        filename: str | None = None,
    ) -> dict[str, Any]:
        fname = filename or "document"
        text = self._extract_text(document_payload, fname)

        # ── Phase 1: Reasoning ──────────────────────────────────────────
        dkr = load_repository(self.agent_key)
        prompt = load_prompt(self.agent_key)

        relevant_fields = self._select_relevant_fields(text, dkr)

        # ── Phase 2: Analysis ───────────────────────────────────────────
        evaluated_fields, field_scores, field_reasons, overall_score = (
            self._analyze_fields(text, relevant_fields)
        )

        # ── Phase 3: Learning ───────────────────────────────────────────
        # Only trigger learning when the LLM is available AND the DKR
        # appears insufficient (few relevant fields found).
        newly_learned: list[dict[str, Any]] = []
        if isinstance(document_payload, dict):
            newly_learned = self._learn_new_fields(
                prompt, document_payload, text, dkr, overall_score
            )

        return {
            "agent": self.name,
            "agent_name": self.name,
            "overall_score": overall_score,
            "threshold": self.threshold,
            "evaluated_fields": evaluated_fields,
            "field_scores": field_scores,
            "field_reasons": field_reasons,
            "newly_learned_fields": newly_learned,
            "filename": fname,
        }

    # ------------------------------------------------------------------ #
    #  Phase 1 helpers: Reasoning                                          #
    # ------------------------------------------------------------------ #

    def _select_relevant_fields(
        self, text: str, dkr: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Return only DKR entries that have a non-zero relevance signal
        against the document.  Relevance is intentionally permissive
        (any keyword overlap) — the actual risk score is computed later.
        """
        doc_tokens = self._tokenize(text)
        relevant = []
        for entry in dkr:
            if self._is_relevant(entry, doc_tokens):
                relevant.append(entry)
        return relevant

    def _is_relevant(
        self, entry: dict[str, Any], doc_tokens: set[str]
    ) -> bool:
        """
        Returns True only when the document shows a meaningful signal for
        this DKR field.  Two-tier gate:

        1. At least one field-name token (the curated risk label) must
           appear in the document.  A field whose name has zero overlap
           with the document is simply not relevant — description/example
           matches alone are too noisy.

        2. Additionally, at least 2 meaningful tokens from the full entry
           (name + description + examples) must match.  This prevents a
           single coincidental word from triggering scoring.

        Tokens shorter than 4 characters are excluded; very short words
        ("the", "and", "is", …) cause false positives across all documents.
        """
        field_name = str(entry.get("field_name", "")).lower()
        description = str(entry.get("description", "")).lower()
        examples = entry.get("examples") or []

        # Gate 1 — at least one field-name token must be in the document
        name_tokens = {t for t in self._tokenize(field_name) if len(t) > 3}
        if not name_tokens or not (name_tokens & doc_tokens):
            return False

        # Gate 2 — require at least 2 meaningful token matches overall
        full: set[str] = name_tokens | {t for t in self._tokenize(description) if len(t) > 3}
        for e in examples:
            if isinstance(e, str):
                full |= {t for t in self._tokenize(str(e)) if len(t) > 3}

        return len(full & doc_tokens) >= 2

    # ------------------------------------------------------------------ #
    #  Phase 2 helpers: Analysis                                           #
    # ------------------------------------------------------------------ #

    def _analyze_fields(
        self,
        text: str,
        relevant_fields: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, str], float]:
        """
        Score each relevant DKR field against the document and compute
        an overall agent risk score.

        Scoring model (max 1.0):
          • Coverage ratio  : unique DKR tokens found in doc / total DKR tokens  (≤ 0.45)
          • Broad coverage  : fraction of all DKR entry tokens matched            (≤ 0.20)
          • Density bonus   : log-scaled reward for repeated token matches         (≤ 0.25)
          • Prominence bonus: field name terms appearing in first 20 % of doc     (≤ 0.10)

        The raw per-field score is then multiplied by a document-level
        governance multiplier (0.15–1.0) that rewards documents explicitly
        describing responsible AI practices and penalises documents that
        dismiss safeguards, skip validation, or claim impossible guarantees.
        """
        doc_tokens = self._tokenize(text)
        doc_words = re.findall(r"\w+", text.lower())
        doc_len = max(len(doc_words), 1)
        prominent_zone = set(doc_words[: max(1, doc_len // 5)])

        # Governance multiplier — computed once for the whole document
        gov_mult = _governance_multiplier(text)

        evaluated: list[dict[str, Any]] = []

        for entry in relevant_fields:
            field_name = str(entry.get("field_name", "")).strip()
            reason = str(entry.get("reason", "")).strip()
            description = str(entry.get("description", "")).strip()
            examples = entry.get("examples") or []

            raw_score = self._risk_score(
                field_name, description, reason, examples,
                doc_tokens, doc_words, prominent_zone
            )
            if raw_score <= 0.0:
                continue

            # Apply governance multiplier — well-governed docs score lower
            score = round(raw_score * gov_mult, 3)

            evaluated.append(
                {
                    "field_id": entry.get("field_id"),
                    "field_name": field_name,
                    "score": score,
                    "reason": reason,
                }
            )

        if not evaluated:
            return [], {}, {}, 0.0

        # Sort by score descending so the highest-risk fields are first
        evaluated.sort(key=lambda x: x["score"], reverse=True)

        # Overall agent score — ceiling-pull model:
        # High-risk fields (score >= threshold) dominate via score²-weighting.
        # Low-risk fields contribute only 15 % noise and cannot pull the
        # agent score up when no genuine risk is present.
        high_risk = [f for f in evaluated if f["score"] >= self.threshold]
        low_risk  = [f for f in evaluated if f["score"] <  self.threshold]

        if high_risk:
            hr_weight_sum = sum(f["score"] ** 2 for f in high_risk)
            hr_weighted   = sum(f["score"] ** 3 for f in high_risk)
            hr_pull = hr_weighted / hr_weight_sum

            lr_noise = (
                sum(f["score"] for f in low_risk) / len(low_risk) * 0.15
            ) if low_risk else 0.0

            overall = round(min(1.0, hr_pull + lr_noise), 3)
        else:
            overall = round(sum(f["score"] for f in evaluated) / len(evaluated), 3)

        field_scores = {f["field_name"]: f["score"] for f in evaluated}
        field_reasons = {
            f["field_name"]: f["reason"]
            for f in evaluated
            if f["score"] >= self.threshold
        }

        return evaluated, field_scores, field_reasons, overall

    def _risk_score(
        self,
        field_name: str,
        description: str,
        reason: str,
        examples: list[Any],
        doc_tokens: set[str],
        doc_words: list[str],
        prominent_zone: set[str],
    ) -> float:
        """
        Three-component risk score calibrated so that:
        - A benign document with incidental keyword overlaps scores < 0.30
        - A document densely focused on risk concepts scores ≥ 0.70

        Component A – Keyword coverage (max 0.60)
            Fraction of the DKR field's meaningful tokens that appear in
            the document.  Coverage ≥ 0.50 → Component A ≥ 0.45, which
            already signals a meaningful match.

        Component B – Term density (max 0.25)
            Logarithmically scaled reward for repeated mentions of the
            matched terms.  Repeated discussion of a risk topic (not just
            a passing mention) increases this component significantly.

        Component C – Prominence (max 0.15)
            Bonus when field-name terms appear early in the document
            (first 20 %), indicating the topic is a primary concern
            rather than a footnote.
        """
        # ── Tokenize DKR entry ─────────────────────────────────────────
        # Field-name tokens are the primary, curated risk label and carry
        # the most signal.  Description/reason/example tokens provide
        # secondary depth.
        field_tokens: set[str] = {t for t in self._tokenize(field_name) if len(t) > 2}
        desc_tokens: set[str] = {t for t in self._tokenize(description) if len(t) > 2}
        reason_tokens: set[str] = {t for t in self._tokenize(reason) if len(t) > 2}
        example_tokens: set[str] = set()
        for e in examples:
            example_tokens |= {t for t in self._tokenize(str(e)) if len(t) > 2}

        all_dkr_tokens = field_tokens | desc_tokens | reason_tokens | example_tokens
        if not all_dkr_tokens:
            return 0.0

        matched_all = all_dkr_tokens & doc_tokens
        if not matched_all:
            return 0.0

        # ── Component A: field-name coverage (max 0.45) ────────────────
        # How many curated field-name tokens appear in the document?
        # A full name match means the document explicitly discusses the
        # exact risk concept.  This is the dominant signal.
        # If no field-name token matches at all, return 0 immediately —
        # the relevance gate should have caught this, but guard here too.
        if field_tokens:
            fn_matched = field_tokens & doc_tokens
            if not fn_matched:
                return 0.0
            fn_coverage = len(fn_matched) / len(field_tokens)
        else:
            return 0.0
        # Power curve: 50 % name coverage → 0.33; 100 % → 0.45
        score_a = min(0.45, 0.45 * (fn_coverage ** 0.65))

        # ── Component B: broad coverage bonus (max 0.20) ──────────────
        # Fraction of ALL DKR entry tokens that match, rewarding deep
        # discussion rather than a passing mention.
        broad_coverage = len(matched_all) / len(all_dkr_tokens)
        score_b = min(0.20, 0.20 * (broad_coverage ** 0.70))

        # ── Component C: term density (max 0.25) ───────────────────────
        # Count occurrences; field-name hits weighted 2× because they are
        # the most specific indicators of the risk being discussed.
        doc_word_count: dict[str, int] = {}
        for w in doc_words:
            doc_word_count[w] = doc_word_count.get(w, 0) + 1

        fn_hits = sum(doc_word_count.get(t, 0) for t in field_tokens & doc_tokens)
        other_hits = sum(doc_word_count.get(t, 0) for t in (matched_all - field_tokens))
        weighted_hits = fn_hits * 2.0 + other_hits
        # log1p: 2 hits→0.11, 10 hits→0.18, 40 hits→0.23, 120 hits→0.25
        score_c = min(0.25, 0.10 * math.log1p(weighted_hits))

        # ── Component D: prominence bonus (max 0.10) ───────────────────
        # Bonus when field-name tokens appear in the first 20 % of doc
        prominence_hits = len(field_tokens & prominent_zone)
        score_d = min(0.10, prominence_hits * 0.06)

        return round(score_a + score_b + score_c + score_d, 3)

    # ------------------------------------------------------------------ #
    #  Phase 3 helpers: Learning                                           #
    # ------------------------------------------------------------------ #

    def _learn_new_fields(
        self,
        prompt: str,
        document_payload: dict[str, Any],
        text: str,
        dkr: list[dict[str, Any]],
        overall_score: float,
    ) -> list[dict[str, Any]]:
        """
        Ask the LLM whether this document introduces a new reusable risk
        concept not already in the DKR.

        Guard conditions (all must pass before calling the LLM):
        1. The document has real content (non-empty text).
        2. The DKR has fewer than 60 fields (prevents unbounded growth).
        3. Fewer than 3 existing fields were relevant — the DKR may be
           insufficient to capture this document's risk profile.

        This ensures learning is targeted: we only propose new fields when
        the existing DKR is genuinely unable to cover the document.
        """
        if not text.strip():
            return []

        if len(dkr) >= 60:
            return []

        user_content = self._render_payload(document_payload, text)
        fireworks_result = call_fireworks(prompt, user_content)

        if not isinstance(fireworks_result, dict):
            return []

        proposed = self._extract_proposed_fields(fireworks_result, text, dkr)
        if proposed:
            append_new_fields(self.agent_key, proposed)

        return proposed

    def _extract_proposed_fields(
        self,
        fireworks_result: dict[str, Any],
        document_text: str,
        dkr: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Validate LLM-proposed fields before persisting them to the DKR.

        Rejection criteria:
        - No field_name provided
        - Field name already exists in the DKR (case-insensitive)
        - Field name is too long (> 6 words) — suggests a sentence, not a concept
        - Missing description or reason — incomplete fields are not useful
        """
        candidate_fields = fireworks_result.get("candidate_fields") or []
        if not isinstance(candidate_fields, list):
            return []

        existing_names = {
            str(entry.get("field_name", "")).strip().lower()
            for entry in dkr
            if str(entry.get("field_name", "")).strip()
        }

        accepted: list[dict[str, Any]] = []
        for field in candidate_fields:
            if not isinstance(field, dict):
                continue
            field_name = str(field.get("field_name", "")).strip()
            description = str(field.get("description") or "").strip()
            reason = str(field.get("reason") or "").strip()

            if not field_name:
                continue
            if field_name.lower() in existing_names:
                continue
            if len(field_name.split()) > 6:
                continue
            if not description or not reason:
                continue

            accepted.append(
                {
                    "field_name": field_name,
                    "description": description,
                    "reason": reason,
                    "examples": field.get("examples") or [],
                    "document_excerpt": document_text[:240],
                }
            )
            existing_names.add(field_name.lower())

        return accepted

    # ------------------------------------------------------------------ #
    #  Utility helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"\w+", text.lower()))

    def _extract_text(
        self, document_payload: str | dict[str, Any], filename: str
    ) -> str:
        if isinstance(document_payload, dict):
            # Fireworks-style messages payload
            messages = document_payload.get("messages") or []
            if isinstance(messages, list):
                for item in messages:
                    if not isinstance(item, dict):
                        continue
                    content = item.get("content")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and isinstance(
                                block.get("text"), str
                            ):
                                return block["text"]
            # Flat text fields
            for key in ("document_text", "text", "content", "body"):
                val = document_payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val
            return ""
        return str(document_payload or "")

    def _render_payload(
        self, document_payload: str | dict[str, Any], text: str
    ) -> str:
        if isinstance(document_payload, dict):
            return json.dumps(document_payload, indent=2)
        return text

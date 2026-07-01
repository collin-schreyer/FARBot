#!/usr/bin/env python3
"""
GSA US AI API → BedrockClient Adapter

Drop-in replacement for OpenAIBedrockAdapter that routes all LLM calls
through the GSA USAI API (https://api.gsa.usai.gov).
Provides the same interface so the RAG pipeline code works unchanged.
"""

import json
import logging
import os
import re
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

# NOTE: This module now only supplies the prompt/domain logic (the base class);
# BedrockAdapter subclasses it and provides the transport. The USAI (openai/httpx)
# libraries are imported lazily inside USAIAdapter.__init__ so the base class can
# be imported without them. The live system runs on Bedrock, not USAI.

logger = logging.getLogger(__name__)

USAI_BASE_URL = os.getenv(
    "USAI_BASE_URL",
    "https://api.gsa.usai.gov/api/v1"
)
# Default models — override via env
DEFAULT_MODEL = os.getenv("USAI_MODEL", "gemini-2.5-pro")
DEFAULT_CHEAP_MODEL = os.getenv("USAI_CHEAP_MODEL", "gemini-2.5-flash")


# ── Process-wide rate limiter ────────────────────────────────────────────────
# USAI hard-caps requests at 3/second per API key. With multiple workers we
# need a shared limiter so we never exceed that ceiling regardless of how
# many threads we spin up. Set USAI_RATE_LIMIT_RPS to override (default 3).
_USAI_RATE_LIMIT_RPS = float(os.getenv("USAI_RATE_LIMIT_RPS", "3"))


class _RateLimiter:
    """Simple thread-safe token-bucket / sliding-window limiter for N requests/sec."""

    def __init__(self, rps: float):
        self.rps = max(rps, 0.001)
        self.window = 1.0  # seconds
        self._lock = threading.Lock()
        self._timestamps: deque = deque(maxlen=int(self.rps) + 8)

    def acquire(self):
        while True:
            with self._lock:
                now = time.time()
                # drop timestamps older than window
                while self._timestamps and now - self._timestamps[0] >= self.window:
                    self._timestamps.popleft()
                if len(self._timestamps) < int(self.rps):
                    self._timestamps.append(now)
                    return
                # Wait until the oldest timestamp falls out of the window.
                wait_for = self.window - (now - self._timestamps[0]) + 0.005
            time.sleep(max(wait_for, 0.005))


_rate_limiter = _RateLimiter(_USAI_RATE_LIMIT_RPS)



def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response text, handling markdown fencing."""
    if not text:
        return {}
    # Try to find JSON in markdown code block
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    # Try raw JSON
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


class USAIAdapter:
    """
    Adapter that provides the BedrockClient / OpenAIBedrockAdapter interface
    but routes every call to the GSA US AI API.
    """

    def __init__(self, api_key: str = None, model: str = None, cheap_model: str = None):
        self.api_key = api_key or os.getenv("USAI_API")
        if not self.api_key:
            raise ValueError("USAI_API must be set in environment or passed to constructor")
        self.model = model or DEFAULT_MODEL
        self.cheap_model = cheap_model or DEFAULT_CHEAP_MODEL
        import openai
        import httpx
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=USAI_BASE_URL,
            timeout=httpx.Timeout(90.0, connect=10.0),
            max_retries=2,
        )
        self._call_count = 0
        self._total_tokens = 0
        self._stage_logs: List[Dict[str, Any]] = []
        logger.info(f"USAI adapter initialized (model={self.model}, cheap={self.cheap_model}, base_url={USAI_BASE_URL})")

    def _log_stage(self, stage_name: str, duration: float, tokens: int, model: str,
                  system_prompt: str = "", user_prompt: str = "", raw_response: str = ""):
        """Track each LLM call for the stage-by-stage report."""
        self._stage_logs.append({
            "stage": stage_name,
            "duration_ms": round(duration * 1000),
            "tokens": tokens,
            "model": model,
            "call_number": self._call_count,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_response": raw_response,
        })

    def get_stage_logs(self) -> List[Dict[str, Any]]:
        return list(self._stage_logs)

    def clear_stage_logs(self):
        self._stage_logs.clear()

    def _chat(self, system: str, user: str, model: str = None,
              temperature: float = 0.0, max_tokens: int = 1000,
              json_mode: bool = False, stage_name: str = "unknown") -> str:
        """Send a chat completion request to USAI."""
        model = model or self.model
        self._call_count += 1
        start = time.time()

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            # "max_tokens": max_tokens, # Dropped to prevent USAI gateway truncation bugs with Gemini
        }
        # Disable response_format as it causes truncation on some USAI gateway models
        # if json_mode:
        #     kwargs["response_format"] = {"type": "json_object"}

        try:
            logger.info(f"    🌐 USAI API call #{self._call_count}: {stage_name} ({model}) — sending...")
            _rate_limiter.acquire()
            resp = self.client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            tokens = resp.usage.total_tokens if resp.usage else 0
            self._total_tokens += tokens
            elapsed = time.time() - start
            self._log_stage(stage_name, elapsed, tokens, model,
                            system_prompt=system, user_prompt=user, raw_response=text)
            logger.info(f"    ✅ USAI API call #{self._call_count}: {stage_name} — {elapsed:.1f}s, {tokens} tokens")
            return text
        except Exception as e:
            elapsed = time.time() - start
            self._log_stage(f"{stage_name}_ERROR", elapsed, 0, model,
                            system_prompt=system, user_prompt=user, raw_response=str(e))
            logger.error(f"    ❌ USAI API error after {elapsed:.1f}s: {stage_name} — {type(e).__name__}: {e}")
            raise

    def _json_chat(self, system: str, user: str, model: str = None,
                   temperature: float = 0.0, max_tokens: int = 1000,
                   retries: int = 3, stage_name: str = "unknown") -> dict:
        """Chat completion that returns parsed JSON with retry."""
        for attempt in range(retries):
            try:
                text = self._chat(system, user, model=model,
                                  temperature=temperature, max_tokens=max_tokens,
                                  json_mode=True, stage_name=stage_name)
                result = _parse_json_response(text)
                if result:
                    return result
                logger.warning(f"JSON parse attempt {attempt + 1}/{retries} failed, retrying... Raw text:\n{text[:500]}")
            except Exception as e:
                logger.warning(f"API attempt {attempt + 1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    # 429-aware backoff: wait longer if we got rate-limited
                    msg = str(e).lower()
                    if "429" in msg or "rate" in msg:
                        time.sleep(1.5 + attempt * 1.5)
                    else:
                        time.sleep(1)
        return {}

    def get_stats(self):
        return {"calls": self._call_count, "total_tokens": self._total_tokens}

    # ── Default fallback responses ────────────────────────────────────

    def _default_applicability_response(self):
        return {"is_508_applicable": True, "confidence_score": 5,
                "key_eit_indicators": [], "applicability_explanation": "Unable to assess — defaulting to applicable",
                "accessibility_considerations": "Manual review needed",
                "is_physical_only": False, "has_explicit_508_mention": False}

    def _default_compliance_response(self):
        return {"is_compliant": False, "compliance_level": "None",
                "gaps": ["Unable to assess"], "strengths": [],
                "explanation": "Analysis failed — defaulting to non-compliant",
                "is_discussing_508": False, "match_strength": "0"}

    def _default_ict_response(self):
        return {"ict_types": {}, "hardware_component": "No",
                "software_component": "No", "explanation": "Analysis failed"}

    def _default_recommendations(self):
        return ["Manually review document for Section 508 compliance requirements"]

    def _default_validation_response(self):
        return {"is_meaningful_match": False, "reasoning": "Validation failed"}

    # ── Stage 2: 508 Applicability ────────────────────────────────────

    def assess_508_applicability(self, document_text: str, model_id: str = None,
                                 temperature: float = 0.0, max_tokens: int = 1200,
                                 top_p=None, top_k=None) -> dict:
        """
        v4.1 — David's refined applicability classifier (APPLICABILITY_SYSTEM_PROMPT).
        Validated against Cynthia's 1,216 reviews: 83.6% accuracy, 90.3% precision,
        89.6% recall, 89.9% F1.

        The refined prompt returns {applicable, confidence, reasoning,
        ict_elements_found, false_positive_risks, incidental_ict_references}.
        We map those back to the legacy keys (is_508_applicable, confidence_score,
        applicability_explanation, key_eit_indicators, ...) so the rest of the
        pipeline keeps working unchanged.
        """
        system = """You are a Section 508 ICT applicability classifier for U.S. government solicitations.

Your task is to determine whether a solicitation involves the PROCUREMENT, DEVELOPMENT,
MAINTENANCE, or OPERATION of Information and Communication Technology (ICT).

## What counts as ICT (applicable)
- Software applications, platforms, or systems being built or bought
- IT services (development, integration, hosting, help desk, cybersecurity)
- Websites or web applications being developed or maintained
- Electronic content, digital documents, or multimedia being created
- Hardware: computers, servers, networks, telecommunications equipment
- Data systems, databases, or cloud services being procured
- Training delivered via electronic means (e-learning, CBT)

## What does NOT count as ICT (not applicable)
- Physical goods with incidental electronic components (weapons, instruments, vehicles)
- Construction, facilities, or infrastructure projects
- Professional/administrative services with no IT deliverable
- Packaging, preservation, marking, or logistics services
- Solicitations that merely REFERENCE existing government IT systems
  (e.g. "submit reports via WebSDR", "access documents at ASSIST") —
  referencing a system is not the same as procuring one
- Electrostatic discharge (ESD) standards for physical hardware packaging
- Maintenance of physical/mechanical equipment (even if electronically controlled)

## Key distinction — three questions in order

1. Is ICT being procured, developed, or maintained as the PRIMARY deliverable?
   (software, IT services, websites, databases, electronic content)
   → YES to any of these → applicable

2. Is this hardware or a component that serves as a human-facing interface
   with a digital system? (displays, projectors, input devices, audio output,
   terminals, kiosks) OR is it an integral subsystem of a larger ICT system
   subject to 508?
   → YES to either → applicable

3. Is ICT only present as:
   - An administrative tool used during contract performance (submit reports via X)
   - An incidental embedded controller in physical/mechanical equipment
   - A boilerplate FAR clause reference
   - A website referenced for document retrieval only
   → YES to any of these → not applicable

# Very important:
If hardware is being procured as a standalone replacement component for a larger system (not the system itself),
classify based on the component being procured, not the system it feeds into.

## The human interface test
When in doubt ask: "Is this component part of how a human interacts with
or receives information from a digital system?"
Yes → applicable
No  → not applicable

## Output format
Respond ONLY with valid JSON. No preamble, no markdown, no explanation outside the JSON.

{
  "applicable": true or false,
  "confidence": "high", "medium", or "low",
  "reasoning": "2-3 sentences explaining the determination",
  "ict_elements_found": ["list of ICT elements if applicable, empty array if not"],
  "false_positive_risks": ["terms that might look like ICT but aren't in this context"],
  "incidental_ict_references": ["existing systems referenced but not procured"]
}"""
        user = f"Determine if Section 508 applies to this document:\n\n{document_text[:50000]}"
        result = self._json_chat(system, user, temperature=temperature,
                                  max_tokens=max_tokens, stage_name="applicability_v2")
        if not result:
            return self._default_applicability_response()

        # ── Map v4.1 refined-prompt output → legacy keys the pipeline expects ──
        conf_map = {"high": 9, "medium": 6, "low": 3}
        confidence_word = str(result.get("confidence", "medium")).lower()
        return {
            "is_508_applicable": bool(result.get("applicable", False)),
            "confidence_score": conf_map.get(confidence_word, 5),
            "confidence_label": confidence_word,
            "key_eit_indicators": result.get("ict_elements_found", []) or [],
            "applicability_explanation": result.get("reasoning", ""),
            "accessibility_considerations": "",
            "is_physical_only": not bool(result.get("applicable", False)),
            "has_explicit_508_mention": False,
            "is_cots_product": False,
            "ict_complexity": "Medium",
            # carry the refined-prompt extras through for storage/debugging
            "false_positive_risks": result.get("false_positive_risks", []) or [],
            "incidental_ict_references": result.get("incidental_ict_references", []) or [],
            "applicability_prompt_version": "4.1_applicability_v2",
        }

    # ── Stage 3: ICT Classification ───────────────────────────────────

    def analyze_ict_types(self, text: str, model_id: str = None,
                          temperature: float = 0.0, max_tokens: int = 1000,
                          top_p=None, top_k=None) -> dict:
        system = """You are an ICT classification expert for federal procurement. Analyze this solicitation document 
and identify what types of Information and Communication Technology are BEING PROCURED (bought/contracted for).

Only mark a type as true if the solicitation is actually acquiring that type of ICT. 
Do NOT mark true just because the document mentions a website URL, uses email, or references 
technology in passing. The question is: what ICT is the government buying?

For example:
- A solicitation to buy laptops → Hardware=true
- A solicitation for a web application → Web=true, Software=true  
- A solicitation that mentions "submit via email" → Telecommunications=false (email is just the submission method, not what's being procured)
- A solicitation for an MRI machine with software → Hardware=true, Software=true, Medical_Devices=true

Return ONLY valid JSON:
{
  "ict_types": {
    "Web": true/false,
    "Software": true/false,
    "Hardware": true/false,
    "Electronic_Content": true/false,
    "Telecommunications": true/false,
    "Multimedia": true/false,
    "Medical_Devices": true/false
  },
  "hardware_component": "Yes"/"No",
  "software_component": "Yes"/"No",
  "explanation": "brief explanation of what ICT is being procured"
}"""
        user = f"Classify ICT types in this text:\n\n{text[:50000]}"
        result = self._json_chat(system, user, temperature=temperature,
                                  max_tokens=max_tokens, stage_name="ict_classification")
        return result or self._default_ict_response()

    # ── Stage 5: Compliance Analysis ──────────────────────────────────

    def analyze_508_compliance(self, document_text: str, standard_text: str,
                               model_id: str = None, temperature: float = 0.0,
                               max_tokens: int = 800, top_p=None, top_k=None) -> dict:
        system = """You are a federal procurement analyst specializing in Section 508 of the Rehabilitation Act.

Your task is to determine whether this federal solicitation INCLUDES or REFERENCES Section 508 
accessibility requirements for the ICT being procured. You are NOT auditing the document's own 
accessibility — you are checking whether the solicitation requires the vendor/contractor to meet 
Section 508 standards.

Look for ANY of the following indicators that 508 is included:
- Explicit mention of "Section 508" or "Rehabilitation Act"
- References to 36 CFR Part 1194 or the Revised 508 Standards
- Requirements for a VPAT, ACR (Accessibility Conformance Report), or accessibility documentation
- References to WCAG 2.0/2.1, accessibility standards, or assistive technology compatibility
- FAR clause 52.239-70 or similar accessibility-related FAR clauses
- Language requiring ICT to be accessible to people with disabilities
- Requirements for accessibility testing or conformance reporting

Return ONLY valid JSON:
{
  "includes_508": true/false,
  "inclusion_level": "Explicit"/"Implicit"/"None",
  "is_discussing_508": true/false,
  "evidence_strength": 0-10,
  "found_references": ["list of specific 508-related references found in the document"],
  "missing_requirements": ["list of 508 requirements that SHOULD be present but are missing"],
  "strengths": ["list of positive 508 inclusion indicators"],
  "explanation": "detailed assessment of whether and how the solicitation includes 508 requirements"
}"""
        user = (f"Analyze this federal solicitation for inclusion of Section 508 accessibility requirements:\n\n"
                f"Document text:\n{document_text[:50000]}")
        result = self._json_chat(system, user, temperature=temperature,
                                  max_tokens=max_tokens, stage_name="508_inclusion_check")
        return result or self._default_compliance_response()

    # ── BM25 Determination Summary ────────────────────────────────────

    def summarize_bm25_determination(self, verdict: str, is_applicable: bool,
                                     per_file: List[Dict[str, Any]],
                                     title: str = "", model_id: str = None,
                                     temperature: float = 0.0, max_tokens: int = 120) -> dict:
        """
        Generate a short plain-English explanation of WHY the BM25 + ML model
        reached its 508 determination for a solicitation, grounded ONLY in the
        BM25 keyword evidence across all of the solicitation's files.

        Args:
            verdict: "compliant" or "non_compliant" (the solicitation-level call)
            is_applicable: whether Section 508 applies to the procurement
            per_file: list of dicts like
                {"file_name": str, "prediction": "compliant"/"non_compliant",
                 "bm25_bucket": str, "keyword_hits": {term: count}}
            title: solicitation title (context only)

        Returns: {"determination_summary": str}
        """
        # Build a compact evidence block for the model. We still feed the BM25
        # signal so the explanation stays grounded in the actual determination,
        # but the model is instructed to explain the SUBSTANCE (what the files
        # indicate about 508 obligations), not the keyword-matching mechanics.
        lines = []
        for f in per_file:
            kw = f.get("keyword_hits") or {}
            top_terms = ", ".join(k for k, _ in sorted(kw.items(), key=lambda x: -x[1])[:6])
            signal = "508 accessibility language present" if f.get("prediction") == "compliant" \
                     else "no 508 accessibility obligations identified"
            lines.append(
                f"- {f.get('file_name','(unnamed)')}: {signal}"
                + (f" (indicators: {top_terms})" if top_terms else "")
            )
        evidence = "\n".join(lines) if lines else "No files with extractable text."

        if verdict == "compliant":
            verdict_label = "INCLUDES Section 508 accessibility language"
        else:
            verdict_label = "does NOT include Section 508 accessibility language"
        applic_label = "Section 508 applies to this procurement" if is_applicable \
                       else "Section 508 does not apply to this procurement"

        system = (
            "You are a Section 508 compliance analyst summarizing the result of an "
            "automated review pipeline that combines document analysis with a trained "
            "BM25 + ML classifier. Write ONE short, confident sentence (max ~30 words) "
            "explaining the determination in substantive terms — what the solicitation "
            "procures and whether it carries accessibility obligations. Sound like an "
            "analyst, not a search tool: do NOT mention keywords, keyword matches, "
            "scanning, or 'Ctrl+F'-style language. Do NOT list file names. Do NOT "
            "contradict the verdict.\n\n"
            "Return ONLY JSON:\n"
            '{ "determination_summary": "one concise sentence" }'
        )
        user = (
            f"Solicitation: {title or '(untitled)'}\n"
            f"Applicability: {applic_label}.\n"
            f"Final classifier verdict: the solicitation {verdict_label}.\n\n"
            f"Per-file signal:\n{evidence}\n\n"
            f"Write the one-sentence determination_summary."
        )
        result = self._json_chat(system, user, model=model_id, temperature=temperature,
                                  max_tokens=max_tokens, stage_name="bm25_determination_summary")
        if result and result.get("determination_summary"):
            return result
        # Deterministic fallback so the field is never empty.
        return {"determination_summary": self._fallback_bm25_summary(verdict, is_applicable, per_file)}

    @staticmethod
    def _fallback_bm25_summary(verdict: str, is_applicable: bool,
                               per_file: List[Dict[str, Any]]) -> str:
        if verdict == "compliant":
            return ("The solicitation includes Section 508 accessibility requirements "
                    "in its procurement language.")
        if not is_applicable:
            return ("Section 508 does not apply — this procurement does not involve "
                    "covered ICT.")
        return ("Section 508 applies, but the solicitation does not yet include the "
                "required accessibility language.")

    # ── Stage 7: Recommendations ──────────────────────────────────────

    def generate_recommendations(self, document_text=None, model_id: str = None,
                                  temperature: float = 0.0, max_tokens: int = 500,
                                  applicability_result=None, compliance_result=None,
                                  top_p=None, top_k=None,
                                  solicitation_summary=None) -> list:
        system = """You are a Section 508 remediation expert. Generate prioritized recommendations 
for improving Section 508 compliance.

Return ONLY valid JSON:
{
  "recommendations": ["recommendation 1", "recommendation 2", ...],
  "priority": "High"/"Medium"/"Low",
  "estimated_effort": "brief estimate"
}"""
        if solicitation_summary:
            user = f"Generate recommendations based on this analysis:\n{json.dumps(solicitation_summary, indent=2, default=str)[:10000]}"
        elif isinstance(document_text, dict):
            user = f"Generate recommendations based on this analysis:\n{json.dumps(document_text, indent=2, default=str)[:10000]}"
        else:
            context = ""
            if applicability_result:
                context += f"Applicability: {json.dumps(applicability_result, default=str)[:3000]}\n"
            if compliance_result:
                context += f"Compliance: {json.dumps(compliance_result, default=str)[:3000]}\n"
            doc_text = str(document_text or "")[:5000]
            user = f"Document:\n{doc_text}\n\nContext:\n{context}\n\nGenerate remediation recommendations."
        result = self._json_chat(system, user, temperature=temperature,
                                  max_tokens=max_tokens, stage_name="recommendations")
        recs = result.get("recommendations", []) if result else []
        return recs if isinstance(recs, list) else self._default_recommendations()

    # ── Vector match helpers (called by vector_matching.py) ───────────

    def explain_matched_section(self, chunk_text: str, standard_text: str,
                                 model_id: str = None, temperature: float = 0.0,
                                 max_tokens: int = 400, top_p=None, top_k=None) -> str:
        system = """You are a Section 508 compliance expert. Explain why the given solicitation
chunk relates to the matched Section 508 standard. Be specific about the compliance 
implications and what accessibility requirements are relevant."""
        user = (f"Solicitation chunk:\n{chunk_text}\n\n"
                f"Matched 508 Standard:\n{standard_text}\n\n"
                "Explain the relationship and compliance implications.")
        return self._chat(system, user, model=self.cheap_model,
                          temperature=temperature, max_tokens=max_tokens,
                          stage_name="match_explanation")

    def validate_match_explanation(self, match_explanation: str, model_id: str = None,
                                    temperature: float = 0.0, max_tokens: int = 300,
                                    top_p=None, top_k=None) -> dict:
        system = """You are a Section 508 validation expert. Determine if the match explanation 
represents a meaningful, substantive connection to Section 508 compliance requirements 
(not just boilerplate or incidental mention).

A match is NOT meaningful if:
- The "508" reference is actually a measurement, dollar amount, or military document ID
- The match is about generic "compliance" without specifically referencing Section 508
- The explanation is vague without specific accessibility requirements

Return ONLY valid JSON:
{
  "is_meaningful_match": true/false,
  "reasoning": "brief explanation"
}"""
        user = f"Validate this match explanation:\n\n{match_explanation}"
        result = self._json_chat(system, user, model=self.cheap_model,
                                  temperature=temperature, max_tokens=max_tokens,
                                  stage_name="match_validation")
        return result or self._default_validation_response()

    def assess_match_meaningfulness(self, chunk_text: str, standard_text: str,
                                     similarity_score: float, model_id: str = None,
                                     temperature: float = 0.0, max_tokens: int = 300,
                                     top_p=None, top_k=None) -> dict:
        system = """Assess if this vector match is meaningful for Section 508 compliance.
Return ONLY valid JSON:
{
  "is_meaningful_match": true/false,
  "reasoning": "brief explanation",
  "confidence": 0.0-1.0
}"""
        user = (f"Chunk: {chunk_text[:500]}\n\nStandard: {standard_text[:500]}\n\n"
                f"Similarity: {similarity_score}\n\nIs this a meaningful 508 match?")
        result = self._json_chat(system, user, model=self.cheap_model,
                                  temperature=temperature, max_tokens=max_tokens,
                                  stage_name="meaningfulness")
        return result or self._default_validation_response()

    def categorize_compliance_requirement(self, text: str, model_id: str = None,
                                           temperature: float = 0.0, max_tokens: int = 200,
                                           top_p=None, top_k=None) -> dict:
        system = """Categorize the compliance requirement type.
Return ONLY valid JSON: {"category": "...", "confidence": 0.0-1.0}"""
        user = f"Categorize: {text[:1000]}"
        return self._json_chat(system, user, model=self.cheap_model,
                                temperature=temperature, max_tokens=max_tokens,
                                stage_name="categorization") or {"category": "unknown", "confidence": 0.0}

    def generate_key_findings(self, file_summaries: List[str], overall_compliance_status: str,
                               model_id: str = None, temperature: float = 0.0,
                               max_tokens: int = 1000, top_p=None, top_k=None) -> dict:
        system = """Generate key findings from the analysis results.
Return ONLY valid JSON: {"key_findings": ["finding 1", ...], "critical_issues": ["issue 1", ...]}"""
        user = f"Summaries:\n{chr(10).join(file_summaries[:10])}\n\nStatus: {overall_compliance_status}"
        return self._json_chat(system, user, temperature=temperature,
                                max_tokens=max_tokens, stage_name="key_findings") or {"key_findings": [], "critical_issues": []}

    def generate_overall_summary(self, file_summaries: List[str], overall_status: str,
                                  model_id: str = None, temperature: float = 0.0,
                                  max_tokens: int = 1000, top_p=None, top_k=None) -> dict:
        system = """Generate an overall compliance summary.
Return ONLY valid JSON: {"summary": "...", "risk_level": "High/Medium/Low", "action_items": ["..."]}"""
        user = f"Summaries:\n{chr(10).join(file_summaries[:10])}\n\nOverall status: {overall_status}"
        return self._json_chat(system, user, temperature=temperature,
                                max_tokens=max_tokens, stage_name="overall_summary") or {"summary": "", "risk_level": "Unknown", "action_items": []}

    def generate_solicitation_summary_analysis(self, individual_file_analyses=None,
                                                solicitation_id: str = "", model_id: str = None,
                                                temperature: float = 0.0, max_tokens: int = 2000,
                                                top_p=None, top_k=None) -> dict:
        system = """You are a Section 508 compliance expert. Based on the individual file analyses,
generate a comprehensive solicitation-level summary.

Return ONLY valid JSON:
{
  "solicitation_applicable": true/false,
  "solicitation_compliant": true/false,
  "conflicts_detected": true/false,
  "conflict_resolution_summary": "",
  "procurement_type": "",
  "procurement_complexity": "Simple/Medium/Complex",
  "primary_ict_types": [],
  "has_cots_products": true/false,
  "explicit_508_coverage": true/false,
  "solicitation_explanation": "detailed explanation",
  "key_findings": [],
  "priority_recommendations": [],
  "vendor_responsibilities": [],
  "file_consistency_assessment": "",
  "overall_risk_level": "High/Medium/Low",
  "recommended_actions": []
}"""
        summaries = []
        if individual_file_analyses:
            for a in individual_file_analyses[:10]:
                summaries.append(f"File: {a.get('file_name','')} | Applicable: {a.get('is_508_applicable')} | Compliant: {a.get('is_compliant')} | Matches: {a.get('matches_found',0)}")
        user = f"Solicitation {solicitation_id}:\n" + "\n".join(summaries)
        return self._json_chat(system, user, temperature=temperature,
                                max_tokens=max_tokens, stage_name="solicitation_summary") or {}

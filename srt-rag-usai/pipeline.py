#!/usr/bin/env python3
"""
Single-file analysis pipeline — runs all 6 stages and returns the full 77+ field dict.

Stages:
  0. Text Extraction
  1. Pre-Processing & Context Detection
  2. 508 Applicability Assessment (LLM)
  3. ICT Type Classification (LLM)
  4. Vector Similarity Matching (FAISS + LLM per-match verdicts)
  5. Final Synthesis & Determination (LLM)
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from text_extractor import extract_text_from_file
from preprocessor import (
    detect_website_source, check_cots, check_alternative_regs,
    filter_false_positives, is_likely_navy_parts, compute_context_scores,
)
from vector_matching import build_faiss_index, run_vector_matching
from field_enrichment import enrich_match, compute_file_quality_metrics, compute_compliance_score
from usai_adapter import USAIAdapter

logger = logging.getLogger(__name__)

DEFAULT_STANDARDS = str(Path(__file__).parent / "data" / "508_standards.txt")


def analyze_file(
    file_path: str,
    client: Optional[USAIAdapter] = None,
    standards_path: str = DEFAULT_STANDARDS,
    embed_model: str = "cohere_english_v3",
    on_stage: Optional[Callable[[Dict], None]] = None,
) -> Dict[str, Any]:
    """
    Run the full 7-stage pipeline on a single file.

    Returns dict with keys:
      - stages: list of per-stage dicts (for debugging / logging)
      - report: compiled 77+ field dict ready for DB insert
      - llm_calls: stage log from adapter
    """
    if client is None:
        client = USAIAdapter()

    client.clear_stage_logs()
    stages = []
    t0 = time.time()
    file_name = Path(file_path).name
    logger.info(f"  📋 Pipeline start: {file_name}")

    def _logs_since(n):
        return client.get_stage_logs()[n:]

    def _emit(d):
        stages.append(d)
        if on_stage:
            on_stage(d)

    # ── Stage 0: Text Extraction ──────────────────────────────────────
    logger.info(f"  ▶ Stage 0: Text Extraction — {file_name}")
    t = time.time()
    try:
        text, file_meta = extract_text_from_file(file_path)
        _emit({"stage": 0, "name": "Text Extraction",
               "status": "success" if len(text) > 10 else "warning",
               "duration_ms": round((time.time() - t) * 1000),
               "output": {**file_meta, "preview": text[:500]}})
    except Exception as e:
        _emit({"stage": 0, "name": "Text Extraction", "status": "error",
               "duration_ms": round((time.time() - t) * 1000),
               "output": {"error": str(e)}})
        return {"stages": stages, "report": {}, "llm_calls": []}

    if len(text) < 10:
        return {"stages": stages, "report": {}, "llm_calls": []}

    # ── Stage 1: Pre-Processing ───────────────────────────────────────
    logger.info(f"  ▶ Stage 1: Pre-Processing — {file_name}")
    t = time.time()
    website_source = detect_website_source(file_path, text)
    is_cots = check_cots(text)
    alt_regs = check_alternative_regs(text)
    filtered_text, false_positives = filter_false_positives(text)
    navy_parts = is_likely_navy_parts(text, website_source)
    ctx_scores = compute_context_scores(text, website_source, is_cots)
    sample = filtered_text[:50000]

    _emit({"stage": 1, "name": "Pre-Processing & Context Detection",
           "status": "success", "duration_ms": round((time.time() - t) * 1000),
           "output": {"website_source": website_source, "is_cots": is_cots,
                      "alt_regs": alt_regs, "false_positives": false_positives,
                      "navy_parts": navy_parts, "context_scores": ctx_scores,
                      "sample_length": len(sample)}})

    # ── Stage 2: BM25 + ML Model Compliance (David's) ──────────────
    logger.info(f"  ▶ Stage 2: BM25 + ML Model — {file_name}")
    t = time.time()
    try:
        from bm25_predictor import run_bm25, predict_with_model
        from pathlib import Path as _Path
        bm25_result = run_bm25(sample)
        model_path = str(_Path(__file__).parent / "data" / "508_compliance_model.joblib")
        ml_prediction = predict_with_model(sample, bm25_result, model_path)
        bm25_stage = {
            "bm25": bm25_result,
            "ml_prediction": ml_prediction,
        }
    except Exception as e:
        logger.warning(f"BM25/ML model failed: {e}")
        bm25_stage = {"error": str(e), "bm25": {}, "ml_prediction": {"prediction": "undetermined", "source": "error"}}
        ml_prediction = {"prediction": "undetermined", "probability": 0, "source": "error"}
    _emit({"stage": 2, "name": "BM25 + ML Compliance",
           "status": "error" if "error" in bm25_stage else "success",
           "duration_ms": round((time.time() - t) * 1000),
           "output": bm25_stage})

    # ── Stage 3: 508 Applicability (LLM) ─────────────────────────────
    logger.info(f"  ▶ Stage 3: Applicability LLM call — {file_name}")
    t = time.time()
    lb = len(client.get_stage_logs())
    try:
        applicability = client.assess_508_applicability(sample)
    except Exception as e:
        applicability = client._default_applicability_response()
        applicability["error"] = str(e)
    _emit({"stage": 3, "name": "508 Applicability", "llm_call": True,
           "status": "error" if "error" in applicability else "success",
           "duration_ms": round((time.time() - t) * 1000),
           "output": applicability, "prompts": _logs_since(lb)})

    # ── Stage 4: ICT Classification (LLM) ────────────────────────────
    logger.info(f"  ▶ Stage 4: ICT Classification LLM call — {file_name}")
    t = time.time()
    lb = len(client.get_stage_logs())
    try:
        ict = client.analyze_ict_types(sample)
    except Exception as e:
        ict = client._default_ict_response()
        ict["error"] = str(e)
    _emit({"stage": 4, "name": "ICT Classification", "llm_call": True,
           "status": "error" if "error" in ict else "success",
           "duration_ms": round((time.time() - t) * 1000),
           "output": ict, "prompts": _logs_since(lb)})

    # ── Stage 4: Vector Matching (FAISS + LLM) ───────────────────────
    logger.info(f"  ▶ Stage 4: Vector Matching — {file_name}")
    t = time.time()
    lb = len(client.get_stage_logs())
    standards_text = ""
    try:
        faiss_db, chunks, standards_text = build_faiss_index(standards_path, embed_model)
        vm = run_vector_matching(text, faiss_db, chunks, client)
    except Exception as e:
        vm = {"matches_found": 0, "matches": [], "match_strength": "Low",
              "explicit_mentions": 0, "processing_stats": {"error": str(e)},
              "llm_analysis": f"Error: {e}"}
    _emit({"stage": 4, "name": "Vector Matching", "llm_call": True,
           "status": "success" if vm["matches_found"] > 0 else "warning",
           "duration_ms": round((time.time() - t) * 1000),
           "output": {"matches_found": vm["matches_found"],
                      "match_strength": vm["match_strength"],
                      "meaningful_matches": vm["explicit_mentions"],
                      "stats": vm.get("processing_stats", {}),
                      "llm_analysis": vm.get("llm_analysis", "")},
           "prompts": _logs_since(lb)})

    # ── Stage 5: Final Synthesis (LLM) ──────────────────────────────
    logger.info(f"  ▶ Stage 5: Document Summary LLM call — {file_name}")
    # (Old Stage 5 — 508 Inclusion Check — removed. Stage 4's LLM now
    #  provides per-match meaningful verdicts, making a separate inclusion
    #  check redundant and eliminating the hallucination source.)

    # Parse Stage 4 LLM verdict for overall includes_508
    vm_includes_508 = False
    try:
        import json as _json
        llm_raw = vm.get("llm_analysis", "")
        if isinstance(llm_raw, str) and llm_raw.startswith("{"):
            vm_verdict = _json.loads(llm_raw)
            vm_includes_508 = vm_verdict.get("overall_includes_508", False)
    except Exception:
        pass

    t = time.time()
    lb = len(client.get_stage_logs())
    synthesis_input = {
        "applicability": {
            "is_508_applicable": applicability.get("is_508_applicable"),
            "confidence_score": applicability.get("confidence_score"),
            "explanation": applicability.get("applicability_explanation"),
            "has_explicit_508_mention": applicability.get("has_explicit_508_mention"),
        },
        "ict": {"ict_types": ict.get("ict_types"), "explanation": ict.get("explanation")},
        "vector_matching": {
            "matches_found": vm["matches_found"],
            "match_strength": vm["match_strength"],
            "overall_includes_508": vm_includes_508,
            "top": [{"chunk": m.get("chunk_text", "")[:200],
                     "standard": m.get("matched_standard", "")[:200],
                     "score": m.get("similarity_score"),
                     "llm_meaningful": m.get("llm_meaningful", False),
                     "llm_reason": m.get("llm_reason", "")}
                    for m in vm.get("matches", [])[:5]],
        },
    }

    synthesis_system = """You are summarizing a single solicitation document.

Your job is to provide a factual summary of what this document is about and what ICT (Information and Communication Technology) is being procured.

Describe:
1. What the solicitation/document is for (the purpose, scope, what's being bought)
2. What types of ICT are involved (software, hardware, services, etc.)
3. Whether Section 508 accessibility standards are mentioned or referenced
4. Any notable regulatory references found in the document

Do NOT make compliance determinations. Do NOT recommend actions. Just describe what's in the document factually.

Return ONLY valid JSON:
{
  "document_summary": "2-3 sentence summary of what this document is about",
  "procurement_description": "what ICT is being procured",
  "section_508_references": ["list of specific 508/accessibility references found, if any"],
  "regulatory_references": ["other notable regulatory references"],
  "key_findings": ["factual finding 1", ...],
  "document_type": "RFQ/RFP/SOW/Amendment/Other"
}"""

    try:
        synthesis = client._json_chat(
            synthesis_system,
            f"Summarize this document based on the analysis:\n\n{json.dumps(synthesis_input, indent=2, default=str)}",
            temperature=0.0, stage_name="document_summary")
        if not synthesis:
            synthesis = {
                "document_summary": "Summary generation failed",
                "procurement_description": "",
                "section_508_references": [],
                "regulatory_references": [],
                "key_findings": [],
                "document_type": "Unknown",
            }
    except Exception as e:
        synthesis = {
            "document_summary": f"Summary error: {e}",
            "procurement_description": "",
            "section_508_references": [],
            "regulatory_references": [],
            "key_findings": [],
            "document_type": "Unknown",
        }

    _emit({"stage": 5, "name": "Document Summary", "llm_call": True,
           "status": "success" if "error" not in str(synthesis) else "warning",
           "duration_ms": round((time.time() - t) * 1000),
           "output": synthesis, "prompts": _logs_since(lb)})

    # ── Compile report ──────────────────────────────────────────────────
    is_applicable = applicability.get("is_508_applicable", False)

    ict_types = ict.get("ict_types", {})
    active_ict = [k for k, v in ict_types.items() if v]

    # Enrich matches
    enriched_matches = [enrich_match(dict(m), text[:2000]) for m in vm.get("matches", [])]
    quality_metrics = compute_file_quality_metrics(enriched_matches)
    compliance_score = compute_compliance_score(enriched_matches, is_applicable)

    total_ms = round((time.time() - t0) * 1000)

    report = {
        # ── File metadata ─────────────────────────────────────────────
        "file_name": file_meta.get("file_name", ""),
        "file_type": file_meta.get("file_type", ""),
        "file_size_mb": file_meta.get("file_size_mb", 0),
        "word_count": file_meta.get("word_count", 0),
        "char_count": file_meta.get("char_count", 0),
        "page_count": file_meta.get("page_count", 0),
        "modification_date": file_meta.get("modification_date", ""),

        # ── Pre-processing ────────────────────────────────────────────
        "website_source": website_source,
        "is_cots_product": is_cots,
        "alternative_regs_found": alt_regs,
        "false_positives_filtered": false_positives,
        "is_navy_parts": navy_parts,
        "document_section_weight": ctx_scores.get("document_section_weight", 0),
        "ict_relevance_score": ctx_scores.get("ict_relevance_score", 0),
        "navy_parts_indicator_score": ctx_scores.get("navy_parts_indicator_score", 0),
        "cots_context_adjustment": ctx_scores.get("cots_context_adjustment", 0),

        # ── Applicability (Stage 2 — LLM informational) ──────────────
        "is_508_applicable": is_applicable,
        "confidence_score": applicability.get("confidence_score", 0),
        "applicability_explanation": applicability.get("applicability_explanation", ""),
        "key_eit_indicators": applicability.get("key_eit_indicators", []),
        "is_physical_only": applicability.get("is_physical_only", False),
        "has_explicit_508_mention": applicability.get("has_explicit_508_mention", False),

        # ── ICT Classification (Stage 3) ──────────────────────────────
        "ict_types": ict_types,
        "applicable_ict_types": active_ict,
        "ict_explanation": ict.get("explanation", ""),
        "hardware_component": ict.get("hardware_component", "No"),
        "software_component": ict.get("software_component", "No"),

        # ── Vector Matching (Stage 4) ─────────────────────────────────
        "matches_found": vm["matches_found"],
        "match_strength": vm["match_strength"],
        "meaningful_matches": vm["explicit_mentions"],
        "top_matches": enriched_matches[:10],
        "vector_llm_analysis": vm.get("llm_analysis", ""),
        "vector_processing_stats": vm.get("processing_stats", {}),

        # ── Quality metrics (from enrichment) ─────────────────────────
        "average_match_quality": quality_metrics["average_match_quality"],
        "high_quality_matches_count": quality_metrics["high_quality_matches_count"],
        "meaningful_matches_ratio": quality_metrics["meaningful_matches_ratio"],
        "false_positive_matches_filtered": quality_metrics["false_positive_matches_filtered"],
        "explicit_mentions_count": quality_metrics["explicit_mentions_count"],
        "compliance_language_count": quality_metrics["compliance_language_count"],

        # ── Match quality score ───────────────────────────────────────
        "compliance_overall_score": compliance_score["overall_score"],
        "compliance_confidence": compliance_score["confidence"],
        "compliance_assessment": compliance_score["assessment"],

        # ── 508 references found (informational, not a decision) ──────
        "section_508_references": synthesis.get("section_508_references", []),
        "regulatory_references": synthesis.get("regulatory_references", []),
        "is_discussing_508": vm_includes_508,

        # ── Document Summary (Stage 5 — LLM informational) ───────────
        "document_summary": synthesis.get("document_summary", ""),
        "procurement_description": synthesis.get("procurement_description", ""),
        "document_type": synthesis.get("document_type", "Unknown"),
        "key_findings": synthesis.get("key_findings", []),

        # ── Pipeline meta ─────────────────────────────────────────────
        "total_pipeline_duration_ms": total_ms,
        "llm_calls_made": client._call_count,
        "total_tokens_used": client._total_tokens,

        # ── BM25 + ML Model (v4) ─────────────────────────────────────
        "bm25_raw_score": bm25_stage.get("bm25", {}).get("bm25_raw_score", 0),
        "bm25_normalized_score": bm25_stage.get("bm25", {}).get("bm25_normalized_score", 0),
        "bm25_bucket": bm25_stage.get("bm25", {}).get("bucket", ""),
        "bm25_keyword_hits": bm25_stage.get("bm25", {}).get("keyword_hits", {}),
        "bm25_prediction": ml_prediction.get("prediction", "undetermined"),
        "bm25_probability": ml_prediction.get("probability", 0),
        "bm25_source": ml_prediction.get("source", ""),
    }

    return {"stages": stages, "report": report, "llm_calls": client.get_stage_logs()}

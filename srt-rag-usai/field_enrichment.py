#!/usr/bin/env python3
"""
Field Enrichment — Compute all 77+ fields from raw pipeline output.

Takes the raw stage outputs and produces the full analysis dict
with every field the database and CSV export expect.
"""

import re
import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def enrich_match(match: Dict, text_context: str = "") -> Dict:
    """Enrich a single vector match with all per-match fields."""
    chunk_text = match.get("chunk_text", "")
    matched_std = match.get("matched_standard", "")
    sim = match.get("similarity_score", 0.0)

    # Accessibility term detection
    acc_terms = ["section 508", "508", "accessibility", "accessible", "wcag",
                 "assistive technology", "screen reader", "vpat", "acr",
                 "rehabilitation act", "disability", "disabilities"]
    found_terms = [t for t in acc_terms if t in chunk_text.lower()]
    has_explicit = len(found_terms) > 0
    compliance_lang = any(t in chunk_text.lower() for t in
                          ["shall comply", "must comply", "conformance", "compliance requirement"])

    # Match quality score (0-1)
    quality = sim * 0.5
    if has_explicit:
        quality += 0.3
    if compliance_lang:
        quality += 0.2
    quality = min(quality, 1.0)

    # Standard classification
    std_lower = matched_std.lower()
    category = "General"
    section = ""
    wcag_level = ""
    if "chapter 4" in std_lower or "hardware" in std_lower:
        category = "Hardware"
    elif "chapter 5" in std_lower or "software" in std_lower:
        category = "Software"
    elif "chapter 3" in std_lower or "functional performance" in std_lower:
        category = "Functional Performance Criteria"
    elif "chapter 6" in std_lower or "support documentation" in std_lower:
        category = "Support Documentation"
    elif "wcag" in std_lower:
        category = "WCAG"

    sec_match = re.search(r'[ECD]?\d{3}(?:\.\d+)*', matched_std)
    if sec_match:
        section = sec_match.group(0)
    if "level a" in std_lower:
        wcag_level = "AA" if "level aa" in std_lower else "A"

    # False positive detection
    fp_pattern = ""
    kaspersky = "kaspersky" in chunk_text.lower()
    admin_lang = any(t in chunk_text.lower() for t in ["hereby", "whereas", "notwithstanding"])
    boilerplate = any(t in chunk_text.lower() for t in ["far 52.", "dfars 252.", "clause"])

    # Relevance category
    if quality >= 0.7:
        relevance_cat = "High"
    elif quality >= 0.4:
        relevance_cat = "Medium"
    else:
        relevance_cat = "Low"

    # Compliance relationship
    if has_explicit and compliance_lang:
        relationship = "Direct_Requirement"
    elif has_explicit:
        relationship = "Reference"
    elif sim >= 0.5:
        relationship = "Semantic_Match"
    else:
        relationship = "Weak_Association"

    match.update({
        "match_quality_score": round(quality, 4),
        "chunk_relevance_category": relevance_cat,
        "chunk_relevance_confidence": round(quality, 4),
        "is_meaningful_match": match.get("llm_meaningful", quality >= 0.4),
        "llm_validation_reasoning": match.get("llm_reason", match.get("llm_validation_reasoning", "")),
        "false_positive_likelihood": round(1.0 - quality, 4),
        "base_similarity_score": sim,
        "enhanced_similarity_score": round(sim + (0.1 if has_explicit else 0), 4),
        "similarity_boost_factor": 0.1 if has_explicit else 0.0,
        "explicit_accessibility_mention": has_explicit,
        "accessibility_terms_found": ", ".join(found_terms),
        "compliance_language_detected": compliance_lang,
        "matched_standard_category": category,
        "specific_508_section": section,
        "wcag_level_mentioned": wcag_level,
        "compliance_relationship_type": relationship,
        "explanation_quality_score": round(quality, 4),
        "explanation_category": category,
        "compliance_implication": relationship,
        "vendor_responsibility_level": "High" if has_explicit else "Standard",
        "false_positive_pattern_matched": fp_pattern,
        "kaspersky_clause_detected": kaspersky,
        "admin_language_detected": admin_lang,
        "contract_boilerplate_detected": boilerplate,
    })
    return match


def compute_file_quality_metrics(matches: List[Dict]) -> Dict:
    """Compute file-level aggregated quality metrics from enriched matches."""
    if not matches:
        return {
            "average_match_quality": 0.0,
            "high_quality_matches_count": 0,
            "meaningful_matches_ratio": 0.0,
            "false_positive_matches_filtered": 0,
            "explicit_mentions_count": 0,
            "compliance_language_count": 0,
            "average_ict_relevance": 0.0,
        }

    qualities = [m.get("match_quality_score", 0) for m in matches]
    meaningful = [m for m in matches if m.get("is_meaningful_match")]
    explicit = [m for m in matches if m.get("explicit_accessibility_mention")]
    compliance_lang = [m for m in matches if m.get("compliance_language_detected")]
    fps = [m for m in matches if m.get("false_positive_likelihood", 0) > 0.7]

    return {
        "average_match_quality": round(sum(qualities) / len(qualities), 4) if qualities else 0.0,
        "high_quality_matches_count": sum(1 for q in qualities if q >= 0.6),
        "meaningful_matches_ratio": round(len(meaningful) / len(matches), 4) if matches else 0.0,
        "false_positive_matches_filtered": len(fps),
        "explicit_mentions_count": len(explicit),
        "compliance_language_count": len(compliance_lang),
        "average_ict_relevance": 0.0,  # Set by context scoring
    }


def compute_compliance_score(matches: List[Dict], is_applicable: bool) -> Dict:
    """Compute overall compliance score from matches."""
    if not is_applicable or not matches:
        return {
            "overall_score": 0.0,
            "confidence": "low",
            "assessment": "not_applicable" if not is_applicable else "no_matches",
        }

    qualities = [m.get("match_quality_score", 0) for m in matches]
    avg = sum(qualities) / len(qualities) if qualities else 0
    high_count = sum(1 for q in qualities if q >= 0.6)

    if high_count >= 3 and avg >= 0.5:
        return {"overall_score": round(avg, 4), "confidence": "high", "assessment": "strong_inclusion"}
    elif high_count >= 1 and avg >= 0.3:
        return {"overall_score": round(avg, 4), "confidence": "medium", "assessment": "partial_inclusion"}
    else:
        return {"overall_score": round(avg, 4), "confidence": "low", "assessment": "weak_or_missing"}

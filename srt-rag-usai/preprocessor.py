#!/usr/bin/env python3
"""Pre-processing: website source detection, COTS, false positive filtering, context scoring."""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def detect_website_source(file_path: str, text: str) -> str:
    """Detect the procurement website source."""
    combined = (file_path + " " + text[:3000]).lower()
    if "dibbs" in combined or "dla.mil" in combined:
        return "DIBBS"
    if "neco" in combined or "navy" in combined:
        return "NECO"
    if "sam.gov" in combined or "acquisition.gov" in combined:
        return "SAM"
    if "piee" in combined:
        return "PIEE"
    if "fedconnect" in combined:
        return "FedConnect"
    if "ebuy" in combined:
        return "eBuy"
    return "Unknown"


def check_cots(text: str) -> bool:
    """Check if the solicitation involves COTS products."""
    patterns = [
        r"commercial.off.the.shelf", r"\bCOTS\b", r"commercial\s+item",
        r"commercial\s+product", r"FAR\s+12\.", r"FAR\s+Part\s+12",
        r"commercial\s+services",
    ]
    t = text[:20000].lower()
    return any(re.search(p, t, re.IGNORECASE) for p in patterns)


def check_alternative_regs(text: str) -> List[str]:
    """Check for alternative accessibility regulations."""
    patterns = [
        r"852\.239[\-\u2013]75", r"VAAR\s*852", r"BSA\s+commercial",
        r"FAR\s+39\.2", r"Section\s+255",
    ]
    found = []
    for p in patterns:
        if re.search(p, text[:30000], re.IGNORECASE):
            found.append(p)
    return found


def filter_false_positives(text: str) -> Tuple[str, List[str]]:
    """Filter known false positive triggers. Returns (filtered_text, list_of_filtered)."""
    filtered = []
    fp_patterns = {
        "FedRAMP": r"FedRAMP",
        "Kaspersky": r"Kaspersky",
        "DFARS_252": r"DFARS\s+252\.204",
    }
    result = text
    for name, pattern in fp_patterns.items():
        if re.search(pattern, result, re.IGNORECASE):
            filtered.append(name)
    return result, filtered


def is_likely_navy_parts(text: str, website_source: str) -> bool:
    """Detect if this is a Navy parts procurement (likely not ICT)."""
    if website_source in ("DIBBS", "NECO"):
        navy_indicators = [
            r"\bNSN\b", r"national\s+stock\s+number", r"\bP/N\b",
            r"part\s+number", r"mil-spec", r"mil-std",
        ]
        t = text[:10000].lower()
        hits = sum(1 for p in navy_indicators if re.search(p, t, re.IGNORECASE))
        return hits >= 2
    return False


def compute_context_scores(text: str, website_source: str, is_cots: bool) -> Dict:
    """Compute context-aware scoring fields."""
    t = text[:20000].lower()

    # ICT relevance
    ict_terms = ["software", "hardware", "website", "application", "system",
                 "database", "network", "cloud", "saas", "platform", "digital"]
    ict_hits = sum(1 for term in ict_terms if term in t)
    ict_relevance = min(ict_hits / len(ict_terms), 1.0)

    # Navy parts indicator
    navy_score = 0.0
    if is_likely_navy_parts(text, website_source):
        navy_score = 0.8

    # Document section weight (how much of the doc is substantive vs boilerplate)
    total_len = len(text)
    boilerplate_patterns = [r"FAR\s+52\.\d+", r"DFARS", r"clause", r"provision"]
    boilerplate_hits = sum(len(re.findall(p, text, re.IGNORECASE)) for p in boilerplate_patterns)
    section_weight = max(0.2, 1.0 - (boilerplate_hits * 50 / max(total_len, 1)))

    # COTS adjustment
    cots_adj = 0.1 if is_cots else 0.0

    return {
        "document_section_weight": round(section_weight, 4),
        "ict_relevance_score": round(ict_relevance, 4),
        "navy_parts_indicator_score": round(navy_score, 4),
        "cots_context_adjustment": round(cots_adj, 4),
    }

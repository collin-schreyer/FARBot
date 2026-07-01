#!/usr/bin/env python3
"""
Agency scoping — layer agency acquisition-regulation deviations onto the review.

The 2026-07-01 direction: "if I'm from HHS asking a FAR question, the tool should
answer as FAR *and* the HHSAR deviation, and show the difference." This module is
the data + matching for that layer. It loads the ACR Agency Expansion workbook
(data/agency/SRT_ACR_Repo_Agency_Expansion.xlsx) — each row is one agency
acquisition-regulation supplement clause bearing on Section 508 / ICT
accessibility (HHSAR, VAAR, AIDAR, DOLAR, TAR, DLAD, DTAR, DARS, AFARS, CAR, EPA).

Given a solicitation's acquiring agency (passed in, or detected from the text),
deviations_for() returns that agency's supplement clauses so the review can add
"FAR is the baseline; <agency> additionally requires <section>: <requirement>."

This is Track A of the Topic Pack plan: an agency dimension on the 508 topic, not
a new engine.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_XLSX = Path(__file__).resolve().parent / "data" / "agency" / "SRT_ACR_Repo_Agency_Expansion.xlsx"

# Canonical agency key (as it appears in column A) -> match aliases. Supplement
# acronyms (hhsar/vaar/…) are the strongest signal; bare abbreviations are matched
# on word boundaries so "va" doesn't fire inside "evaluation".
_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "HHS (HHSAR)":                 {"strong": ["hhsar"], "name": ["health and human services", "department of health"], "abbr": ["hhs"]},
    "Transportation (TAR)":        {"strong": ["tar "], "name": ["department of transportation", "transportation"], "abbr": ["dot"]},
    "Veterans Affairs (VAAR)":     {"strong": ["vaar"], "name": ["veterans affairs", "veterans administration"], "abbr": ["va"]},
    "USAID (AIDAR)":               {"strong": ["aidar"], "name": ["agency for international development", "usaid"], "abbr": []},
    "Department of Labor (DOLAR)": {"strong": ["dolar"], "name": ["department of labor"], "abbr": ["dol"]},
    "Defense Logistics Aquisition Directive (DLAD)": {"strong": ["dlad"], "name": ["defense logistics"], "abbr": ["dla"]},
    "Department of Treasury (DTAR)": {"strong": ["dtar"], "name": ["department of treasury", "treasury"], "abbr": []},
    "EPA":                         {"strong": [], "name": ["environmental protection agency"], "abbr": ["epa"]},
    "Defense (DARS)":              {"strong": ["dars", "dfars"], "name": ["department of defense"], "abbr": ["dod"]},
    "Army (AFARS)":                {"strong": ["afars"], "name": ["department of the army", "u.s. army", "us army"], "abbr": ["army"]},
    "Commerce (CAR)":              {"strong": [], "name": ["department of commerce", "commerce"], "abbr": []},
}

_FIELDS = ["part", "section", "language", "requirement",
           "vpat_acr_mention", "vpat_acr_required", "remediation_required",
           "deliverables_508_required"]

_cache: Optional[Dict[str, List[Dict[str, str]]]] = None


def _load() -> Dict[str, List[Dict[str, str]]]:
    global _cache
    if _cache is not None:
        return _cache
    out: Dict[str, List[Dict[str, str]]] = {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(_XLSX, data_only=True)
        ws = wb["Agency Regs"]
        rows = list(ws.iter_rows(values_only=True))
        last = None
        for r in rows[2:]:  # row 1 blank, row 2 header
            if not any(v for v in r):
                continue
            agency = (str(r[0]).strip() if r[0] else "")
            if agency:
                last = agency
            if not last or not (r[2] or r[3]):  # need at least a section or language
                continue
            rec = {
                "part": _s(r[1]), "section": _s(r[2]), "language": _s(r[3]),
                "requirement": _s(r[4]), "vpat_acr_mention": _yn(r[5]),
                "vpat_acr_required": _yn(r[6]), "remediation_required": _yn(r[7]),
                "deliverables_508_required": _yn(r[8]),
            }
            out.setdefault(last, []).append(rec)
        logger.info(f"[agency_packs] loaded {sum(len(v) for v in out.values())} clauses / {len(out)} agencies")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[agency_packs] could not load {_XLSX}: {e}")
    _cache = out
    return out


def _s(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def _yn(v) -> str:
    s = str(v).strip().lower() if v is not None else ""
    return "y" if s.startswith("y") else ("n" if s.startswith("n") else "")


def agencies() -> List[str]:
    return sorted(_load().keys())


def match_agency(name_or_text: str) -> Optional[str]:
    """Best canonical agency for a name or a body of solicitation text."""
    if not name_or_text:
        return None
    low = name_or_text.lower()
    best, best_score = None, 0
    for key, al in _ALIASES.items():
        score = 0
        for s in al["strong"]:
            if s in low:
                score += 5
        for n in al["name"]:
            if n in low:
                score += 3
        for a in al["abbr"]:
            if re.search(rf"\b{re.escape(a)}\b", low):
                score += 1
        if score > best_score:
            best, best_score = key, score
    return best if best_score > 0 else None


def deviations_for(agency_key: Optional[str]) -> List[Dict[str, str]]:
    if not agency_key:
        return []
    data = _load()
    if agency_key in data:
        return data[agency_key]
    # allow passing a raw name/abbr
    canon = match_agency(agency_key)
    return data.get(canon, []) if canon else []


def _relevance_508(d: Dict[str, str]) -> int:
    """Rank a deviation clause by how directly it bears on 508/accessibility."""
    score = 0
    if d["vpat_acr_required"] == "y": score += 3
    if d["deliverables_508_required"] == "y": score += 2
    if d["remediation_required"] == "y": score += 2
    if d["vpat_acr_mention"] == "y": score += 1
    blob = f"{d['section']} {d['language']}".lower()
    if any(t in blob for t in ("508", "accessib", "vpat", "acr", "electronic and information",
                               "information and communication", " eit", "(eit")):
        score += 2
    return score


def agency_suggestions(agency_key: str, devs: List[Dict[str, str]]) -> List[str]:
    """Prescriptive lines for the agency deviation layer (offline template)."""
    if not devs:
        return []
    ranked = sorted(devs, key=_relevance_508, reverse=True)
    out = [f"This is a {agency_key} acquisition — FAR is the baseline, but the agency "
           f"supplement adds requirements the FAR-level review won't surface on its own:"]
    for d in ranked[:6]:
        bits = []
        if d["vpat_acr_required"] == "y":
            bits.append("requires a VPAT/ACR")
        if d["remediation_required"] == "y":
            bits.append("requires remediation")
        if d["deliverables_508_required"] == "y":
            bits.append("deliverables must be 508-conformant")
        extra = f" — {', '.join(bits)}" if bits else ""
        sec = d["section"] or d["part"]
        out.append(f"Confirm {sec}{extra}. ({d['requirement'] or d['language'][:80]})")
    return out

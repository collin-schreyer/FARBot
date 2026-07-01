#!/usr/bin/env python3
"""
Solicitation review — the blended FAR_BOT + SRT flow.

This is the first end-to-end proof of the two systems working as one, and the
skeleton of the "prescriptive" tool from the 2026-07-01 direction: the AI infers
what *should* be reviewed from the uploaded documents instead of waiting for the
user to know what to ask.

Flow (given one or more uploaded solicitation files):

  1. Extract   — pull text from each file (reuses SRT's text_extractor).
  2. Infer     — decide which regulatory *issue areas* apply to this package
                 (508, cybersecurity, agency deviations, small business, privacy,
                 labor). LLM when Bedrock creds are present; keyword scoring offline.
  3. Retrieve  — for each applicable area, pull relevant FAR sections via
                 FARRetriever (FAR_BOT's Bedrock+graph retrieval — the seam).
  4. Suggest   — turn each area + its FAR hits into "questions you should be
                 asking / things to check" (the prescriptive output).
  5. Check     — (optional, --determination) run SRT's v4.1 pipeline for the
                 508 compliance determination on each file.

Offline by default so the wiring is provable without creds; pass --live to run
entirely on Bedrock (retrieval + inference + suggestions + determination).

Usage:
  python solicitation_review.py doc1.pdf doc2.docx
  python solicitation_review.py sol.pdf --live --determination --json out.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import agency_packs
from far_retrieval import FARRetriever
from text_extractor import extract_text_from_file

logger = logging.getLogger(__name__)


# ── Issue-area registry ────────────────────────────────────────────────────
# Each area is the seed of a future "Topic Pack": a label, the keywords that flag
# it offline, and the FAR query used to retrieve the governing sections. Adding a
# new area (cyber deviations, labor standards, …) is a data edit, not new code —
# the Topic Pack principle from SRT_EXPANSION_ARCHITECTURE_RECOMMENDATION.md.
ISSUE_AREAS: List[Dict[str, Any]] = [
    {
        "id": "section_508",
        "label": "Section 508 / ICT Accessibility",
        "keywords": ["508", "accessibility", "vpat", "wcag", "acr", "accessible",
                     "screen reader", "rehabilitation act", "ict"],
        "far_query": "Section 508 accessibility standards for information and communication technology",
    },
    {
        "id": "cybersecurity",
        "label": "Cybersecurity / Information Protection",
        "keywords": ["cybersecurity", "cyber", "nist 800-171", "cmmc", "cui",
                     "controlled unclassified", "fedramp", "security control",
                     "supply chain", "52.204-21", "information system"],
        "far_query": "cybersecurity safeguarding covered contractor information systems controlled unclassified information",
    },
    {
        "id": "agency_deviation",
        "label": "Agency Acquisition-Regulation Deviations",
        "keywords": ["hhsar", "vaar", "dfars", "gsam", "agency supplement",
                     "deviation", "class deviation"],
        "far_query": "agency FAR supplement deviations acquisition regulation clauses",
    },
    {
        "id": "small_business",
        "label": "Small Business / Set-Asides",
        "keywords": ["small business", "set-aside", "set aside", "8(a)", "hubzone",
                     "sdvosb", "wosb", "socioeconomic", "subcontracting plan"],
        "far_query": "small business set-aside programs socioeconomic subcontracting",
    },
    {
        "id": "privacy",
        "label": "Privacy / PII Handling",
        "keywords": ["privacy act", "pii", "personally identifiable", "system of records",
                     "privacy impact", "safeguarding personal"],
        "far_query": "Privacy Act handling of personally identifiable information system of records",
    },
    {
        "id": "labor_standards",
        "label": "Labor Standards",
        "keywords": ["service contract act", "sca", "wage determination",
                     "davis-bacon", "prevailing wage", "fair labor"],
        "far_query": "Service Contract Labor Standards wage determination prevailing wage",
    },
]


# ── Step 1: extract ────────────────────────────────────────────────────────
def extract_documents(files: List[str]) -> List[Dict[str, Any]]:
    docs = []
    for f in files:
        try:
            text, meta = extract_text_from_file(f)
        except Exception as e:
            text, meta = "", {"error": str(e)}
        docs.append({"file": f, "name": Path(f).name, "text": text,
                     "chars": len(text), "meta": meta})
    return docs


# ── Step 2: infer applicable issue areas ───────────────────────────────────
def infer_issue_areas(text: str, client=None) -> List[Dict[str, Any]]:
    if client is not None:
        try:
            return _infer_issue_areas_llm(text, client)
        except Exception as e:
            logger.warning(f"[infer] LLM inference failed, falling back to keywords: {e}")
    return _infer_issue_areas_keywords(text)


def _infer_issue_areas_keywords(text: str) -> List[Dict[str, Any]]:
    low = text.lower()
    out = []
    for area in ISSUE_AREAS:
        hits = sorted({kw for kw in area["keywords"] if kw in low})
        if hits:
            # crude confidence: more distinct keyword families -> higher
            conf = "high" if len(hits) >= 3 else "medium" if len(hits) == 2 else "low"
            out.append({"id": area["id"], "label": area["label"],
                        "applicable": True, "confidence": conf,
                        "evidence": hits, "method": "keyword"})
    return out


def _infer_issue_areas_llm(text: str, client) -> List[Dict[str, Any]]:
    catalog = "\n".join(f'- {a["id"]}: {a["label"]}' for a in ISSUE_AREAS)
    system = (
        "You are a federal acquisition analyst. Given solicitation text, decide which "
        "regulatory issue areas a contracting officer should review. Only mark an area "
        "applicable if the solicitation's subject matter actually implicates it — not "
        "because a term is mentioned in passing.\n\n"
        f"Issue areas:\n{catalog}\n\n"
        'Return ONLY valid JSON: {"areas":[{"id":"<id>","applicable":true|false,'
        '"confidence":"high|medium|low","reasoning":"one sentence"}]}'
    )
    result = client._json_chat(system, f"Solicitation text:\n\n{text[:50000]}",
                               model=getattr(client, "cheap_model", None),
                               temperature=0.0, max_tokens=1200, retries=2,
                               stage_name="issue_area_inference")
    by_id = {a["id"]: a for a in ISSUE_AREAS}
    out = []
    for a in (result or {}).get("areas", []):
        if a.get("applicable") and a.get("id") in by_id:
            out.append({"id": a["id"], "label": by_id[a["id"]]["label"],
                        "applicable": True, "confidence": a.get("confidence", "medium"),
                        "evidence": [a.get("reasoning", "")], "method": "llm"})
    return out


# ── Steps 3+4: retrieve FAR + suggest ──────────────────────────────────────
def review_area(area_id: str, retriever: FARRetriever, doc_text: str,
                client=None, top_k: int = 6) -> Dict[str, Any]:
    area = next(a for a in ISSUE_AREAS if a["id"] == area_id)
    retrieval = retriever.retrieve(area["far_query"], top_k=top_k)
    far_hits = retrieval["semantic"] + retrieval["graph"]
    suggestions = suggest_questions(area, far_hits, doc_text, client)
    return {"id": area_id, "label": area["label"],
            "far_backend": retrieval["backend"],
            "far_sections": [{"section": h["section"], "title": h["title"],
                              "source": h["source"], "via": h.get("via")}
                             for h in far_hits],
            "suggestions": suggestions}


def suggest_questions(area: Dict[str, Any], far_hits: List[Dict[str, Any]],
                      doc_text: str, client=None) -> List[str]:
    if client is not None:
        try:
            return _suggest_llm(area, far_hits, doc_text, client)
        except Exception as e:
            logger.warning(f"[suggest] LLM suggestion failed, using template: {e}")
    return _suggest_template(area, far_hits)


def _suggest_template(area: Dict[str, Any], far_hits: List[Dict[str, Any]]) -> List[str]:
    cites = ", ".join(f"FAR {h['section']}" for h in far_hits[:4]) or "the governing FAR sections"
    label = area["label"]
    return [
        f"This solicitation appears to implicate {label}. Have you confirmed the requirements in {cites}?",
        f"Does the draft include the clauses prescribed for {label}, or state why they don't apply?",
        f"Is there anything the reviewer needs from you to assess {label} (system type, data handled, agency)?",
    ]


def _suggest_llm(area: Dict[str, Any], far_hits: List[Dict[str, Any]],
                 doc_text: str, client) -> List[str]:
    far_context = "\n".join(
        f"- FAR {h['section']} ({h['title']})" + (f" [{h['text'][:300]}]" if h.get("text") else "")
        for h in far_hits[:8]
    )
    system = (
        f"You are helping a contracting officer draft a compliant solicitation. Focus area: "
        f"{area['label']}. Using the retrieved FAR context, produce the questions the officer "
        f"should be asking but may not know to ask, and the concrete things to check in the "
        f"draft. Be specific and cite FAR sections. This is prescriptive guidance — the AI "
        f"prompting the user, not answering a question.\n\n"
        'Return ONLY valid JSON: {"suggestions":["...","..."]}'
    )
    user = f"Retrieved FAR context:\n{far_context}\n\nSolicitation excerpt:\n{doc_text[:6000]}"
    result = client._json_chat(system, user, model=getattr(client, "cheap_model", None),
                               temperature=0.2, max_tokens=1500, retries=2,
                               stage_name="suggestions")
    return (result or {}).get("suggestions", []) or _suggest_template(area, far_hits)


# ── Step 5: optional 508 determination via the v4.1 pipeline ───────────────
def run_determination(files: List[str], client) -> List[Dict[str, Any]]:
    from pipeline import analyze_file  # lazy: heavy deps + model files
    out = []
    for f in files:
        try:
            res = analyze_file(f, client=client)
            rep = res.get("report", {})
            out.append({"file": Path(f).name,
                        "is_508_applicable": rep.get("is_508_applicable"),
                        "bm25_prediction": rep.get("bm25_prediction"),
                        "compliance_assessment": rep.get("compliance_assessment"),
                        "document_summary": rep.get("document_summary", "")[:400]})
        except Exception as e:
            out.append({"file": Path(f).name, "error": str(e)})
    return out


# ── Orchestrator ───────────────────────────────────────────────────────────
def review_package(files: List[str], live: bool = False,
                   determination: bool = False,
                   agency: Optional[str] = None) -> Dict[str, Any]:
    client = None
    if live:
        try:
            from bedrock_adapter import BedrockAdapter
            client = BedrockAdapter()
        except Exception as e:
            logger.warning(f"[review] Bedrock client unavailable ({e}); continuing offline")

    retriever = FARRetriever(offline=None if live else True)

    docs = extract_documents(files)
    combined = "\n\n".join(d["text"] for d in docs)

    areas = infer_issue_areas(combined, client=client)
    reviews = [review_area(a["id"], retriever, combined, client=client) for a in areas]

    # ── Agency scoping: layer the acquiring agency's deviations on top ─────
    agency_key = agency_packs.match_agency(agency) if agency else agency_packs.match_agency(combined)
    devs = agency_packs.deviations_for(agency_key)
    agency_layer = None
    if agency_key and devs:
        agency_layer = {
            "agency": agency_key,
            "source": "explicit" if agency else "detected from text",
            "deviation_count": len(devs),
            "deviations": devs,
            "suggestions": agency_packs.agency_suggestions(agency_key, devs),
        }
        # If 508 is in play, fold the agency layer into that review too.
        for rv in reviews:
            if rv["id"] == "section_508":
                rv["agency_deviations"] = {"agency": agency_key,
                                           "suggestions": agency_layer["suggestions"]}

    result = {
        "files": [{"name": d["name"], "chars": d["chars"]} for d in docs],
        "far_backend": retriever.backend(),
        "inference_method": (areas[0]["method"] if areas else ("llm" if client else "keyword")),
        "agency": agency_key,
        "agency_layer": agency_layer,
        "issue_areas": areas,
        "reviews": reviews,
    }
    if determination:
        if client is None:
            result["determination"] = {"skipped": "requires --live with Bedrock creds"}
        else:
            result["determination"] = run_determination(files, client)
    return result


def print_report(r: Dict[str, Any]) -> None:
    p = print
    p("\n" + "=" * 70)
    p("  SOLICITATION REVIEW — blended FAR_BOT + SRT v4.1")
    p("=" * 70)
    p(f"  Files:      {', '.join(f['name'] for f in r['files'])}")
    p(f"  FAR source: {r['far_backend']}")
    p(f"  Inference:  {r['inference_method']}")
    if r.get("agency"):
        src = r["agency_layer"]["source"] if r.get("agency_layer") else ""
        p(f"  Agency:     {r['agency']}  ({src})")
    if not r["issue_areas"]:
        p("\n  No issue areas detected.")
    for area in r["reviews"]:
        p("\n" + "-" * 70)
        p(f"  ▶ {area['label']}   [FAR via {area['far_backend']}]")
        if area["far_sections"]:
            p("    Relevant FAR:")
            for h in area["far_sections"][:8]:
                tag = h["source"] if h["source"] == "semantic" else f"graph:{h.get('via')}"
                p(f"      • FAR {h['section']}  {h['title']}  ({tag})")
        p("    Suggested questions / checks:")
        for s in area["suggestions"]:
            p(f"      → {s}")
        if area.get("agency_deviations"):
            p(f"    Agency layer ({area['agency_deviations']['agency']}):")
            for s in area["agency_deviations"]["suggestions"]:
                p(f"      ⊕ {s}")
    al = r.get("agency_layer")
    if al:
        p("\n" + "-" * 70)
        p(f"  AGENCY DEVIATIONS — {al['agency']}  ({al['deviation_count']} supplement clauses)")
        for d in al["deviations"][:10]:
            flags = []
            if d["vpat_acr_required"] == "y": flags.append("VPAT/ACR")
            if d["remediation_required"] == "y": flags.append("remediation")
            if d["deliverables_508_required"] == "y": flags.append("508-deliverables")
            fl = f"  [{', '.join(flags)}]" if flags else ""
            p(f"      • {d['section'] or d['part']}{fl}")
    if "determination" in r:
        p("\n" + "-" * 70)
        p("  508 DETERMINATION (v4.1 pipeline):")
        d = r["determination"]
        if isinstance(d, dict) and "skipped" in d:
            p(f"      (skipped — {d['skipped']})")
        else:
            for f in d:
                p(f"      • {f.get('file')}: applicable={f.get('is_508_applicable')} "
                  f"ml={f.get('bm25_prediction')} — {f.get('compliance_assessment')}")
    p("\n" + "=" * 70 + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Blended FAR_BOT + SRT solicitation review")
    ap.add_argument("files", nargs="+", help="solicitation document(s) to review")
    ap.add_argument("--live", action="store_true",
                    help="run entirely on Bedrock (FAR retrieval + inference/suggestions)")
    ap.add_argument("--determination", action="store_true",
                    help="also run the SRT v4.1 508 determination (needs --live)")
    ap.add_argument("--agency", help="acquiring agency (name/abbr, e.g. HHS, VA, USAID); "
                    "auto-detected from the document if omitted")
    ap.add_argument("--json", dest="json_out", help="write full result JSON to this path")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    missing = [f for f in args.files if not Path(f).exists()]
    if missing:
        print(f"error: file(s) not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    result = review_package(args.files, live=args.live, determination=args.determination,
                            agency=args.agency)
    print_report(result)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=str))
        print(f"  full result written to {args.json_out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Focused applicability re-evaluation using the refined APPLICABILITY_SYSTEM_PROMPT.

Targets the cohort where Cynthia disagreed with the prior AI on applicability
(qa_agree_applicability IN (0, 2)) — the cases V4 mostly inherited the same
mistake on. We re-run ONLY the applicability stage with a tighter prompt and
store the structured output in pipeline_eval_runs.applicability_extra.

Usage:
    python pipeline_eval_applicability.py --run-label v4-applicability-v2-2026MMDD --workers 8 --limit 200
"""

import argparse
import gc
import json
import logging
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("pipeline_eval_applicability")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ── Refined applicability prompt ─────────────────────────────────────────────

APPLICABILITY_SYSTEM_PROMPT = """You are a Section 508 ICT applicability classifier for U.S. government solicitations.

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
}
"""

USER_TEMPLATE = """Solicitation number: {sol_num}
Title: {title}
Agency: {agency}

Document text (truncated):
{doc_text}
"""


# ── DB ────────────────────────────────────────────────────────────────────────

def open_db():
    import psycopg2
    full = os.getenv("SECTION_508_DATABASE_URL") or os.getenv("DATABASE_URL")
    if full:
        return psycopg2.connect(full, sslmode="require")
    vcap = os.environ.get("VCAP_SERVICES")
    c = json.loads(vcap)["aws-rds"][0]["credentials"]
    return psycopg2.connect(
        host=c["host"], port=c["port"], dbname=c.get("db_name") or c.get("name"),
        user=c["username"], password=c["password"], sslmode="require",
    )


def fetch_targets(conn, limit: int, reviewer: Optional[str] = "Cynthia") -> List[Dict]:
    """
    Pull reviewed solicitations directly from qa_feedback (joined to
    rag-solicitations), most-recently-reviewed first. Defaults to Cynthia's
    reviews. Use --limit 10 for a smoke test and a large limit for the full run.

    Column aliases (qa_*) match what process_one expects.
    """
    cur = conn.cursor()
    where_clauses = []
    params: list = []
    if reviewer:
        where_clauses.append("q.reviewer_name = %s")
        params.append(reviewer)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(limit)
    cur.execute(f"""
        SELECT s.solicitation_number,
               q.agree_applicability AS qa_agree_applicability,
               q.agree_compliance    AS qa_agree_compliance,
               q.quality_rating      AS qa_quality_rating,
               q.notes               AS qa_notes,
               q.reviewer_name,
               s.ai_applicable AS prior_applicable,
               s.title,
               s.agency,
               COALESCE(legacy.legacy_posted_date, NULL) AS posted_date,
               legacy.legacy_notice_data AS notice_data
        FROM qa_feedback q
        JOIN "rag-solicitations" s ON s.id = q.solicitation_id
        LEFT JOIN LATERAL (
            SELECT date AS legacy_posted_date, "noticeData" AS legacy_notice_data
            FROM solicitations leg
            WHERE leg."solNum" = s.solicitation_number
            ORDER BY leg."createdAt" DESC
            LIMIT 1
        ) legacy ON TRUE
        {where_sql}
        ORDER BY q.created_at DESC
        LIMIT %s
    """, tuple(params))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


# ── SAM helpers (mirror pipeline_eval.py) ────────────────────────────────────

def opp_from_legacy_notice_data(sol_num: str, notice_data) -> Optional[Dict]:
    if not notice_data:
        return None
    if isinstance(notice_data, str):
        try:
            notice_data = json.loads(notice_data)
        except Exception:
            return None
    rls = notice_data.get("resourceLinks") or []
    if not rls:
        return None
    return {
        "solicitationNumber": sol_num,
        "resourceLinks": rls,
        "noticeId": notice_data.get("noticeId"),
        "title": notice_data.get("subject") or notice_data.get("title", sol_num),
    }


class SamCache:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._by_day: Dict[str, List[dict]] = {}
        self._lock = threading.Lock()

    def get_day(self, iso_date: str) -> List[dict]:
        with self._lock:
            if iso_date in self._by_day:
                return self._by_day[iso_date]
        from sam_scraper import fetch_opportunities
        try:
            opps = fetch_opportunities(self.api_key, from_date=iso_date, to_date=iso_date)
            logger.info(f"  [SAM] cached {len(opps)} ICT opps for {iso_date}")
        except Exception as e:
            logger.warning(f"  [SAM] failed to fetch {iso_date}: {e}")
            opps = []
        with self._lock:
            self._by_day[iso_date] = opps
        return opps

    def find(self, sol_num: str, posted_iso: Optional[str]) -> Optional[dict]:
        if not posted_iso:
            return None
        try:
            base = datetime.strptime(posted_iso[:10], "%Y-%m-%d").date()
        except Exception:
            return None
        for offset in (0, -1, 1, -2, 2):
            d = base + timedelta(days=offset)
            iso = d.strftime("%Y-%m-%d")
            for opp in self.get_day(iso):
                if opp.get("solicitationNumber") == sol_num:
                    return opp
        return None


# ── Worker ────────────────────────────────────────────────────────────────────

def get_doc_text(sol_num: str, opp: Dict, attachments_dir: str) -> tuple:
    """Returns (combined_text, num_files). Downloads + extracts on the fly."""
    from sam_scraper import download_attachments
    from text_extractor import extract_text_from_file

    sol_dir = os.path.join(attachments_dir, f"{sol_num}_attachments")
    try:
        file_paths = download_attachments(opp, attachments_dir) or []
        parts: List[str] = []
        for fp in file_paths:
            if not (fp and os.path.exists(fp)):
                continue
            try:
                t, _ = extract_text_from_file(fp)
                if t:
                    parts.append(t)
            except Exception as e:
                logger.warning(f"  text_extractor failed on {fp}: {e}")
        combined = "\n\n".join(parts)[:120_000]
        return combined, len(file_paths)
    finally:
        # Delete this solicitation's downloaded files IMMEDIATELY after extraction,
        # even if download/extraction partially failed, so disk never accumulates
        # across the full run (prevents [Errno 28] No space left on device).
        try:
            if os.path.isdir(sol_dir):
                shutil.rmtree(sol_dir, ignore_errors=True)
        except Exception:
            pass
        gc.collect()


def run_applicability_v2(client, sol_num: str, title: str, agency: str, doc_text: str) -> Dict:
    """Single LLM call against the refined prompt. Returns the parsed JSON dict."""
    user = USER_TEMPLATE.format(sol_num=sol_num, title=title or sol_num, agency=agency or "Unknown",
                                 doc_text=doc_text[:120_000])
    try:
        # Use the existing _json_chat helper which does retry + 429 handling
        result = client._json_chat(
            system=APPLICABILITY_SYSTEM_PROMPT,
            user=user,
            temperature=0.0,
            max_tokens=1200,
            retries=3,
            stage_name="applicability_v2",
        )
        if not isinstance(result, dict):
            return {"applicable": None, "error": "non-dict response"}
        return result
    except Exception as e:
        return {"applicable": None, "error": str(e)}


def process_one(t: Dict, args, sam: SamCache, run_label: str) -> Dict:
    sol_num = t["solicitation_number"]
    started = time.time()

    posted_iso = None
    if t.get("posted_date"):
        try:
            posted_iso = t["posted_date"].isoformat()
        except Exception:
            posted_iso = str(t["posted_date"])

    opp = sam.find(sol_num, posted_iso) or opp_from_legacy_notice_data(sol_num, t.get("notice_data")) \
          or {"solicitationNumber": sol_num}

    try:
        doc_text, num_files = get_doc_text(sol_num, opp, args.attachments_dir)
    except Exception as e:
        return {"sol_num": sol_num, "row": None, "error": str(e), "log": f"{sol_num} download error: {e}"}

    if not doc_text:
        result = {"applicable": None, "error": "no extracted text"}
        v4_applicable = None
    else:
        from usai_adapter import USAIAdapter
        client = USAIAdapter()
        result = run_applicability_v2(client, sol_num, t.get("title") or "", t.get("agency") or "", doc_text)
        v4_applicable = result.get("applicable")
        if v4_applicable is not None and not isinstance(v4_applicable, bool):
            v4_applicable = bool(v4_applicable)

    # Build the row to insert
    elapsed_ms = int((time.time() - started) * 1000)
    row = (
        run_label, "4.1_applicability_v2", sol_num,
        t.get("reviewer_name"), t.get("qa_agree_applicability"), t.get("qa_agree_compliance"),
        t.get("qa_quality_rating"), t.get("qa_notes"),
        v4_applicable, None,  # ai_compliant intentionally None — this run only re-evaluates applicability
        None, None, None, None, None,  # bm25_*
        "applicability_v2_only",  # prediction_source
        num_files, None,
        None, None,  # agree_*_match — recomputed later
        "", [], elapsed_ms, result.get("error"),
        None, None, None, None, None,  # ai_*_explanation, ict_types, document_type, procurement_description
        None, None,  # llm_calls_made / llm_tokens_used
        json.dumps(result),  # applicability_extra
    )

    # Cleanup downloaded files
    try:
        folder = os.path.join(args.attachments_dir, f"{sol_num}_attachments")
        if os.path.isdir(folder):
            shutil.rmtree(folder, ignore_errors=True)
    except Exception:
        pass
    gc.collect()

    return {
        "sol_num": sol_num,
        "row": row,
        "log": f"{sol_num}: files={num_files} v4_applicable={v4_applicable} qa_app={t.get('qa_agree_applicability')} prior={t.get('prior_applicable')} ({elapsed_ms}ms)",
    }


# ── Insert SQL ────────────────────────────────────────────────────────────────

INSERT_SQL = """
INSERT INTO pipeline_eval_runs (
    run_label, pipeline_version, solicitation_number,
    reviewer_name, qa_agree_applicability, qa_agree_compliance, qa_quality_rating, qa_notes,
    ai_applicable, ai_compliant,
    bm25_prediction, bm25_probability, bm25_avg_normalized_score, bm25_max_normalized_score,
    bm25_keyword_hits, prediction_source,
    total_files, applicable_files,
    agree_applicability_match, agree_compliance_match,
    summary, key_findings, processing_time_ms, error,
    ai_applicability_explanation, ai_ict_types, ai_ict_explanation,
    ai_document_type, ai_procurement_description,
    llm_calls_made, llm_tokens_used,
    applicability_extra
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-label", required=True)
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--reviewer", default="Cynthia",
                   help="Reviewer whose qa_feedback rows to target (default: Cynthia)")
    p.add_argument("--attachments-dir", default="/app/attachments_v2")
    args = p.parse_args()

    if not (os.getenv("SAM_API_KEY") or os.getenv("SAM_API")):
        logger.error("SAM_API_KEY not set; cannot fetch attachments.")
        sys.exit(1)

    os.makedirs(args.attachments_dir, exist_ok=True)
    sam = SamCache(os.getenv("SAM_API_KEY") or os.getenv("SAM_API"))

    conn = open_db()
    targets = fetch_targets(conn, args.limit, args.reviewer)
    logger.info(f"Loaded {len(targets)} targets (reviewer={args.reviewer}, limit={args.limit})")

    success = 0
    failed = 0
    insert_lock = threading.Lock()

    def submit_and_drain(executor):
        nonlocal success, failed
        futures = [executor.submit(process_one, t, args, sam, args.run_label) for t in targets]
        for fut in as_completed(futures):
            try:
                outcome = fut.result()
            except Exception as e:
                failed += 1
                logger.error(f"worker crashed: {e}")
                continue
            if outcome.get("row") is None:
                failed += 1
                logger.error(f"  ✗ {outcome.get('log')}")
                continue
            try:
                with insert_lock:
                    cur = conn.cursor()
                    cur.execute(INSERT_SQL, outcome["row"])
                    conn.commit()
                    cur.close()
                success += 1
                logger.info(f"  ✓ {outcome['log']}")
            except Exception as e:
                failed += 1
                logger.error(f"  ✗ insert failed for {outcome['sol_num']}: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        submit_and_drain(ex)

    conn.close()
    logger.info(f"Done. {success} succeeded, {failed} failed. Run label: {args.run_label}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
V4 pipeline evaluation runner.

For the most recent N reviewed solicitations from qa_feedback (joined to
rag-solicitations):
  1) Look up the solicitation on SAM.gov via a date-range search around the
     stored postedDate (cached per day).
  2) Download attachments via the existing scraper helper.
  3) Run the FULL pipeline against the freshly downloaded files:
        - machine readability, BM25 + ML (David's classifier), 508 applicability
          (LLM), ICT classification (LLM), document summary (LLM)
       This is the same code path the daily run uses.
  4) Aggregate the per-file V4 BM25 + ML output into a solicitation-level call.
  5) Write one row into pipeline_eval_runs with both Cynthia's QA labels and
     the V4 outputs side by side.

This run does NOT touch rag-solicitations, rag-documents, or the legacy
solicitations table. It's an evaluation side channel only.
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

logger = logging.getLogger("pipeline_eval")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ── DB ────────────────────────────────────────────────────────────────

def open_db():
    import psycopg2
    full_url = os.getenv("SECTION_508_DATABASE_URL") or os.getenv("DATABASE_URL")
    if full_url:
        return psycopg2.connect(full_url, sslmode="require")
    vcap = os.environ.get("VCAP_SERVICES")
    if not vcap:
        raise RuntimeError("No DB credentials available (need VCAP_SERVICES or DATABASE_URL).")
    c = json.loads(vcap)["aws-rds"][0]["credentials"]
    return psycopg2.connect(
        host=c["host"], port=c["port"], dbname=c.get("db_name") or c.get("name"),
        user=c["username"], password=c["password"], sslmode="require",
    )


def fetch_targets(conn, limit: int, reviewer: Optional[str], only_zero_files_label: Optional[str] = None) -> List[Dict]:
    cur = conn.cursor()
    where_clauses = []
    params: list = []
    if reviewer:
        where_clauses.append("q.reviewer_name = %s")
        params.append(reviewer)
    if only_zero_files_label:
        # Only re-run the solicitations that came back as zero-files in a prior run
        where_clauses.append("""s.solicitation_number IN (
            SELECT solicitation_number FROM pipeline_eval_runs
            WHERE run_label = %s AND total_files = 0
        )""")
        params.append(only_zero_files_label)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(limit)
    cur.execute(f"""
        SELECT s.solicitation_number, s.title, s.agency,
               s.id AS rag_sol_id,
               s.ai_applicable, s.ai_compliant,
               s.solicitation_summary, s.ai_key_findings,
               q.reviewer_name, q.agree_applicability, q.agree_compliance,
               q.quality_rating, q.notes, q.created_at,
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


# ── SAM.gov: by-day search, cached ────────────────────────────────────

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


# ── BM25 + ML aggregation ─────────────────────────────────────────────

def aggregate_v4(individual_analyses: List[Dict], file_paths: List[str]) -> Dict:
    """Run David's BM25 + ML on the combined text of all attachments."""
    from text_extractor import extract_text_from_file
    from bm25_predictor import run_bm25, predict_with_model

    parts: List[str] = []
    for fp in file_paths:
        try:
            t, _ = extract_text_from_file(fp)
            if t:
                parts.append(t)
        except Exception as e:
            logger.warning(f"  text_extractor failed on {fp}: {e}")

    combined = "\n\n".join(parts)[:200_000]
    if not combined:
        return {
            "prediction": "non_compliant",
            "probability": 0.0,
            "source": "no_text",
            "bm25_avg_normalized_score": 0.0,
            "bm25_max_normalized_score": 0.0,
            "bm25_keyword_hits": {},
        }

    model_path = str(Path(__file__).resolve().parent / "data" / "508_compliance_model.joblib")
    bm = run_bm25(combined)
    ml = predict_with_model(combined, bm, model_path)

    # Per-file aggregation for avg/max bucket scores
    per_file_scores = []
    for a in individual_analyses or []:
        sc = a.get("bm25_normalized_score")
        if sc is not None and isinstance(sc, (int, float)):
            per_file_scores.append(float(sc))

    return {
        "prediction": ml.get("prediction"),
        "probability": float(ml.get("probability", 0)),
        "source": ml.get("source", "bm25_ml_model"),
        "bm25_avg_normalized_score": (sum(per_file_scores) / len(per_file_scores)) if per_file_scores else float(bm.get("bm25_normalized_score") or 0),
        "bm25_max_normalized_score": max(per_file_scores) if per_file_scores else float(bm.get("bm25_normalized_score") or 0),
        "bm25_keyword_hits": bm.get("keyword_hits") or {},
    }


# ── INSERT ────────────────────────────────────────────────────────────

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
    llm_calls_made, llm_tokens_used
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def coarse_agree(qa_val, model_truthy):
    if qa_val not in (0, 1):
        return None
    return bool(model_truthy) if qa_val == 1 else not bool(model_truthy)


def aggregate_ict_types(individual_analyses: List[Dict]) -> Dict[str, bool]:
    """Solicitation-level ICT flags = OR across all files."""
    keys = ["Web", "Software", "Hardware", "Electronic_Content", "Telecommunications", "Multimedia", "Medical_Devices"]
    out = {k: False for k in keys}
    for a in individual_analyses or []:
        ict = a.get("ict_types") or (a.get("ict_analysis") or {}).get("ict_types") or {}
        for k in keys:
            if ict.get(k):
                out[k] = True
    return out


def aggregate_applicability_explanation(individual_analyses: List[Dict]) -> str:
    parts = []
    for a in individual_analyses or []:
        e = a.get("applicability_explanation")
        if e:
            parts.append(f"[{a.get('file_name','file')}] {e}")
    return "\n\n".join(parts)[:8000]


def aggregate_ict_explanation(individual_analyses: List[Dict]) -> str:
    parts = []
    for a in individual_analyses or []:
        e = a.get("ict_explanation")
        if e:
            parts.append(f"[{a.get('file_name','file')}] {e}")
    return "\n\n".join(parts)[:8000]


def opp_from_legacy_notice_data(sol_num: str, notice_data) -> Optional[Dict]:
    """Build a minimal SAM 'opp' dict from our stored noticeData.

    The original scraper persisted the full SAM payload in solicitations.noticeData.
    The resource links inside are still valid and downloadable even after the
    listing has been archived from the public search results — we tested it.
    """
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


def process_one_target(idx_total, t, args, sam, run_label, pipeline_version) -> Dict:
    """Worker function: process a single target through the full V4 pipeline.

    Each worker uses its own USAI client and DB connection. Returns a dict the
    main thread inserts into pipeline_eval_runs (after collecting it).
    """
    i, total = idx_total
    sol_num = t["solicitation_number"]
    started = time.time()
    download_error: Optional[str] = None
    file_paths: List[str] = []
    result: Dict = {}

    posted_iso = None
    if t.get("posted_date"):
        try:
            posted_iso = t["posted_date"].isoformat()
        except Exception:
            posted_iso = str(t["posted_date"])

    opp = sam.find(sol_num, posted_iso)
    if not opp:
        # Fall back to our own noticeData (resource links work even when SAM
        # has archived the listing out of date-range search).
        opp = opp_from_legacy_notice_data(sol_num, t.get("notice_data"))
    if not opp:
        opp = {"solicitationNumber": sol_num}

    # Download attachments to a per-solicitation folder
    try:
        from sam_scraper import download_attachments
        file_paths = download_attachments(opp, args.attachments_dir) or []
    except Exception as e:
        download_error = str(e)
        file_paths = []

    # Per-worker USAI client (separate instance avoids any shared rate-limit state)
    from bedrock_adapter import BedrockAdapter
    from solicitation_processor import process_solicitation
    client = BedrockAdapter()

    ai_applicable = None
    ai_compliant = None
    v4 = {}
    ict_types: Dict[str, bool] = {}
    applicability_explanation = ""
    ict_explanation = ""
    document_type = None
    procurement_description = None
    applicable_files = 0
    llm_calls = 0
    llm_tokens = 0
    error_msg: Optional[str] = download_error

    try:
        if file_paths:
            folder = os.path.dirname(file_paths[0])
            result = process_solicitation(
                folder, client=client, standards_path=args.standards_path, embed_model=args.embed_model,
            )
            analyses = result.get("individual_analyses", []) or []
            applicable_files = sum(1 for a in analyses if a.get("is_508_applicable"))
            det = result.get("determination") or {}
            ai_applicable = det.get("is_508_applicable")

            v4 = aggregate_v4(analyses, file_paths)
            ai_compliant = (v4.get("prediction") == "compliant")

            ict_types = aggregate_ict_types(analyses)
            applicability_explanation = aggregate_applicability_explanation(analyses)
            ict_explanation = aggregate_ict_explanation(analyses)

            summary = result.get("summary") or {}
            document_type = summary.get("document_type") or (analyses[0].get("document_type") if analyses else None)
            procurement_description = (summary.get("procurement_description", "") or "")[:8000]

            llm_calls = getattr(client, "_call_count", 0)
            llm_tokens = getattr(client, "_total_tokens", 0)
        else:
            v4 = aggregate_v4([], [])
            ai_compliant = (v4.get("prediction") == "compliant")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"  pipeline failed for {sol_num}: {e}")
        v4 = v4 or {"prediction": None, "probability": 0, "source": "error",
                    "bm25_avg_normalized_score": 0, "bm25_max_normalized_score": 0, "bm25_keyword_hits": {}}
    finally:
        try:
            folder = os.path.join(args.attachments_dir, f"{sol_num}_attachments")
            if os.path.isdir(folder):
                shutil.rmtree(folder, ignore_errors=True)
        except Exception:
            pass
        gc.collect()

    row = (
        run_label, pipeline_version, sol_num,
        t.get("reviewer_name"), t.get("agree_applicability"), t.get("agree_compliance"),
        t.get("quality_rating"), t.get("notes"),
        ai_applicable, ai_compliant,
        v4.get("prediction"), v4.get("probability"),
        v4.get("bm25_avg_normalized_score"), v4.get("bm25_max_normalized_score"),
        json.dumps(v4.get("bm25_keyword_hits") or {}),
        v4.get("source"),
        len(file_paths), applicable_files,
        coarse_agree(t.get("agree_applicability"), ai_applicable),
        coarse_agree(t.get("agree_compliance"), ai_compliant),
        ((result.get("summary") or {}).get("solicitation_summary", "") or "")[:8000],
        (result.get("summary") or {}).get("key_findings", []) or [],
        int((time.time() - started) * 1000),
        error_msg,
        applicability_explanation,
        json.dumps(ict_types),
        ict_explanation,
        document_type,
        procurement_description,
        int(llm_calls or 0),
        int(llm_tokens or 0),
    )
    return {
        "i": i, "total": total, "sol_num": sol_num,
        "row": row,
        "summary_log": f"[{i}/{total}] {sol_num}: files={len(file_paths)} applicable={ai_applicable} pred={v4.get('prediction')} prob={float(v4.get('probability') or 0):.3f} src={v4.get('source')}",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-label", required=True)
    p.add_argument("--pipeline-version", default="4.0_bm25_ml")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--reviewer", default="Cynthia")
    p.add_argument("--attachments-dir", default="/tmp/eval_attachments")
    p.add_argument("--standards-path", default="data/508_standards.txt")
    p.add_argument("--embed-model", default="cohere-english-v3")
    p.add_argument("--workers", type=int, default=1, help="Parallel solicitations to process at once")
    p.add_argument("--recover-zero-from", default=None,
                   help="Only re-run solicitations that came back zero-files in this prior run_label")
    args = p.parse_args()

    sam_api_key = os.getenv("SAM_API_KEY") or os.getenv("SAM_API")
    if not sam_api_key:
        logger.error("SAM_API_KEY not set; cannot re-fetch attachments.")
        sys.exit(1)

    os.makedirs(args.attachments_dir, exist_ok=True)

    logger.info(f"Run label: {args.run_label}")
    logger.info(f"Pipeline:  {args.pipeline_version}")
    logger.info(f"Limit:     {args.limit}  Reviewer: {args.reviewer}  Workers: {args.workers}")

    conn_main = open_db()
    targets = fetch_targets(conn_main, args.limit, args.reviewer,
                            only_zero_files_label=args.recover_zero_from)
    conn_main.close()
    logger.info(f"Loaded {len(targets)} targets from qa_feedback")

    sam = SamCache(sam_api_key)

    insert_lock = threading.Lock()
    insert_conn = open_db()  # one shared writer connection (serialized by lock)

    success = 0
    failed = 0

    indexed_targets = [((i + 1, len(targets)), t) for i, t in enumerate(targets)]

    def submit_and_handle(executor):
        nonlocal success, failed
        futures = [executor.submit(process_one_target, idx_total, t, args, sam, args.run_label, args.pipeline_version)
                   for (idx_total, t) in indexed_targets]
        for fut in as_completed(futures):
            try:
                outcome = fut.result()
            except Exception as e:
                failed += 1
                logger.error(f"worker crashed: {e}")
                continue

            try:
                with insert_lock:
                    cur = insert_conn.cursor()
                    cur.execute(INSERT_SQL, outcome["row"])
                    insert_conn.commit()
                    cur.close()
                success += 1
                logger.info(outcome["summary_log"])
            except Exception as e:
                failed += 1
                logger.error(f"insert failed for {outcome['sol_num']}: {e}")
                try:
                    insert_conn.rollback()
                except Exception:
                    pass

    if args.workers <= 1:
        # Backwards-compatible serial path
        from concurrent.futures import ThreadPoolExecutor as _Single
        with _Single(max_workers=1) as ex:
            submit_and_handle(ex)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            submit_and_handle(ex)

    insert_conn.close()
    logger.info(f"Done. {success} succeeded, {failed} failed. Run label: {args.run_label}")


if __name__ == "__main__":
    main()

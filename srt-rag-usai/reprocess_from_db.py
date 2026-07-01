#!/usr/bin/env python3
"""
Re-run the FULL V4 pipeline against solicitations already stored in the legacy
`solicitations` table (rather than scraping SAM live by date).

For each target row:
  1. Read its stored `noticeData` JSON (the raw SAM payload, incl. resourceLinks).
  2. Reconstruct the SAM "opp" object from it.
  3. Download its attachments, run the full V4 pipeline (BM25 + ML + LLM stages),
     and write results to the rag-* tables AND the legacy solicitations table —
     exactly the same writers the daily run uses.
  4. Delete the downloaded files immediately (keep disk flat).

Targets = solicitations posted in the last N days (default 60), most recent first.

Usage:
    python reprocess_from_db.py --days 60 --limit 5
    python reprocess_from_db.py --from-date 2026-04-01 --to-date 2026-06-01 --limit 5
"""

import argparse
import gc
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("reprocess_from_db")


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


def fetch_targets(conn, from_date, to_date, limit, missing_only=False):
    cur = conn.cursor()
    if missing_only:
        # Only solicitations NOT yet present in rag-solicitations
        cur.execute("""
            SELECT s."solNum", s.title, s.agency, s.office, s."noticeData", s.date
            FROM solicitations s
            LEFT JOIN "rag-solicitations" r ON r.solicitation_number = s."solNum"
            WHERE s.date >= %s AND s.date <= %s
              AND s."noticeData" IS NOT NULL
              AND r.id IS NULL
            ORDER BY s.date DESC
            LIMIT %s
        """, (from_date, to_date, limit))
    else:
        cur.execute("""
            SELECT "solNum", title, agency, office, "noticeData", date
            FROM solicitations
            WHERE date >= %s AND date <= %s
              AND "noticeData" IS NOT NULL
            ORDER BY date DESC
            LIMIT %s
        """, (from_date, to_date, limit))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def opp_from_row(row):
    """Rebuild a SAM opportunity dict from the stored noticeData blob."""
    nd = row.get("noticeData")
    if isinstance(nd, str):
        try:
            nd = json.loads(nd)
        except Exception:
            nd = {}
    nd = nd or {}
    sol_num = row["solNum"]
    opp = dict(nd)  # start from the raw saved SAM payload
    opp["solicitationNumber"] = sol_num
    opp.setdefault("title", row.get("title") or sol_num)
    opp["agency"] = row.get("agency") or nd.get("agency") or "Unknown"
    opp["office"] = row.get("office") or nd.get("office") or ""
    # resourceLinks must be present for downloads; leave as-is if missing
    return opp


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=60, help="Look back this many days (ignored if --from-date given)")
    p.add_argument("--from-date", type=str, default=None, help="YYYY-MM-DD")
    p.add_argument("--to-date", type=str, default=None, help="YYYY-MM-DD")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--workers", type=int, default=8,
                   help="Number of parallel workers (each owns one solicitation end-to-end)")
    p.add_argument("--missing-only", action="store_true",
                   help="Only process solicitations not yet present in rag-solicitations")
    p.add_argument("--attachments-dir", default="/app/attachments_reproc")
    p.add_argument("--csv-output", default=None)
    args = p.parse_args()

    if args.from_date:
        from_date = args.from_date
        to_date = args.to_date or datetime.utcnow().strftime("%Y-%m-%d")
    else:
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        from_date = (datetime.utcnow() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    if not os.getenv("SAM_API_KEY") and not os.getenv("SAM_API"):
        logger.warning("SAM_API_KEY not set — attachment download may fail if links require it.")
    if not (os.getenv("AWS_REGION") or os.getenv("AWS_PROFILE") or os.getenv("AWS_ACCESS_KEY_ID")):
        logger.error("No AWS credentials/region configured — cannot run Bedrock analysis.")
        sys.exit(1)

    db_conn = os.getenv("SECTION_508_DATABASE_URL") or os.getenv("DATABASE_URL")
    if db_conn and db_conn.startswith("postgres://"):
        db_conn = db_conn.replace("postgres://", "postgresql://", 1)
    # If no explicit URL, build one from VCAP for the writers (they accept a conn string)
    if not db_conn:
        c = json.loads(os.environ["VCAP_SERVICES"])["aws-rds"][0]["credentials"]
        db_conn = (f"postgresql://{c['username']}:{c['password']}@{c['host']}:{c['port']}/"
                   f"{c.get('db_name') or c.get('name')}?sslmode=require")

    standards = str(Path(__file__).parent / "data" / "508_standards.txt")
    os.makedirs(args.attachments_dir, exist_ok=True)

    from sam_scraper import download_attachments
    from batch_runner import process_single_solicitation, init_writers, close_writers

    conn = open_db()
    targets = fetch_targets(conn, from_date, to_date, args.limit, args.missing_only)
    conn.close()
    logger.info(f"Loaded {len(targets)} target solicitations from DB ({from_date} → {to_date})"
                f"{' [missing-only]' if args.missing_only else ''}")
    logger.info(f"Running with {args.workers} parallel workers")

    # Each worker thread gets its OWN writers (own DB connection). psycopg2
    # connections are not safe to SHARE across threads, but one-per-thread is the
    # standard safe pattern. Each worker owns one whole solicitation end-to-end:
    # download all its files -> extract -> 4 LLM stages + BM25/ML -> write both schemas.
    # Distinct solicitations never touch the same row, so concurrent upserts are safe.
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    thread_local = threading.local()
    all_writers = []
    writers_lock = threading.Lock()

    def get_writers():
        w = getattr(thread_local, "writers", None)
        if w is None:
            w = init_writers(csv_path=None, db_connection=db_conn)
            thread_local.writers = w
            with writers_lock:
                all_writers.append(w)
        return w

    counters = {"ok": 0, "fail": 0}
    counters_lock = threading.Lock()

    def process_one(idx, row):
        sol_num = row["solNum"]
        opp = opp_from_row(row)
        sol_dir = os.path.join(args.attachments_dir, f"{sol_num}_attachments")
        try:
            files = download_attachments(opp, args.attachments_dir) or []
            opp["attachment_folder"] = sol_dir
            opp["downloaded_files"] = files
            if not files:
                logger.warning(f"[{idx}/{len(targets)}] {sol_num}: no attachments (links retired) — skipping")
                with counters_lock:
                    counters["fail"] += 1
                return
            process_single_solicitation(
                opp=opp, standards_path=standards,
                embed_model="cohere_english_v3", writers=get_writers(),
            )
            with counters_lock:
                counters["ok"] += 1
            logger.info(f"[{idx}/{len(targets)}] ✅ {sol_num} (posted {row.get('date')})")
        except Exception as e:
            logger.error(f"[{idx}/{len(targets)}] {sol_num}: failed — {e}")
            with counters_lock:
                counters["fail"] += 1
        finally:
            if os.path.isdir(sol_dir):
                shutil.rmtree(sol_dir, ignore_errors=True)
            gc.collect()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process_one, i, row) for i, row in enumerate(targets, 1)]
        for f in as_completed(futures):
            f.result()  # surface any unexpected exception

    # Close every per-thread writer set
    for w in all_writers:
        try:
            close_writers(w)
        except Exception:
            pass

    logger.info(f"\nDone. {counters['ok']} processed, {counters['fail']} skipped/failed.")


if __name__ == "__main__":
    main()

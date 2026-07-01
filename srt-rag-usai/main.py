#!/usr/bin/env python3
"""
SRT RAG USAI — Section 508 Analysis Pipeline

Self-contained daily pipeline:
  1. Scrape SAM.gov for new ICT solicitations
  2. Download attachments
  3. Run 7-stage 508 analysis (USAI + Cohere)
  4. Write results to PostgreSQL + CSV

Usage:
    # Full daily run: scrape SAM.gov → analyze → write DB
    python main.py --daily

    # Scrape + analyze a specific date range
    python main.py --daily --from-date 2026-03-28 --to-date 2026-03-28

    # Analyze pre-downloaded attachment folders (skip scraping)
    python main.py --batch-folder /path/to/attachments --csv-output results.csv

    # Single file analysis
    python main.py --file-path /path/to/doc.pdf

    # With database
    python main.py --daily --db-connection "postgresql://..."
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("srt_rag_usai.log"),
    ],
)
logger = logging.getLogger("srt-rag-usai")


def main():
    parser = argparse.ArgumentParser(
        description="SRT RAG USAI — Section 508 Analysis with USAI/Cohere",
    )
    # Modes
    parser.add_argument("--daily", action="store_true",
                        help="Full daily run: scrape SAM.gov → analyze → write DB")
    parser.add_argument("--file-path", type=str, help="Analyze a single file")
    parser.add_argument("--batch-folder", type=str,
                        help="Batch analyze pre-downloaded solicitation folders")

    # Scraper options
    parser.add_argument("--from-date", type=str, default="yesterday",
                        help="Scrape start date (YYYY-MM-DD or 'yesterday')")
    parser.add_argument("--to-date", type=str, default="yesterday",
                        help="Scrape end date (YYYY-MM-DD or 'yesterday')")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max solicitations to process (for testing)")

    # Output options
    parser.add_argument("--csv-output", type=str, help="CSV output path")
    parser.add_argument("--db-connection", type=str, default=None,
                        help="PostgreSQL connection string (or uses DATABASE_URL / SECTION_508_DATABASE_URL)")
    parser.add_argument("--attachments-dir", type=str, default="/app/attachments",
                        help="Directory for downloaded attachments")
    parser.add_argument("--standards-path", type=str, default=None,
                        help="Path to 508_standards.txt")
    parser.add_argument("--embed-model", type=str, default="cohere_english_v3",
                        help="Embedding model")
    parser.add_argument("--save-json", action="store_true",
                        help="Save JSON output alongside CSV")

    args = parser.parse_args()

    # Resolve standards path
    standards = args.standards_path or str(Path(__file__).parent / "data" / "508_standards.txt")

    # Resolve DB connection
    db_conn = args.db_connection or os.getenv("SECTION_508_DATABASE_URL") or os.getenv("DATABASE_URL")
    if db_conn and db_conn.startswith("postgres://"):
        db_conn = db_conn.replace("postgres://", "postgresql://", 1)

    if args.daily:
        _run_daily(args, standards, db_conn)
    elif args.file_path:
        _run_single_file(args.file_path, standards, args.embed_model,
                         args.csv_output, args.save_json)
    elif args.batch_folder:
        _run_batch(args.batch_folder, standards, args.embed_model,
                   args.csv_output, db_conn)
    else:
        parser.print_help()
        sys.exit(1)


def _run_daily(args, standards, db_conn):
    """Full daily pipeline: stream one solicitation at a time from SAM.gov."""
    from sam_scraper import scrape_sam_streaming
    from batch_runner import process_single_solicitation, init_writers, close_writers

    # Verify required keys
    sam_key = os.getenv("SAM_API_KEY")
    if not sam_key:
        logger.error("SAM_API_KEY not set — cannot scrape SAM.gov")
        sys.exit(1)

    usai_key = os.getenv("USAI_API")
    if not usai_key:
        logger.error("USAI_API not set — cannot run analysis")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    att_dir = args.attachments_dir
    csv_path = args.csv_output or f"/app/output/daily_{timestamp}.csv"

    logger.info("=" * 60)
    logger.info("SRT RAG USAI — Daily Pipeline Starting")
    logger.info(f"  Date range: {args.from_date} to {args.to_date}")
    logger.info(f"  Attachments: {att_dir}")
    logger.info(f"  CSV output: {csv_path}")
    logger.info(f"  Database: {'yes' if db_conn else 'no'}")
    logger.info(f"  Limit: {args.limit or 'none'}")
    logger.info("=" * 60)

    # Initialize writers once
    writers = init_writers(csv_path=csv_path, db_connection=db_conn)

    # Stream solicitations one at a time: download → process → delete
    processed = 0
    t0 = time.time()

    for opp in scrape_sam_streaming(
        api_key=sam_key,
        attachments_dir=att_dir,
        from_date=args.from_date,
        to_date=args.to_date,
        limit=args.limit,
    ):
        sol_num = opp.get("solicitationNumber", "unknown")
        idx = opp.get("_index", 0)
        total = opp.get("_total", 0)

        if not opp.get("downloaded_files"):
            logger.info(f"[{idx}/{total}] {sol_num}: no attachments, skipping")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"[{idx}/{total}] Processing: {sol_num}")
        logger.info(f"{'='*60}")

        try:
            count = process_single_solicitation(
                opp=opp,
                standards_path=standards,
                embed_model=args.embed_model,
                writers=writers,
            )
            if count:
                processed += 1
        except Exception as e:
            logger.error(f"❌ Failed {sol_num}: {e}")

    close_writers(writers)
    elapsed = round(time.time() - t0, 1)

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"Daily pipeline complete: {processed} solicitations analyzed in {elapsed}s")
    logger.info(f"CSV: {csv_path}")
    if db_conn:
        logger.info("Results written to database")
    logger.info("=" * 60)


def _run_single_file(file_path, standards, embed_model, csv_output, save_json):
    from usai_adapter import USAIAdapter
    from pipeline import analyze_file

    logger.info(f"Analyzing single file: {file_path}")
    client = USAIAdapter()
    result = analyze_file(file_path, client=client, standards_path=standards,
                          embed_model=embed_model)

    report = result.get("report", {})
    if not report:
        logger.error("Analysis produced empty report")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"File: {report.get('file_name')}")
    print(f"508 Applicable: {report.get('is_508_applicable')}")
    print(f"Includes 508: {report.get('includes_508')}")
    print(f"Matches: {report.get('matches_found')}")
    print(f"Duration: {report.get('total_pipeline_duration_ms')}ms")
    print(f"{'='*50}\n")

    if save_json:
        json_path = csv_output.replace(".csv", ".json") if csv_output else "analysis_result.json"
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        logger.info(f"JSON saved: {json_path}")

    if csv_output:
        from batch_runner import _init_csv, _build_file_base_row, _get_match_fields
        csv_file, writer = _init_csv(csv_output)
        base = _build_file_base_row(report, report.get("solicitation_id", "single_file"))
        matches = report.get("top_matches", [])
        if not matches:
            writer.writerow(base)
        else:
            for m in matches:
                row = base.copy()
                row.update(_get_match_fields(m))
                writer.writerow(row)
        csv_file.close()
        logger.info(f"CSV saved: {csv_output}")


def _run_batch(batch_folder, standards, embed_model, csv_output, db_connection):
    from batch_runner import run_batch

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = csv_output or f"output/batch_analysis_{timestamp}.csv"

    count = run_batch(
        attachments_dir=batch_folder,
        csv_output=csv_path,
        db_connection=db_connection,
        standards_path=standards,
        embed_model=embed_model,
    )

    logger.info(f"Batch complete: {count} solicitations processed")
    if csv_path:
        logger.info(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()

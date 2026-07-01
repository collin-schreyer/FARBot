#!/usr/bin/env python3
"""
sync_review_rec.py — One-shot sync to correct reviewRec in the legacy
`solicitations` table for any row where:
  • reviewRec = 'Cannot Evaluate (Review Required)'   AND
  • a matching row exists in `rag-solicitations` with a real determination

Maps rag-solicitations fields → legacy reviewRec using the same logic
as legacy_db_writer.store_solicitation():

  ai_applicable=False                          → Not Applicable
  ai_applicable=True  AND ai_compliant=True    → Compliant
  ai_applicable=True  AND ai_compliant=False   → Non-compliant (Action Required)
  ai_applicable=None                           → leave as Cannot Evaluate

Also syncs the `predictions` JSONB colour and `compliant` int column.

Usage (via cf run-task):
  python sync_review_rec.py [--dry-run]
"""

import argparse
import logging
import os
import sys
import json
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor, Json

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_review_rec")


def get_conn():
    url = os.getenv("SECTION_508_DATABASE_URL") or os.getenv("DATABASE_URL")
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)


def review_rec_from_rag(rag_row: dict):
    """
    Given a rag-solicitations row, return (review_rec, color, compliant_int).
    Returns (None, None, None) if the rag row has no actionable determination.
    """
    applicable = rag_row.get("ai_applicable")
    compliant  = rag_row.get("ai_compliant")

    if applicable is None:
        return None, None, None

    if applicable is False:
        return "Not Applicable", "grey", 0

    # applicable is True
    # Use bm25_prediction as tiebreaker when ai_compliant is ambiguous
    bm25 = rag_row.get("bm25_prediction")
    if compliant is True or bm25 == "compliant":
        return "Compliant", "green", 1

    return "Non-compliant (Action Required)", "red", 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would change without writing")
    args = parser.parse_args()

    dry = args.dry_run
    if dry:
        logger.info("DRY RUN — no writes will be made")

    conn = get_conn()
    conn.autocommit = False
    read_cur = conn.cursor(cursor_factory=RealDictCursor)
    write_cur = conn.cursor()

    # Find all Cannot Evaluate rows that have a rag match
    read_cur.execute('''
        SELECT
            s."solNum",
            s."reviewRec"      AS old_rec,
            rs.ai_applicable,
            rs.ai_compliant,
            rs.bm25_prediction,
            rs.bm25_probability
        FROM solicitations s
        JOIN "rag-solicitations" rs ON rs.solicitation_number = s."solNum"
        WHERE s."reviewRec" = 'Cannot Evaluate (Review Required)'
          AND rs.ai_applicable IS NOT NULL
        ORDER BY s."solNum"
    ''')
    rows = read_cur.fetchall()
    logger.info(f"Found {len(rows)} Cannot Evaluate rows with a rag determination to sync")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    updated = 0
    skipped = 0

    for row in rows:
        sol_num = row["solNum"]
        new_rec, color, compliant_int = review_rec_from_rag(row)

        if new_rec is None:
            skipped += 1
            continue

        predictions = {
            "value": color,
            "508": color,
            "estar": "Not Applicable",
            "history": [{"date": now_str, "value": color, "508": color,
                          "estar": "Not Applicable"}],
        }

        logger.info(f"  {sol_num}: '{row['old_rec']}' → '{new_rec}' "
                    f"(applicable={row['ai_applicable']}, compliant={row['ai_compliant']}, "
                    f"bm25={row['bm25_prediction']})")

        if not dry:
            write_cur.execute('''
                UPDATE solicitations
                SET "reviewRec"  = %s,
                    compliant    = %s,
                    predictions  = %s,
                    "updatedAt"  = NOW()
                WHERE "solNum"   = %s
            ''', (new_rec, compliant_int, Json(predictions), sol_num))

        updated += 1

    if not dry:
        conn.commit()
        logger.info(f"Committed. Updated: {updated}, Skipped (no determination): {skipped}")
    else:
        conn.rollback()
        logger.info(f"Dry run complete. Would update: {updated}, Would skip: {skipped}")

    read_cur.close()
    write_cur.close()
    conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Legacy Database Writer — Inserts solicitation metadata into the original
'solicitations' table used by the SRT frontend (srt-api / srt-ui).

This bridges the new RAG pipeline output back into the legacy schema so that
the existing SRT Angular dashboard continues to display new solicitations
with all the metadata the old srt-fbo-scraper used to populate.
"""

import logging
import os
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import psycopg2
from psycopg2.extras import Json

logger = logging.getLogger(__name__)


class LegacyDBWriter:
    """
    Writes solicitation records into the original `solicitations` and
    `attachment` tables so the SRT frontend picks them up.
    """

    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or self._get_connection_string()
        self.connection = None
        self._connect()

    def _get_connection_string(self) -> str:
        full_url = os.getenv("SECTION_508_DATABASE_URL") or os.getenv("DATABASE_URL")
        if full_url:
            if full_url.startswith("postgres://"):
                full_url = full_url.replace("postgres://", "postgresql://", 1)
            return full_url
        host = os.getenv("RAG_DB_HOST", "localhost")
        port = os.getenv("RAG_DB_PORT", "5432")
        db = os.getenv("RAG_DB_NAME", "SRT")
        user = os.getenv("RAG_DB_USER", "circleci")
        pw = os.getenv("RAG_DB_PASSWORD", "srtpass")
        return f"postgresql://{user}:{pw}@{host}:{port}/{db}"

    def _connect(self):
        try:
            self.connection = psycopg2.connect(self.connection_string)
            self.connection.autocommit = True
            logger.info("[LegacyDB] Connected to solicitations table")
        except Exception as e:
            logger.error(f"[LegacyDB] Connection failed: {e}")
            raise

    def _ensure_notice_type(self, notice_type: str) -> Optional[int]:
        """Get or create a notice_type row and return its ID."""
        with self.connection.cursor() as cur:
            cur.execute(
                'SELECT id FROM notice_type WHERE notice_type = %s',
                (notice_type,),
            )
            row = cur.fetchone()
            if row:
                return row[0]
            # Insert new notice type
            cur.execute(
                'INSERT INTO notice_type (notice_type, "createdAt") VALUES (%s, NOW()) RETURNING id',
                (notice_type,),
            )
            return cur.fetchone()[0]

    def _resolve_agency_id(self, agency_name: str) -> Optional[int]:
        """Look up agency_id from agency_alias table."""
        try:
            with self.connection.cursor() as cur:
                cur.execute(
                    'SELECT agency_id FROM agency_alias WHERE alias = %s LIMIT 1',
                    (agency_name,),
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def store_solicitation(
        self,
        opp: Dict[str, Any],
        result: Dict[str, Any],
        sklearn_prediction: Dict[str, Any] = None,
    ) -> bool:
        """
        Write (upsert) a solicitation into the legacy `solicitations` table.

        Args:
            opp: Raw SAM.gov opportunity dict (from sam_scraper)
            result: Pipeline result dict (from batch_runner)
            sklearn_prediction: Output from sklearn_predictor.predict_solicitation()

        Returns:
            True if successful
        """
        sol_num = opp.get("solicitationNumber", "")
        if not sol_num:
            logger.warning("[LegacyDB] No solicitationNumber — skipping")
            return False

        try:
            now = datetime.now(timezone.utc)
            now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            # --- Parse SAM.gov metadata (same as old schematize_opp) ---
            hierarchy = opp.get("fullParentPathName", "").split(".")
            agency = hierarchy[0].strip() if hierarchy else ""
            office = hierarchy[1].strip() if len(hierarchy) > 1 else ""

            notice_type_raw = opp.get("type", {})
            if isinstance(notice_type_raw, dict):
                notice_type_code = notice_type_raw.get("value", "o")
            else:
                notice_type_code = str(notice_type_raw)

            notice_type_map = {
                "o": "Solicitation",
                "p": "Presolicitation",
                "k": "Combined Synopsis/Solicitation",
            }
            notice_type = notice_type_map.get(notice_type_code, notice_type_code)

            title = opp.get("title", sol_num)
            url = opp.get("uiLink", "")
            posted_date = opp.get("postedDate", now_str)
            naics = opp.get("naicsCode", "")
            psc = opp.get("classificationCode", "")
            set_aside = opp.get("typeOfSetAside", "")

            # Contact info
            poc = opp.get("pointOfContact", [])
            emails = [p.get("email") for p in (poc or []) if p.get("email")]

            # --- Determine compliance from sklearn ---
            compliant_int = 0
            review_rec = "Non-compliant (Action Required)"
            prediction_color = "red"

            # Pull the authoritative determination from the new RAG pipeline result.
            # This is what the detail page in the UI also reads.
            det = result.get("determination", {}) or {}
            is_applicable = det.get("is_508_applicable")
            includes_508 = det.get("includes_508")
            det_total_files = det.get("total_files")

            # ── Fallback: read from rag-solicitations if this write is a post-hoc
            # update and the in-memory determination is missing. This prevents
            # "Cannot Evaluate" from persisting in the legacy table when the RAG
            # pipeline has already written a real verdict to rag-solicitations.
            if is_applicable is None and sol_num:
                try:
                    with self.connection.cursor() as _cur:
                        _cur.execute(
                            'SELECT ai_applicable, ai_compliant, bm25_prediction '
                            'FROM "rag-solicitations" WHERE solicitation_number = %s '
                            'ORDER BY updated_at DESC NULLS LAST LIMIT 1',
                            (sol_num,),
                        )
                        _rag = _cur.fetchone()
                    if _rag and _rag[0] is not None:
                        is_applicable = _rag[0]
                        # Use bm25_prediction as primary signal, fall back to ai_compliant
                        bm25_pred = _rag[2]
                        if bm25_pred == "compliant":
                            includes_508 = True
                        elif bm25_pred == "non_compliant":
                            includes_508 = False
                        elif _rag[1] is not None:
                            includes_508 = _rag[1]
                        logger.info(
                            f"[LegacyDB] {sol_num}: loaded determination from "
                            f"rag-solicitations (applicable={is_applicable}, "
                            f"includes_508={includes_508}, bm25={bm25_pred})"
                        )
                except Exception as _e:
                    logger.warning(f"[LegacyDB] {sol_num}: rag fallback lookup failed: {_e}")

            if sklearn_prediction:
                is_compliant = sklearn_prediction.get("includes_508", False)
                if is_compliant:
                    compliant_int = 1
                    review_rec = "Compliant"
                    prediction_color = "green"
            else:
                # Fall back to LLM determination
                if includes_508:
                    compliant_int = 1
                    review_rec = "Compliant"
                    prediction_color = "green"

            # Override based on the pipeline's authoritative applicability call.
            # Not Applicable trumps everything — it's a definite, intentional state.
            if is_applicable is False:
                review_rec = "Not Applicable"
                prediction_color = "grey"
                compliant_int = 0
            elif is_applicable is True:
                # Applicable. Use compliance signal (sklearn first, then LLM).
                if includes_508 or (sklearn_prediction and sklearn_prediction.get("includes_508")):
                    review_rec = "Compliant"
                    prediction_color = "green"
                    compliant_int = 1
                else:
                    review_rec = "Non-compliant (Action Required)"
                    prediction_color = "red"
                    compliant_int = 0

            # "Cannot Evaluate" should only fire when the pipeline truly produced no
            # determination AND no documents could be analyzed. The previous logic
            # checked text_length on the legacy analyses array, which produced
            # false positives whenever this writer's text-extraction step returned
            # zero even though the RAG pipeline had successfully analyzed the docs.
            analyses = result.get("individual_analyses", []) or []
            num_docs = len(analyses)

            pipeline_produced_a_call = is_applicable is not None or includes_508 is not None
            has_any_files = num_docs > 0 or (det_total_files is not None and det_total_files > 0)
            has_readable = any((a.get("text_length", 0) or 0) > 0 for a in analyses)

            if not pipeline_produced_a_call and not has_any_files:
                # No pipeline call AND no files at all → genuine "no data."
                review_rec = "Cannot Evaluate (Review Required)"
                prediction_color = "yellow"
                compliant_int = 0
            elif not pipeline_produced_a_call and num_docs > 0 and not has_readable:
                # Pipeline produced no call AND every analysis came back empty →
                # extraction failed across the board.
                review_rec = "Cannot Evaluate (Review Required)"
                prediction_color = "yellow"
                compliant_int = 0

            # --- Build the noticeData JSONB (entire raw SAM payload) ---
            notice_data = deepcopy(opp)
            # Remove large binary fields we don't need in the JSON blob
            notice_data.pop("downloaded_files", None)
            notice_data.pop("attachment_folder", None)
            notice_data.pop("_index", None)
            notice_data.pop("_total", None)
            # Add the parsed fields for compatibility
            notice_data["notice type"] = notice_type
            notice_data["solnbr"] = sol_num
            notice_data["agency"] = agency
            notice_data["office"] = office
            notice_data["classcod"] = psc
            notice_data["psc"] = psc
            notice_data["naics"] = naics
            notice_data["subject"] = title
            notice_data["url"] = url
            notice_data["setaside"] = set_aside
            notice_data["emails"] = emails

            # --- Build the predictions JSONB ---
            predictions = {
                "value": prediction_color,
                "508": prediction_color,
                "estar": "Not Applicable",
                "history": [
                    {
                        "date": now_str,
                        "value": prediction_color,
                        "508": prediction_color,
                        "estar": "Not Applicable",
                    }
                ],
            }

            # --- Build parse status ---
            # Pair each analyzed file with its SAM.gov resource link so the UI can
            # download the original document. SAM returns resourceLinks in the same
            # order that download_attachments saved files, so we zip by index, then
            # also build a name-to-URL map as a fallback.
            resource_links = opp.get("resourceLinks") or []
            downloaded_files = opp.get("downloaded_files") or []
            url_by_basename = {}
            for idx, file_path in enumerate(downloaded_files):
                if idx < len(resource_links):
                    basename = os.path.basename(file_path)
                    url_by_basename[basename] = resource_links[idx]

            parse_status = []
            for i, a in enumerate(analyses):
                file_name = a.get("file_name", "unknown")
                # Prefer name match; fall back to position; finally empty.
                a_url = (
                    a.get("url")
                    or url_by_basename.get(file_name)
                    or (resource_links[i] if i < len(resource_links) else "")
                )
                parse_status.append({
                    "name": file_name,
                    "status": "successfully parsed" if a.get("text_length", 0) > 0 else "processing error",
                    "postedDate": now_str,
                    "attachment_url": a_url,
                })

            # --- Build action history ---
            action = [
                {
                    "date": now_str,
                    "user": "",
                    "action": "Solicitation Posted",
                    "status": "complete",
                }
            ]

            # --- Build search text ---
            search_text = " ".join([
                sol_num, notice_type, title, posted_date or "",
                review_rec, "Solicitation Posted", now_str,
                agency, office,
            ]).lower()

            # --- Notice type ID ---
            notice_type_id = self._ensure_notice_type(notice_type)

            # --- Agency ID ---
            agency_id = self._resolve_agency_id(agency)

            # --- Check if solicitation already exists ---
            with self.connection.cursor() as cur:
                cur.execute(
                    'SELECT id, "solNum" FROM solicitations WHERE "solNum" = %s',
                    (sol_num,),
                )
                existing = cur.fetchone()

            if existing:
                # UPDATE existing solicitation
                with self.connection.cursor() as cur:
                    cur.execute("""
                        UPDATE solicitations SET
                            title = %s,
                            url = %s,
                            agency = %s,
                            agency_id = %s,
                            office = %s,
                            "numDocs" = %s,
                            notice_type_id = %s,
                            "noticeType" = %s,
                            date = %s,
                            compliant = %s,
                            "noticeData" = %s,
                            "reviewRec" = %s,
                            predictions = %s,
                            "parseStatus" = %s,
                            "contactInfo" = %s,
                            "searchText" = %s,
                            "updatedAt" = NOW()
                        WHERE "solNum" = %s
                    """, (
                        title, url, agency, agency_id, office,
                        num_docs, notice_type_id, notice_type,
                        posted_date, compliant_int,
                        Json(notice_data), review_rec,
                        Json(predictions), Json(parse_status),
                        Json(emails), search_text,
                        sol_num,
                    ))
                logger.info(f"[LegacyDB] Updated solicitation {sol_num}")

            else:
                # INSERT new solicitation
                with self.connection.cursor() as cur:
                    cur.execute("""
                        INSERT INTO solicitations (
                            "solNum", active, title, url, agency, agency_id, office,
                            "numDocs", notice_type_id, "noticeType", date,
                            na_flag, category_list, undetermined,
                            history, action, "actionStatus", "actionDate",
                            "contactInfo", "parseStatus", predictions,
                            "reviewRec", "searchText", compliant, "noticeData",
                            "createdAt"
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s,
                            NOW()
                        )
                    """, (
                        sol_num, True, title, url, agency, agency_id, office,
                        num_docs, notice_type_id, notice_type, posted_date,
                        False, Json({"value": "yes", "it": "yes", "estar": "no"}), False,
                        Json([]), Json(action), "Solicitation Posted", now,
                        Json(emails), Json(parse_status), Json(predictions),
                        review_rec, search_text, compliant_int, Json(notice_data),
                    ))
                logger.info(f"[LegacyDB] Inserted solicitation {sol_num}")

            # --- Store attachments in the attachment table ---
            self._store_attachments(sol_num, analyses, notice_type_id, sklearn_prediction)

            return True

        except Exception as e:
            logger.error(f"[LegacyDB] Failed to store {sol_num}: {e}")
            logger.error(traceback.format_exc())
            return False

    def _store_attachments(
        self,
        sol_num: str,
        analyses: List[Dict],
        notice_type_id: int,
        sklearn_prediction: Dict = None,
    ):
        """Store individual file records in the legacy `attachment` table."""
        try:
            # Get the solicitation ID
            with self.connection.cursor() as cur:
                cur.execute(
                    'SELECT id FROM solicitations WHERE "solNum" = %s',
                    (sol_num,),
                )
                row = cur.fetchone()
                if not row:
                    return
                sol_id = row[0]

            for analysis in analyses:
                filename = analysis.get("file_name", "unknown")
                text = analysis.get("extracted_text", "") or ""
                machine_readable = len(text) > 0

                # Per-file prediction from sklearn (1=compliant, 0=non-compliant)
                prediction = 0
                decision_boundary = 0.0
                if sklearn_prediction:
                    prediction = 1 if sklearn_prediction.get("includes_508", False) else 0
                    decision_boundary = sklearn_prediction.get("confidence", 0.0)

                with self.connection.cursor() as cur:
                    # Check if attachment already exists
                    cur.execute(
                        'SELECT id FROM attachment WHERE solicitation_id = %s AND filename = %s',
                        (sol_id, filename),
                    )
                    existing = cur.fetchone()

                    if existing:
                        cur.execute("""
                            UPDATE attachment SET
                                machine_readable = %s,
                                attachment_text = %s,
                                prediction = %s,
                                decision_boundary = %s,
                                "updatedAt" = NOW()
                            WHERE id = %s
                        """, (
                            machine_readable, text[:50000], prediction,
                            decision_boundary, existing[0],
                        ))
                    else:
                        cur.execute("""
                            INSERT INTO attachment (
                                notice_type_id, solicitation_id, filename,
                                machine_readable, attachment_text,
                                prediction, decision_boundary,
                                validation, trained, "createdAt"
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """, (
                            notice_type_id, sol_id, filename,
                            machine_readable, text[:50000],
                            prediction, decision_boundary,
                            None, False,
                        ))

            logger.info(f"[LegacyDB] Stored {len(analyses)} attachments for {sol_num}")

        except Exception as e:
            logger.error(f"[LegacyDB] Failed to store attachments for {sol_num}: {e}")

    def close(self):
        if self.connection:
            self.connection.close()
            logger.info("[LegacyDB] Connection closed")

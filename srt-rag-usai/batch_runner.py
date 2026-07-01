#!/usr/bin/env python3
"""
Batch Runner — Process multiple solicitation folders, write to DB + CSV.
"""

import csv
import gc
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional

from bedrock_adapter import BedrockAdapter
from solicitation_processor import process_solicitation

logger = logging.getLogger(__name__)


def run_batch(
    attachments_dir: str,
    csv_output: str = None,
    db_connection: str = None,
    standards_path: str = None,
    embed_model: str = "cohere_english_v3",
) -> int:
    """
    Process all solicitation folders in attachments_dir.

    Args:
        attachments_dir: Directory containing solicitation folders
        csv_output: Path for CSV export (optional)
        db_connection: PostgreSQL connection string (optional)
        standards_path: Path to 508_standards.txt
        embed_model: Embedding model name

    Returns:
        Number of solicitations processed
    """
    att_dir = Path(attachments_dir)
    if not att_dir.exists():
        logger.error(f"Attachments directory not found: {attachments_dir}")
        return 0

    sol_folders = sorted([f for f in att_dir.iterdir() if f.is_dir()])
    if not sol_folders:
        logger.error(f"No solicitation folders found in {attachments_dir}")
        return 0

    logger.info(f"Found {len(sol_folders)} solicitation folders to process")

    # Initialize USAI client (shared across all solicitations)
    client = BedrockAdapter()

    # Initialize DB writer if connection provided
    db_writer = None
    if db_connection:
        try:
            from rag_data_writer import RAGDataWriter
            db_writer = RAGDataWriter(db_connection)
            logger.info("Database writer initialized")
        except Exception as e:
            logger.warning(f"Database writer init failed: {e} — continuing without DB")

    # Initialize CSV
    csv_file = None
    csv_writer = None
    if csv_output:
        csv_file, csv_writer = _init_csv(csv_output)

    processed = 0
    t0 = time.time()

    for i, sol_folder in enumerate(sol_folders):
        logger.info(f"\n{'='*60}")
        logger.info(f"[{i+1}/{len(sol_folders)}] Processing: {sol_folder.name}")
        logger.info(f"{'='*60}")

        try:
            result = process_solicitation(
                str(sol_folder),
                client=client,
                standards_path=standards_path,
                embed_model=embed_model,
            )

            # Write to CSV
            if csv_writer and csv_file:
                _write_solicitation_csv(csv_writer, result)

            # Write to database
            if db_writer:
                try:
                    _write_to_database(db_writer, result)
                except Exception as e:
                    logger.error(f"DB write failed for {sol_folder.name}: {e}")

            processed += 1
            det = result.get("determination", {})
            logger.info(f"✅ {sol_folder.name}: applicable={det.get('is_508_applicable')}, "
                        f"includes_508={det.get('includes_508')}, "
                        f"files={det.get('total_files')}")

            # Clean up attachment files to free memory/disk
            try:
                shutil.rmtree(str(sol_folder), ignore_errors=True)
                gc.collect()
                logger.info(f"🧹 Cleaned up {sol_folder.name}")
            except Exception:
                pass

        except Exception as e:
            logger.error(f"❌ Failed to process {sol_folder.name}: {e}")
            # Still clean up on failure
            try:
                shutil.rmtree(str(sol_folder), ignore_errors=True)
                gc.collect()
            except Exception:
                pass

    elapsed = round(time.time() - t0, 1)
    logger.info(f"\n{'='*60}")
    logger.info(f"Batch complete: {processed}/{len(sol_folders)} solicitations in {elapsed}s")
    logger.info(f"{'='*60}")

    if csv_file:
        csv_file.close()
        logger.info(f"CSV saved: {csv_output}")

    if db_writer:
        db_writer.close()

    return processed


# ── Streaming mode: process one solicitation at a time ────────────────

def init_writers(csv_path: str = None, db_connection: str = None) -> Dict:
    """Initialize CSV and DB writers for streaming mode."""
    writers = {"csv_file": None, "csv_writer": None, "db_writer": None, "legacy_writer": None, "client": BedrockAdapter()}

    if csv_path:
        writers["csv_file"], writers["csv_writer"] = _init_csv(csv_path)

    if db_connection:
        try:
            from rag_data_writer import RAGDataWriter
            writers["db_writer"] = RAGDataWriter(db_connection)
            logger.info("Database writer initialized")
        except Exception as e:
            logger.warning(f"Database writer init failed: {e}")

        try:
            from legacy_db_writer import LegacyDBWriter
            writers["legacy_writer"] = LegacyDBWriter(db_connection)
            logger.info("Legacy solicitations writer initialized")
        except Exception as e:
            logger.warning(f"Legacy DB writer init failed: {e}")

    return writers


def close_writers(writers: Dict):
    """Close CSV and DB writers."""
    if writers.get("csv_file"):
        writers["csv_file"].close()
    if writers.get("db_writer"):
        writers["db_writer"].close()
    if writers.get("legacy_writer"):
        writers["legacy_writer"].close()


def process_single_solicitation(
    opp: Dict,
    standards_path: str,
    embed_model: str,
    writers: Dict,
) -> bool:
    """
    Process one solicitation: analyze files, run SetFit, write results, clean up.

    Returns True if successfully processed.
    """
    sol_num = opp.get("solicitationNumber", "unknown")
    folder = opp.get("attachment_folder", "")
    client = writers.get("client")

    try:
        # Run the RAG pipeline on all files
        result = process_solicitation(
            folder,
            client=client,
            standards_path=standards_path,
            embed_model=embed_model,
        )

        # Run BM25 + ML compliance prediction (David's v4 model)
        try:
            from text_extractor import extract_text_from_file
            from bm25_predictor import run_bm25, predict_with_model
            from pathlib import Path as _Path

            file_texts = []
            for analysis in result.get("individual_analyses", []):
                file_path = analysis.get("path", "")
                if file_path and os.path.exists(file_path):
                    text, _ = extract_text_from_file(file_path)
                    file_texts.append({"file_name": analysis.get("file_name", ""), "text": text})

            if file_texts:
                model_path = str(_Path(__file__).resolve().parent / "data" / "508_compliance_model.joblib")

                # Run the BM25 + ML model PER FILE. The solicitation-level verdict
                # uses the "any compliant file wins" rule: if even one file in the
                # package includes 508 language, the whole solicitation is Compliant.
                # This keeps the solicitation verdict, the per-file chips, and the
                # legacy reviewRec all consistent (all sourced from bm25_prediction).
                per_file_preds = []
                best = None  # the compliant file (or highest-prob file) drives the headline
                for ft in file_texts:
                    txt = ft.get("text", "")
                    if not txt:
                        continue
                    bm = run_bm25(txt)
                    ml = predict_with_model(txt, bm, model_path)
                    pred = {
                        "file_name": ft.get("file_name", ""),
                        "prediction": ml.get("prediction"),
                        "probability": ml.get("probability", 0),
                        "bm25_raw_score": bm.get("bm25_raw_score", 0),
                        "bm25_normalized_score": bm.get("bm25_normalized_score", 0),
                        "bm25_bucket": bm.get("bucket", ""),
                        "bm25_keyword_hits": bm.get("keyword_hits", {}),
                    }
                    per_file_preds.append(pred)

                # Attach each file's bm25 prediction back onto its analysis record so
                # the per-file rag-documents rows store the same signal the UI shows.
                _by_name = {p["file_name"]: p for p in per_file_preds}
                for analysis in result.get("individual_analyses", []):
                    p = _by_name.get(analysis.get("file_name", ""))
                    if p:
                        analysis["bm25_prediction"] = p["prediction"]
                        analysis["bm25_probability"] = p["probability"]
                        analysis["bm25_raw_score"] = p["bm25_raw_score"]
                        analysis["bm25_normalized_score"] = p["bm25_normalized_score"]
                        analysis["bm25_bucket"] = p["bm25_bucket"]
                        analysis["bm25_keyword_hits"] = p["bm25_keyword_hits"]

                # "Any compliant file" rule for the solicitation-level call.
                compliant_files = [p for p in per_file_preds if p["prediction"] == "compliant"]
                solicitation_compliant = len(compliant_files) > 0
                if solicitation_compliant:
                    # Headline from the strongest compliant file.
                    best = max(compliant_files, key=lambda p: p["probability"])
                elif per_file_preds:
                    # No compliant file — surface the strongest non-compliant signal.
                    best = max(per_file_preds, key=lambda p: p["probability"])
                else:
                    best = {"prediction": "non_compliant", "probability": 0,
                            "bm25_raw_score": 0, "bm25_normalized_score": 0,
                            "bm25_bucket": "", "bm25_keyword_hits": {}}

                v4_prediction = {
                    "is_508_applicable": True,  # applicability is decided by the LLM stage; we only override compliance
                    "includes_508": solicitation_compliant,
                    "prediction": "compliant" if solicitation_compliant else "non_compliant",
                    "probability": best.get("probability", 0),
                    "source": "bm25_ml_model",
                    "bm25_raw_score": best.get("bm25_raw_score", 0),
                    "bm25_normalized_score": best.get("bm25_normalized_score", 0),
                    "bm25_bucket": best.get("bm25_bucket", ""),
                    "bm25_keyword_hits": best.get("bm25_keyword_hits", {}),
                }

                # Stash for the legacy writer (it expects key "setfit_prediction" historically; we
                # carry the same shape under a clearer name).
                result["v4_prediction"] = v4_prediction
                # Backwards-compatible key for legacy_db_writer.store_solicitation()
                result["setfit_prediction"] = {
                    "includes_508": v4_prediction["includes_508"],
                    "is_508_applicable": v4_prediction["is_508_applicable"],
                    "confidence": v4_prediction["probability"],
                    "prediction": v4_prediction["prediction"],
                    "prediction_source": "bm25_ml_model",
                }

                det = result.get("determination", {})
                det["v4_includes_508"] = v4_prediction["includes_508"]
                det["v4_probability"] = v4_prediction["probability"]
                det["v4_bucket"] = v4_prediction["bm25_bucket"]
                det["prediction_source"] = "bm25_ml_model"
                # Override the includes_508 with the v4 model result. Applicability stays
                # with the LLM (which is grounded in FAR 39.104).
                det["includes_508"] = v4_prediction["includes_508"]
                result["determination"] = det

                logger.info(
                    f"🤖 v4 BM25+ML: prediction={v4_prediction['prediction']} "
                    f"prob={v4_prediction['probability']:.3f} bucket={v4_prediction['bm25_bucket']}"
                )

                # ── LLM determination summary (grounded in BM25 evidence) ──
                # A quick LLM pass that reads the BM25 keyword evidence across ALL
                # files and explains, in plain English, WHY the solicitation was
                # judged to include / not include 508 language. Stored on the
                # solicitation so the UI/QA app can show the reasoning.
                try:
                    summary_files = [
                        {
                            "file_name": p.get("file_name", ""),
                            "prediction": p.get("prediction", ""),
                            "bm25_bucket": p.get("bm25_bucket", ""),
                            "keyword_hits": p.get("bm25_keyword_hits", {}) or {},
                        }
                        for p in per_file_preds
                    ]
                    det_summary = client.summarize_bm25_determination(
                        verdict=v4_prediction["prediction"],
                        is_applicable=v4_prediction["is_508_applicable"],
                        per_file=summary_files,
                        title=opp.get("title", sol_num),
                    )
                    determination_summary = det_summary.get("determination_summary", "")
                    if determination_summary:
                        result["determination_summary"] = determination_summary
                        result.setdefault("summary", {})
                        result["summary"]["determination_summary"] = determination_summary
                        logger.info(f"📝 BM25 determination summary: {determination_summary[:120]}...")
                except Exception as e:
                    logger.warning(f"BM25 determination summary failed: {e}")
        except Exception as e:
            logger.warning(f"v4 BM25+ML prediction failed: {e} — using LLM determination")

        # Add metadata from SAM.gov opportunity
        if result.get("summary") is None:
            result["summary"] = {}
        metadata = {
            "title": opp.get("title", sol_num),
            "agency": opp.get("agency", "Unknown"),
            "office": opp.get("office", ""),
        }

        # Write to CSV
        if writers.get("csv_writer") and writers.get("csv_file"):
            _write_solicitation_csv(writers["csv_writer"], result)

        # Write to database (RAG tables)
        if writers.get("db_writer"):
            try:
                _write_to_database(writers["db_writer"], result, metadata=metadata)
            except Exception as e:
                logger.error(f"DB write failed for {sol_num}: {e}")

        # Write to legacy solicitations table (for SRT frontend)
        if writers.get("legacy_writer"):
            try:
                writers["legacy_writer"].store_solicitation(
                    opp=opp,
                    result=result,
                    sklearn_prediction=result.get("setfit_prediction"),
                )
            except Exception as e:
                logger.error(f"Legacy DB write failed for {sol_num}: {e}")

        det = result.get("determination", {})
        logger.info(f"✅ {sol_num}: applicable={det.get('is_508_applicable')}, "
                    f"includes_508={det.get('includes_508')}, "
                    f"files={det.get('total_files')}")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to process {sol_num}: {e}")
        return False

    finally:
        # Always clean up attachments
        if folder and os.path.isdir(folder):
            shutil.rmtree(folder, ignore_errors=True)
            gc.collect()
            logger.info(f"🧹 Cleaned up {sol_num}")


# ── CSV helpers ───────────────────────────────────────────────────────

CSV_HEADERS = [
    # Row type
    "row_type", "solicitation_id",
    # Basic file info
    "file_name", "file_path", "file_size_mb", "modification_date",
    # Core 508
    "is_508_applicable", "confidence_score", "is_compliant",
    "has_explicit_508_mention", "matches_found", "match_strength",
    "vector_match_strength", "is_discussing_508", "is_physical_only",
    "key_standards_matched", "applicable_ict_types", "ict_explanation",
    "applicability_explanation", "compliance_explanation", "recommendations",
    # Context
    "website_source", "is_cots_product", "alternative_accessibility_regs",
    "false_positives_filtered",
    # Conflict resolution
    "applicability_conflict_detected", "applicability_resolution_method",
    "applicability_override_reason", "compliance_conflict_detected",
    "compliance_resolution_method", "compliance_decision_reasoning",
    "meaningful_matches_count", "high_quality_meaningful_matches_count",
    "explicit_accessibility_matches_count", "compliance_language_matches_count",
    "original_is_508_applicable", "original_applicability_explanation",
    # Solicitation-level
    "document_type", "solicitation_primary_purpose", "consistency_score",
    "total_files_in_solicitation", "ict_complexity", "accessibility_risk_level",
    "confidence_level", "hardware_component", "software_component",
    "vendor_responsibility_level", "specific_508_standards_applicable",
    "recommended_overall_applicability", "conflict_resolution_notes",
    "applicable_ict_types_detailed", "ict_explanation_detailed",
    "compliance_explanation_detailed", "applicability_explanation_detailed",
    "recommendations_detailed", "key_standards_matched_detailed",
    "analysis_completeness", "text_quality_score", "analysis_version",
    # Match quality
    "match_quality_score", "chunk_relevance_category", "chunk_relevance_confidence",
    "is_meaningful_match", "llm_validation_reasoning", "false_positive_likelihood",
    # Similarity
    "base_similarity_score", "enhanced_similarity_score", "similarity_boost_factor",
    "explicit_accessibility_mention", "accessibility_terms_found",
    "compliance_language_detected",
    # Standard classification
    "matched_standard_category", "specific_508_section", "wcag_level_mentioned",
    "compliance_relationship_type",
    # Explanations
    "explanation_quality_score", "explanation_category", "compliance_implication",
    "vendor_responsibility_level_detailed",
    # False positive
    "false_positive_pattern_matched", "kaspersky_clause_detected",
    "admin_language_detected", "contract_boilerplate_detected",
    # Context scoring
    "document_section_weight", "ict_relevance_score", "navy_parts_indicator_score",
    "cots_context_adjustment",
    # Processing
    "chunk_processing_time_ms", "total_chunks_processed", "chunks_filtered_out",
    "filtering_efficiency_ratio",
    # Aggregated
    "average_match_quality", "high_quality_matches_count", "meaningful_matches_ratio",
    "false_positive_matches_filtered", "explicit_mentions_count",
    "compliance_language_count", "average_ict_relevance", "processing_time_ms",
    "overall_compliance_score", "compliance_confidence", "compliance_assessment",
    # Solicitation AI summary
    "solicitation_applicable", "solicitation_compliant", "conflicts_detected",
    "conflict_resolution_summary", "procurement_type", "procurement_complexity",
    "primary_ict_types", "has_cots_products", "explicit_508_coverage",
    "solicitation_explanation", "key_findings", "priority_recommendations",
    "vendor_responsibilities", "file_consistency_assessment", "overall_risk_level",
    "recommended_actions",
    # Match details
    "match_index", "chunk_text", "matched_standard", "similarity_score",
    "match_explanation", "has_explicit_mention_in_chunk", "url",
]


def _init_csv(csv_path: str):
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    f = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    return f, writer


def _build_file_base_row(analysis: Dict, solicitation_id: str) -> Dict:
    """Build the base CSV row from a single file analysis report."""
    matches = analysis.get("top_matches", [])
    stats = analysis.get("vector_processing_stats", {})

    return {
        "row_type": "file_analysis",
        "solicitation_id": solicitation_id,
        "file_name": analysis.get("file_name", ""),
        "file_path": analysis.get("path", ""),
        "file_size_mb": analysis.get("file_size_mb", ""),
        "modification_date": analysis.get("modification_date", ""),
        "is_508_applicable": analysis.get("is_508_applicable", False),
        "confidence_score": analysis.get("confidence_score", 0),
        "is_compliant": analysis.get("includes_508", False),
        "has_explicit_508_mention": analysis.get("has_explicit_508_mention", False),
        "matches_found": analysis.get("matches_found", 0),
        "match_strength": analysis.get("match_strength", ""),
        "vector_match_strength": analysis.get("match_strength", ""),
        "is_discussing_508": analysis.get("is_discussing_508", False),
        "is_physical_only": analysis.get("is_physical_only", False),
        "key_standards_matched": ", ".join(analysis.get("key_eit_indicators", [])),
        "applicable_ict_types": ", ".join(analysis.get("applicable_ict_types", [])),
        "ict_explanation": analysis.get("ict_explanation", ""),
        "applicability_explanation": analysis.get("applicability_explanation", ""),
        "compliance_explanation": analysis.get("inclusion_explanation", ""),
        "recommendations": "",
        "website_source": analysis.get("website_source", ""),
        "is_cots_product": analysis.get("is_cots_product", False),
        "alternative_accessibility_regs": ", ".join(analysis.get("alternative_regs_found", [])),
        "false_positives_filtered": ", ".join(analysis.get("false_positives_filtered", [])),
        # Conflict resolution
        "compliance_decision_reasoning": analysis.get("decision_reasoning", ""),
        "meaningful_matches_count": analysis.get("meaningful_matches", 0),
        "high_quality_meaningful_matches_count": analysis.get("high_quality_matches_count", 0),
        "explicit_accessibility_matches_count": analysis.get("explicit_mentions_count", 0),
        "compliance_language_matches_count": analysis.get("compliance_language_count", 0),
        # Solicitation-level
        "total_files_in_solicitation": analysis.get("total_files_in_solicitation", 1),
        "hardware_component": analysis.get("hardware_component", "No"),
        "software_component": analysis.get("software_component", "No"),
        "applicable_ict_types_detailed": ", ".join(analysis.get("applicable_ict_types", [])),
        "ict_explanation_detailed": analysis.get("ict_explanation", ""),
        "compliance_explanation_detailed": analysis.get("inclusion_explanation", ""),
        "applicability_explanation_detailed": analysis.get("applicability_explanation", ""),
        "key_standards_matched_detailed": ", ".join(analysis.get("key_eit_indicators", [])),
        "analysis_version": "4.1_bm25_ml",
        # Context scoring
        "document_section_weight": analysis.get("document_section_weight", ""),
        "ict_relevance_score": analysis.get("ict_relevance_score", ""),
        "navy_parts_indicator_score": analysis.get("navy_parts_indicator_score", ""),
        "cots_context_adjustment": analysis.get("cots_context_adjustment", ""),
        # Processing
        "total_chunks_processed": stats.get("total_chunks_processed", ""),
        "chunks_filtered_out": stats.get("chunks_filtered_out", ""),
        "filtering_efficiency_ratio": stats.get("filtering_efficiency_ratio", ""),
        "processing_time_ms": analysis.get("total_pipeline_duration_ms", ""),
        # Aggregated
        "average_match_quality": analysis.get("average_match_quality", ""),
        "high_quality_matches_count": analysis.get("high_quality_matches_count", ""),
        "meaningful_matches_ratio": analysis.get("meaningful_matches_ratio", ""),
        "false_positive_matches_filtered": analysis.get("false_positive_matches_filtered", ""),
        "explicit_mentions_count": analysis.get("explicit_mentions_count", ""),
        "compliance_language_count": analysis.get("compliance_language_count", ""),
        "overall_compliance_score": analysis.get("compliance_overall_score", ""),
        "compliance_confidence": analysis.get("compliance_confidence", ""),
        "compliance_assessment": analysis.get("compliance_assessment", ""),
    }


def _get_match_fields(match: Dict) -> Dict:
    """Extract per-match fields for CSV row."""
    return {
        "match_index": match.get("chunk_index", ""),
        "chunk_text": match.get("chunk_text", ""),
        "matched_standard": match.get("matched_standard", ""),
        "similarity_score": match.get("similarity_score", ""),
        "match_quality_score": match.get("match_quality_score", ""),
        "chunk_relevance_category": match.get("chunk_relevance_category", ""),
        "chunk_relevance_confidence": match.get("chunk_relevance_confidence", ""),
        "is_meaningful_match": match.get("is_meaningful_match", ""),
        "false_positive_likelihood": match.get("false_positive_likelihood", ""),
        "base_similarity_score": match.get("base_similarity_score", ""),
        "enhanced_similarity_score": match.get("enhanced_similarity_score", ""),
        "similarity_boost_factor": match.get("similarity_boost_factor", ""),
        "explicit_accessibility_mention": match.get("explicit_accessibility_mention", ""),
        "accessibility_terms_found": match.get("accessibility_terms_found", ""),
        "compliance_language_detected": match.get("compliance_language_detected", ""),
        "matched_standard_category": match.get("matched_standard_category", ""),
        "specific_508_section": match.get("specific_508_section", ""),
        "wcag_level_mentioned": match.get("wcag_level_mentioned", ""),
        "compliance_relationship_type": match.get("compliance_relationship_type", ""),
        "explanation_quality_score": match.get("explanation_quality_score", ""),
        "explanation_category": match.get("explanation_category", ""),
        "compliance_implication": match.get("compliance_implication", ""),
        "vendor_responsibility_level_detailed": match.get("vendor_responsibility_level", ""),
        "false_positive_pattern_matched": match.get("false_positive_pattern_matched", ""),
        "kaspersky_clause_detected": match.get("kaspersky_clause_detected", ""),
        "admin_language_detected": match.get("admin_language_detected", ""),
        "contract_boilerplate_detected": match.get("contract_boilerplate_detected", ""),
    }


def _write_solicitation_csv(writer, result: Dict):
    """Write all rows for a solicitation to CSV."""
    sol_id = result.get("solicitation_id", "")
    summary = result.get("summary", {})
    analyses = result.get("individual_analyses", [])

    for analysis in analyses:
        base = _build_file_base_row(analysis, sol_id)
        matches = analysis.get("top_matches", [])

        if not matches:
            writer.writerow(base)
        else:
            for match in matches:
                row = base.copy()
                row.update(_get_match_fields(match))
                writer.writerow(row)

    # Write solicitation summary row
    if summary:
        summary_row = {
            "row_type": "solicitation_summary",
            "solicitation_id": sol_id,
            "solicitation_applicable": summary.get("solicitation_applicable", ""),
            "solicitation_compliant": summary.get("solicitation_includes_508", ""),
            "conflicts_detected": summary.get("conflicts_detected", ""),
            "conflict_resolution_summary": summary.get("conflict_resolution_summary", ""),
            "procurement_type": summary.get("procurement_type", ""),
            "procurement_complexity": summary.get("procurement_complexity", ""),
            "primary_ict_types": str(summary.get("primary_ict_types", [])),
            "has_cots_products": summary.get("has_cots_products", ""),
            "explicit_508_coverage": summary.get("explicit_508_coverage", ""),
            "solicitation_explanation": summary.get("solicitation_explanation", ""),
            "key_findings": str(summary.get("key_findings", [])),
            "priority_recommendations": str(summary.get("priority_recommendations", [])),
            "vendor_responsibilities": str(summary.get("vendor_responsibilities", [])),
            "file_consistency_assessment": summary.get("file_consistency_assessment", ""),
            "overall_risk_level": summary.get("overall_risk_level", ""),
            "recommended_actions": str(summary.get("recommended_actions", [])),
            "total_files_in_solicitation": result.get("stats", {}).get("total_files", ""),
        }
        writer.writerow(summary_row)


# ── Database helpers ──────────────────────────────────────────────────

def _write_to_database(db_writer, result: Dict, metadata: Dict = None):
    """Write solicitation result to PostgreSQL via RAGDataWriter."""
    sol_id = result.get("solicitation_id", "")
    analyses = result.get("individual_analyses", [])
    summary = result.get("summary", {})

    if not analyses:
        return

    # Map summary fields to what RAGDataWriter expects
    ai_summary = {
        "solicitation_applicable": summary.get("solicitation_applicable",
                                                result["determination"].get("is_508_applicable", False)),
        "solicitation_compliant": summary.get("solicitation_includes_508",
                                               result["determination"].get("includes_508", False)),
        "conflicts_detected": summary.get("conflicts_detected", False),
        "conflict_resolution_summary": summary.get("conflict_resolution_summary", ""),
        "procurement_type": summary.get("procurement_type", ""),
        "procurement_complexity": summary.get("procurement_complexity", "Medium"),
        "primary_ict_types": summary.get("primary_ict_types", []),
        "has_cots_products": summary.get("has_cots_products", False),
        "explicit_508_coverage": summary.get("explicit_508_coverage", False),
        "solicitation_explanation": summary.get("solicitation_explanation", ""),
        "key_findings": summary.get("key_findings", []),
        "priority_recommendations": summary.get("priority_recommendations", []),
        "vendor_responsibilities": summary.get("vendor_responsibilities", []),
        "file_consistency_assessment": summary.get("file_consistency_assessment", ""),
        "overall_risk_level": summary.get("overall_risk_level", "Medium"),
        "recommended_actions": summary.get("recommended_actions", []),
        # New summary fields
        "solicitation_summary": summary.get("solicitation_summary", ""),
        "procurement_description": summary.get("procurement_description", ""),
        # LLM explanation of the BM25 determination (why included / not included)
        "determination_summary": result.get("determination_summary",
                                             summary.get("determination_summary", "")),
    }

    # Add v4 BM25 + ML prediction if available (this is the new Section 508 model)
    v4 = result.get("v4_prediction") or {}
    setfit = result.get("setfit_prediction", {})
    if v4:
        ai_summary["setfit_compliant"] = v4.get("includes_508", False)
        ai_summary["setfit_confidence"] = v4.get("probability", 0)
        ai_summary["setfit_signal_text"] = ""
        ai_summary["prediction_source"] = "bm25_ml_model"
        # New v4 fields surfaced at the solicitation level
        ai_summary["bm25_prediction"] = v4.get("prediction", "")
        ai_summary["bm25_probability"] = v4.get("probability", 0)
        ai_summary["bm25_source"] = v4.get("source", "")
    elif setfit:
        ai_summary["setfit_compliant"] = setfit.get("includes_508", False)
        ai_summary["setfit_confidence"] = setfit.get("confidence", 0)
        ai_summary["setfit_signal_text"] = setfit.get("signal_text", "")
        ai_summary["prediction_source"] = setfit.get("prediction_source", "sklearn_legacy")

    # Map individual analyses to what RAGDataWriter expects
    mapped_analyses = []
    for a in analyses:
        mapped = dict(a)
        # Ensure old field names exist for backward compat
        mapped.setdefault("is_compliant", a.get("includes_508", False))
        mapped.setdefault("compliance_explanation", a.get("inclusion_explanation", ""))
        mapped.setdefault("recommendations", [])
        mapped.setdefault("key_standards", a.get("key_eit_indicators", []))
        mapped.setdefault("matches", a.get("top_matches", []))
        mapped.setdefault("ict_analysis", {"ict_types": a.get("ict_types", {})})
        mapped.setdefault("file_quality_metrics", {
            "average_match_quality": a.get("average_match_quality", 0),
            "high_quality_matches_count": a.get("high_quality_matches_count", 0),
            "meaningful_matches_ratio": a.get("meaningful_matches_ratio", 0),
            "false_positive_matches_filtered": a.get("false_positive_matches_filtered", 0),
            "explicit_mentions_count": a.get("explicit_mentions_count", 0),
            "compliance_language_count": a.get("compliance_language_count", 0),
        })
        mapped.setdefault("processing_stats", a.get("vector_processing_stats", {}))
        mapped.setdefault("overall_compliance_score", {
            "overall_score": a.get("compliance_overall_score", 0),
            "confidence": a.get("compliance_confidence", "low"),
            "assessment": a.get("compliance_assessment", ""),
        })
        mapped_analyses.append(mapped)

    db_writer.store_solicitation_analysis(
        solicitation_id=sol_id,
        individual_analyses=mapped_analyses,
        ai_summary=ai_summary,
        metadata=metadata,
    )
    logger.info(f"✅ DB: Stored solicitation {sol_id}")
    logger.info(f"   AI Summary: applicable={ai_summary.get('solicitation_applicable')}, "
                f"compliant={ai_summary.get('solicitation_compliant')}, "
                f"risk={ai_summary.get('overall_risk_level')}, "
                f"findings={len(ai_summary.get('key_findings', []))}, "
                f"explanation={ai_summary.get('solicitation_explanation', '')[:100]}")

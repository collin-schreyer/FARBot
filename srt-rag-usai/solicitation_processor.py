#!/usr/bin/env python3
"""
Solicitation Processor — Multi-file analysis for a single solicitation.

A solicitation folder contains multiple files (PDFs, DOCX, etc.).
This module:
  1. Runs pipeline.analyze_file() on each file
  2. Applies the key rule: ONE meaningful 508 reference in ANY file = solicitation includes 508
  3. Generates a solicitation-level AI summary
  4. Returns the full result ready for DB insert and CSV export
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from bedrock_adapter import BedrockAdapter
from pipeline import analyze_file

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".xlsx", ".xls", ".xlsm"}


def find_files(folder: str) -> List[Path]:
    """Find all supported files in a solicitation folder."""
    folder_path = Path(folder)
    files = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(folder_path.glob(f"**/*{ext}"))
    return sorted(files)


def process_solicitation(
    folder_path: str,
    client: Optional[BedrockAdapter] = None,
    standards_path: str = None,
    embed_model: str = "cohere_english_v3",
    on_file: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    """
    Process all files in a solicitation folder.

    Args:
        folder_path: Path to solicitation folder containing attachments
        client: BedrockAdapter instance (created if None)
        standards_path: Path to 508_standards.txt
        embed_model: Embedding model name
        on_file: Optional callback(file_name, index, total) for progress

    Returns:
        dict with keys:
          - solicitation_id: extracted from folder name
          - individual_analyses: list of per-file report dicts (77+ fields each)
          - summary: solicitation-level AI summary
          - determination: final solicitation-level determination
          - stats: aggregate statistics
    """
    if client is None:
        client = BedrockAdapter()

    if standards_path is None:
        standards_path = str(Path(__file__).parent / "data" / "508_standards.txt")

    folder = Path(folder_path)
    solicitation_id = folder.name.replace("_attachments", "")
    logger.info(f"=== Processing Solicitation: {solicitation_id} ===")

    files = find_files(folder_path)
    if not files:
        logger.warning(f"No supported files found in {folder_path}")
        return {
            "solicitation_id": solicitation_id,
            "individual_analyses": [],
            "summary": {},
            "determination": {"includes_508": False, "reason": "No files found"},
            "stats": {"total_files": 0},
        }

    logger.info(f"Found {len(files)} files to process")

    # ── Analyze each file ─────────────────────────────────────────────
    individual_analyses = []
    all_stages = []
    t0 = time.time()
    FILE_TIMEOUT = 300  # 5 minutes max per file

    for i, file_path in enumerate(files):
        logger.info(f"  [{i+1}/{len(files)}] {file_path.name}")
        if on_file:
            on_file(file_path.name, i, len(files))

        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    analyze_file,
                    str(file_path),
                    client=client,
                    standards_path=standards_path,
                    embed_model=embed_model,
                )
                try:
                    result = future.result(timeout=FILE_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    logger.error(f"    ⏰ TIMEOUT after {FILE_TIMEOUT}s for {file_path.name} — skipping")
                    individual_analyses.append({
                        "file_name": file_path.name,
                        "path": str(file_path),
                        "solicitation_id": solicitation_id,
                        "is_508_applicable": False,
                        "error": f"Timeout after {FILE_TIMEOUT}s",
                    })
                    continue
            report = result.get("report", {})
            if report:
                report["path"] = str(file_path)
                report["solicitation_id"] = solicitation_id
                report["total_files_in_solicitation"] = len(files)
                individual_analyses.append(report)
                all_stages.extend(result.get("stages", []))
                logger.info(f"    ✅ applicable={report.get('is_508_applicable')}, "
                            f"includes_508={report.get('includes_508')}, "
                            f"matches={report.get('matches_found')}")
            else:
                logger.warning(f"    ❌ Empty report for {file_path.name}")
        except Exception as e:
            logger.error(f"    ❌ Error: {e}")
            individual_analyses.append({
                "file_name": file_path.name,
                "path": str(file_path),
                "solicitation_id": solicitation_id,
                "is_508_applicable": False,
                "includes_508": False,
                "error": str(e),
            })

    # ── Solicitation-level determination ──────────────────────────────
    # Key rule: ONE meaningful 508 reference in ANY file = solicitation includes 508
    any_applicable = any(a.get("is_508_applicable", False) for a in individual_analyses)
    any_includes_508 = any(
        a.get("includes_508") is True or
        a.get("has_explicit_508_mention") is True or
        a.get("explicit_mentions_count", 0) > 0
        for a in individual_analyses
    )
    any_meaningful_match = any(
        a.get("meaningful_matches", 0) > 0 or
        a.get("high_quality_matches_count", 0) > 0
        for a in individual_analyses
    )

    total_matches = sum(a.get("matches_found", 0) for a in individual_analyses)
    applicable_count = sum(1 for a in individual_analyses if a.get("is_508_applicable"))
    includes_count = sum(1 for a in individual_analyses if a.get("includes_508") is True)

    determination = {
        "is_508_applicable": any_applicable,
        "includes_508": any_includes_508,
        "any_meaningful_match": any_meaningful_match,
        "applicable_files": applicable_count,
        "files_with_508": includes_count,
        "total_files": len(files),
        "total_matches": total_matches,
    }

    # ── AI Summary (single LLM call across all files) ─────────────────
    summary = {}
    if individual_analyses:
        try:
            summary = _generate_solicitation_summary(
                client, solicitation_id, individual_analyses, determination
            )
            determination["ai_determination"] = summary.get("final_determination", "")
            determination["risk_level"] = summary.get("overall_risk_level", "Medium")
        except Exception as e:
            logger.error(f"AI summary failed: {e}")
            summary = {"error": str(e)}

    elapsed = round((time.time() - t0) * 1000)
    stats = {
        "total_files": len(files),
        "files_analyzed": len(individual_analyses),
        "applicable_files": applicable_count,
        "files_with_508": includes_count,
        "total_matches": total_matches,
        "processing_time_ms": elapsed,
        "llm_calls": client._call_count,
        "total_tokens": client._total_tokens,
    }

    logger.info(f"=== Solicitation {solicitation_id} complete: "
                f"{stats['files_analyzed']} files, {applicable_count} applicable, "
                f"{includes_count} include 508, {total_matches} matches, "
                f"{elapsed}ms ===")

    return {
        "solicitation_id": solicitation_id,
        "individual_analyses": individual_analyses,
        "summary": summary,
        "determination": determination,
        "stats": stats,
    }


def _generate_solicitation_summary(
    client: BedrockAdapter,
    solicitation_id: str,
    analyses: List[Dict],
    determination: Dict,
) -> Dict:
    """Generate AI solicitation-level summary — informational only, no compliance decisions."""
    # Build compact summary of each file for the LLM
    file_summaries = []
    for a in analyses[:15]:
        file_summaries.append({
            "file": a.get("file_name", ""),
            "applicable": a.get("is_508_applicable", False),
            "document_summary": a.get("document_summary", ""),
            "document_type": a.get("document_type", ""),
            "matches": a.get("matches_found", 0),
            "meaningful": a.get("meaningful_matches", 0),
            "explicit_mention": a.get("has_explicit_508_mention", False),
            "ict_types": a.get("applicable_ict_types", []),
            "section_508_references": a.get("section_508_references", []),
        })

    system = """You are summarizing a federal solicitation package across multiple files.

Describe:
1. What this solicitation is for (the overall procurement purpose)
2. What types of ICT are being procured across all files
3. A brief description of what each file contains
4. Whether any files reference Section 508 accessibility standards (factual observation)
5. The primary ICT types involved

Do NOT make compliance determinations. Do NOT recommend actions. 
Compliance is determined by a separate ML model — your job is informational context only.

Return ONLY valid JSON:
{
  "solicitation_summary": "2-3 sentence overview of what this solicitation is about",
  "procurement_description": "A detailed description of what exactly is being procured",
  "procurement_type": "Services/Products/Mixed",
  "procurement_complexity": "Simple/Medium/Complex",
  "primary_ict_types": ["list of ICT types being procured"],
  "has_cots_products": true/false,
  "file_descriptions": [{"file": "name", "description": "what this file contains"}],
  "section_508_observations": "factual note on whether 508 is mentioned in any files",
  "key_findings": ["factual finding 1", ...],
  "solicitation_explanation": "A complete blanket review and explanation of why Section 508 does or does not apply to this solicitation as a whole"
}"""

    user = (f"Solicitation: {solicitation_id}\n"
            f"Stats: {json.dumps(determination, default=str)}\n\n"
            f"Per-file analyses:\n{json.dumps(file_summaries, indent=2, default=str)}")

    result = client._json_chat(system, user, temperature=0.0,
                                stage_name="solicitation_summary")
    return result or {
        "solicitation_summary": "Summary generation failed",
        "solicitation_explanation": "",
        "key_findings": [],
    }

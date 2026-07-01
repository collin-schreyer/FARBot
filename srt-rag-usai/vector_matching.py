#!/usr/bin/env python3
"""
Vector similarity matching using pre-built FAISS index with Cohere embeddings.
"""

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Module-level cache
_cached_db = None
_cached_chunks = None
_cached_text = None


def build_faiss_index(standards_path: str, embed_model: str = "cohere_english_v3"):
    """Load pre-built FAISS index or build on-the-fly."""
    global _cached_db, _cached_chunks, _cached_text

    if _cached_db is not None:
        logger.info("[FAISS] Using cached index.")
        return _cached_db, _cached_chunks, _cached_text

    try:
        from langchain_community.vectorstores import FAISS
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        standards_text = Path(standards_path).read_text(encoding="utf-8", errors="ignore")
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.create_documents([standards_text])
        chunks = [d.page_content for d in docs]

        if not chunks:
            return None, [], standards_text

        # Bedrock Cohere English v3 embeddings — same model the prebuilt 508
        # FAISS index was built with, so query vectors stay compatible.
        from bedrock_adapter import BedrockLCEmbeddings
        embeddings = BedrockLCEmbeddings()

        # Fast path: load pre-built index
        db_path = str(Path(__file__).parent / "data" / "faiss_index")
        if os.path.exists(db_path):
            logger.info("[FAISS] Loading pre-built index from disk.")
            db = FAISS.load_local(db_path, embeddings, allow_dangerous_deserialization=True)
            _cached_db = db
            _cached_chunks = chunks
            _cached_text = standards_text
            return db, chunks, standards_text

        # Slow path: build on-the-fly
        logger.info(f"[FAISS] Building index from {len(chunks)} chunks...")
        valid_chunks, valid_embeddings = [], []
        for chunk in chunks:
            if not chunk.strip():
                continue
            emb = embeddings.embed_documents([chunk])
            if emb and emb[0]:
                valid_chunks.append(chunk)
                valid_embeddings.append(emb[0])

        if not valid_chunks:
            return None, [], standards_text

        pairs = list(zip(valid_chunks, valid_embeddings))
        db = FAISS.from_embeddings(pairs, embeddings)
        db.save_local(db_path)

        _cached_db = db
        _cached_chunks = chunks
        _cached_text = standards_text
        return db, chunks, standards_text

    except Exception as e:
        logger.warning(f"FAISS build failed: {e}")
        standards_text = Path(standards_path).read_text(encoding="utf-8", errors="ignore") if Path(standards_path).exists() else ""
        return None, [], standards_text


def run_vector_matching(text: str, db, chunks: list, client, threshold: float = 0.40) -> Dict[str, Any]:
    """Run vector similarity search against 508 standards. Single LLM call for all matches."""
    if db is None:
        return {"matches_found": 0, "matches": [], "match_strength": "Low",
                "explicit_mentions": 0, "processing_stats": {},
                "llm_analysis": "FAISS index not available."}

    TOP_N = 10
    MAX_CHUNKS = 75
    FILE_TIMEOUT = 180  # 3 minute max per file for vector matching

    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.create_documents([text])
        text_chunks = [d.page_content for d in docs]
        logger.info(f"[VectorMatch] {len(text_chunks)} chunks, processing up to {MAX_CHUNKS}...")

        start = time.time()
        raw_matches = []
        errors = 0
        for i, chunk in enumerate(text_chunks[:MAX_CHUNKS]):
            if time.time() - start > FILE_TIMEOUT:
                logger.warning(f"[VectorMatch] Timeout after {i} chunks ({FILE_TIMEOUT}s)")
                break
            try:
                results = db.similarity_search_with_score(chunk, k=1)
                for doc, score in results:
                    similarity = max(0.0, 1.0 - score / 2.0)
                    if similarity >= threshold:
                        raw_matches.append({
                            "chunk_index": i,
                            "chunk_text": chunk[:300],
                            "matched_standard": doc.page_content[:300],
                            "similarity_score": float(round(similarity, 4)),
                            "l2_distance": float(round(score, 4)),
                            "full_chunk": chunk[:500],
                            "full_standard": doc.page_content[:500],
                        })
            except Exception as ex:
                errors += 1
                continue

        faiss_time = round((time.time() - start) * 1000)
        raw_matches.sort(key=lambda m: m["similarity_score"], reverse=True)
        top_matches = raw_matches[:TOP_N]

        # Single LLM call for all matches — get per-match meaningful verdict
        llm_analysis = ""
        llm_time = 0
        match_verdicts = {}
        if top_matches and client:
            match_summary = ""
            for idx, m in enumerate(top_matches):
                match_summary += (f"\n--- Match {idx+1} (sim: {m['similarity_score']}) ---\n"
                                  f"Solicitation text:\n{m['full_chunk']}\n\n"
                                  f"508 Standard text:\n{m['full_standard']}\n")
            try:
                llm_start = time.time()
                import json as _json
                verdict_result = client._json_chat(
                    system="""You are a Section 508 expert. For each match between solicitation text and a 508 standard, determine if the solicitation text is a MEANINGFUL reference to Section 508 accessibility.

A match IS meaningful if the solicitation text:
- Explicitly mentions "Section 508", "Rehabilitation Act" in the context of ICT accessibility
- References VPAT, ACR, WCAG, or accessibility conformance requirements
- Contains FAR clauses specifically about ICT accessibility (e.g., 52.239-70, HHSAR 352.239-73/74)
- Requires the vendor to make products/services accessible to people with disabilities

A match is NOT meaningful if the solicitation text:
- References "Equal Opportunity for Workers with Disabilities" (FAR 52.222-36) — this is about hiring, not product accessibility
- Contains generic FAR boilerplate about telecommunications equipment prohibitions (Kaspersky, Huawei bans)
- Just happens to use similar regulatory language but has nothing to do with accessibility
- References the Rehabilitation Act only in the context of employment discrimination (Section 503), not ICT accessibility (Section 508)

Return ONLY valid JSON:
{
  "matches": [
    {"match_number": 1, "is_meaningful": true/false, "reason": "brief reason"},
    ...
  ],
  "overall_includes_508": true/false,
  "summary": "1-2 sentence factual summary"
}""",
                    user=f"Analyze these {len(top_matches)} matches:\n{match_summary}",
                    model=client.cheap_model,
                    temperature=0.0,
                    stage_name="match_analysis",
                )
                llm_time = round((time.time() - llm_start) * 1000)

                if verdict_result:
                    llm_analysis = verdict_result.get("summary", "")
                    for v in verdict_result.get("matches", []):
                        num = v.get("match_number", 0)
                        match_verdicts[num] = {
                            "is_meaningful": v.get("is_meaningful", False),
                            "reason": v.get("reason", ""),
                        }
                    # Store the overall verdict for use by the pipeline
                    if "overall_includes_508" in verdict_result:
                        llm_analysis = _json.dumps(verdict_result)
            except Exception as ex:
                llm_analysis = f"LLM analysis failed: {ex}"
        elif not top_matches:
            llm_analysis = "No matches found above threshold."

        # Apply LLM verdicts to top matches
        for idx, m in enumerate(top_matches):
            verdict = match_verdicts.get(idx + 1, {})
            m["llm_meaningful"] = verdict.get("is_meaningful", False)
            m["llm_reason"] = verdict.get("reason", "")

        matches = [{k: v for k, v in m.items() if k not in ("full_chunk", "full_standard")}
                   for m in raw_matches]

        return {
            "matches_found": len(matches),
            "matches": matches,
            "match_strength": "High" if len(matches) >= 3 else "Medium" if len(matches) >= 1 else "Low",
            "explicit_mentions": sum(1 for m in top_matches if m["similarity_score"] >= 0.50),
            "processing_stats": {
                "total_chunks_processed": min(len(text_chunks), MAX_CHUNKS),
                "matches_above_threshold": len(matches),
                "embedding_errors": errors,
                "threshold_used": threshold,
                "faiss_time_ms": faiss_time,
                "llm_time_ms": llm_time,
                "chunks_filtered_out": max(0, len(text_chunks) - MAX_CHUNKS),
                "filtering_efficiency_ratio": round(len(matches) / max(min(len(text_chunks), MAX_CHUNKS), 1), 4),
            },
            "llm_analysis": llm_analysis,
        }
    except Exception as e:
        logger.error(f"Vector matching error: {e}")
        return {"matches_found": 0, "matches": [], "match_strength": "Low",
                "explicit_mentions": 0, "processing_stats": {"error": str(e)},
                "llm_analysis": f"Error: {e}"}

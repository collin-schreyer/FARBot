#!/usr/bin/env python3
"""
RAG Database Writer for Section 508 Compliance Analysis
Comprehensive version that uses the full normalized schema with all 7 tables.

This module stores Section 508 analysis results in PostgreSQL using the complete
database schema with proper normalization instead of JSON blobs.
"""

import os
import json
import uuid
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2 import sql

logger = logging.getLogger(__name__)

class RAGDataWriter:
    """
    Comprehensive RAG database writer for Section 508 analysis results.
    Uses the full normalized schema with all 7 tables.
    """
    
    def __init__(self, connection_string: str = None):
        """
        Initialize RAG database writer.
        
        Args:
            connection_string: PostgreSQL connection string. If None, uses environment variables.
        """
        print("🗄️ RAG Database: Initializing comprehensive writer...")
        self.connection_string = connection_string or self._get_default_connection_string()
        self.connection = None
        print(f"🔗 RAG Database: Using connection to {self._mask_password(self.connection_string)}")
        self._connect()
        self._verify_schema_exists()
        print("✅ RAG Database: Ready for comprehensive data storage")
    
    def _get_default_connection_string(self) -> str:
        """Build connection string from environment variables with SRT database defaults."""
        # Check for full connection string first (set by run_daily.sh on cloud.gov)
        full_url = os.getenv('SECTION_508_DATABASE_URL') or os.getenv('DATABASE_URL')
        if full_url:
            # Fix postgres:// dialect for SQLAlchemy
            if full_url.startswith("postgres://"):
                full_url = full_url.replace("postgres://", "postgresql://", 1)
            print(f"🔧 RAG Database: Using connection URL from environment")
            return full_url
        
        host = os.getenv('RAG_DB_HOST', 'localhost')
        port = os.getenv('RAG_DB_PORT', '5432')
        database = os.getenv('RAG_DB_NAME', 'SRT')  # Use existing SRT database
        user = os.getenv('RAG_DB_USER', 'circleci')  # Use existing SRT user
        password = os.getenv('RAG_DB_PASSWORD', 'srtpass')  # Use existing SRT password
        
        print(f"🔧 RAG Database: Config - Host: {host}, Port: {port}, Database: {database}, User: {user}")
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    def _mask_password(self, connection_string: str) -> str:
        """Mask password in connection string for logging."""
        import re
        return re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', connection_string)
    
    def _connect(self):
        """Establish database connection."""
        try:
            print("🔌 RAG Database: Attempting connection...")
            self.connection = psycopg2.connect(self.connection_string)
            self.connection.autocommit = True
            print("✅ RAG Database: Connected successfully")
            logger.info("✅ Connected to RAG database")
        except Exception as e:
            print(f"❌ RAG Database: Connection failed - {e}")
            logger.error(f"Failed to connect to RAG database: {e}")
            raise
    
    def _verify_schema_exists(self):
        """Verify that the comprehensive schema exists."""
        print("📋 RAG Database: Verifying comprehensive schema...")
        
        expected_tables = [
            'rag-solicitations',
            'rag-documents', 
            'rag-document-ict-types',
            'rag-vector-matches',
            'rag-document-quality-metrics',
            'rag-website-sources',
            'rag-ict-types-reference'
        ]
        
        try:
            with self.connection.cursor() as cursor:
                for table in expected_tables:
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        )
                    """, (table,))
                    
                    exists = cursor.fetchone()[0]
                    if exists:
                        print(f"  ✅ Table '{table}' found")
                    else:
                        print(f"  ❌ Table '{table}' missing")
                        raise Exception(f"Required table '{table}' not found. Run setup_database.py first.")

                # Idempotent column migrations (safe to run every startup).
                # determination_summary: LLM explanation of the BM25 verdict.
                cursor.execute("""
                    ALTER TABLE "rag-solicitations"
                    ADD COLUMN IF NOT EXISTS determination_summary TEXT
                """)
                print("  ✅ Column 'rag-solicitations.determination_summary' ensured")

            print("✅ RAG Database: Comprehensive schema verified")
            
        except Exception as e:
            print(f"❌ RAG Database: Schema verification failed - {e}")
            logger.error(f"Failed to verify schema: {e}")
            raise
    
    def store_solicitation_analysis(
        self, 
        solicitation_id: str, 
        individual_analyses: List[Dict[str, Any]], 
        ai_summary: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store complete solicitation analysis using comprehensive normalized schema.
        
        Args:
            solicitation_id: Unique solicitation identifier
            individual_analyses: List of individual file analysis results
            ai_summary: Optional AI-generated solicitation summary
            metadata: Optional additional metadata
            
        Returns:
            str: UUID of stored solicitation record
        """
        try:
            # Validate input
            if not individual_analyses:
                print("❌ RAG Database: No individual analyses provided")
                raise ValueError("No individual analyses provided")
            
            print(f"💾 RAG Database: Storing solicitation '{solicitation_id}' with {len(individual_analyses)} files using comprehensive schema")
            logger.info(f"Storing solicitation {solicitation_id} with {len(individual_analyses)} files")
            
            # Calculate solicitation-level statistics
            total_files = len(individual_analyses)
            applicable_files = sum(1 for f in individual_analyses if self._safe_get(f, 'is_508_applicable', False))
            compliant_files = sum(1 for f in individual_analyses if 
                                self._safe_get(f, 'is_508_applicable', False) and 
                                self._safe_get(f, 'is_compliant', False))
            total_matches = sum(self._safe_get(f, 'matches_found', 0) for f in individual_analyses)
            
            print(f"📊 RAG Database: Stats - {total_files} total, {applicable_files} applicable, {compliant_files} compliant, {total_matches} matches")
            
            # Extract aggregate data
            website_sources = [self._safe_get(f, 'website_source', 'Unknown') for f in individual_analyses]
            primary_website = max(set(website_sources), key=website_sources.count) if website_sources else 'Unknown'
            
            # Calculate quality metrics
            quality_scores = [self._safe_get(f, 'file_quality_metrics', {}).get('average_match_quality', 0) for f in individual_analyses]
            avg_quality = sum(quality_scores) / max(len(quality_scores), 1)
            
            processing_times = [self._safe_get(f, 'processing_stats', {}).get('processing_time_ms', 0) for f in individual_analyses]
            total_processing_time = sum(processing_times)
            
            print(f"🌐 RAG Database: Primary website: {primary_website}, Avg quality: {avg_quality:.3f}")
            
            # Store solicitation record
            solicitation_uuid = str(uuid.uuid4())
            print(f"🆔 RAG Database: Generated UUID: {solicitation_uuid}")
            
            with self.connection.cursor() as cursor:
                print("💾 RAG Database: Inserting comprehensive solicitation record...")
                
                # Prepare AI summary fields
                ai_applicable = ai_summary.get('solicitation_applicable', False) if ai_summary else applicable_files > 0
                ai_compliant = ai_summary.get('solicitation_compliant', False) if ai_summary else compliant_files > 0
                ai_conflicts = ai_summary.get('conflicts_detected', False) if ai_summary else False
                
                cursor.execute("""
                    INSERT INTO "rag-solicitations" (
                        id, solicitation_number, title, agency, website_source,
                        procurement_type, procurement_complexity,
                        ai_applicable, ai_compliant, ai_conflicts_detected,
                        ai_conflict_resolution_summary, ai_procurement_type,
                        ai_primary_ict_types, ai_has_cots_products, ai_explicit_508_coverage,
                        ai_solicitation_explanation, ai_key_findings, ai_priority_recommendations,
                        ai_vendor_responsibilities, ai_file_consistency_assessment,
                        ai_overall_risk_level, ai_recommended_actions,
                        total_files, applicable_files, compliant_files, total_matches,
                        average_quality_score, processing_time_ms, analysis_version,
                        setfit_compliant, setfit_confidence, setfit_signal_text,
                        prediction_source, solicitation_summary, procurement_description,
                        bm25_prediction, bm25_probability, bm25_source,
                        bm25_avg_normalized_score, bm25_max_normalized_score,
                        determination_summary
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (solicitation_number) DO UPDATE SET
                        ai_applicable = EXCLUDED.ai_applicable,
                        ai_compliant = EXCLUDED.ai_compliant,
                        ai_conflicts_detected = EXCLUDED.ai_conflicts_detected,
                        ai_conflict_resolution_summary = EXCLUDED.ai_conflict_resolution_summary,
                        ai_procurement_type = EXCLUDED.ai_procurement_type,
                        ai_primary_ict_types = EXCLUDED.ai_primary_ict_types,
                        ai_has_cots_products = EXCLUDED.ai_has_cots_products,
                        ai_explicit_508_coverage = EXCLUDED.ai_explicit_508_coverage,
                        ai_solicitation_explanation = EXCLUDED.ai_solicitation_explanation,
                        ai_key_findings = EXCLUDED.ai_key_findings,
                        ai_priority_recommendations = EXCLUDED.ai_priority_recommendations,
                        ai_vendor_responsibilities = EXCLUDED.ai_vendor_responsibilities,
                        ai_file_consistency_assessment = EXCLUDED.ai_file_consistency_assessment,
                        ai_overall_risk_level = EXCLUDED.ai_overall_risk_level,
                        ai_recommended_actions = EXCLUDED.ai_recommended_actions,
                        total_files = EXCLUDED.total_files,
                        applicable_files = EXCLUDED.applicable_files,
                        compliant_files = EXCLUDED.compliant_files,
                        total_matches = EXCLUDED.total_matches,
                        average_quality_score = EXCLUDED.average_quality_score,
                        processing_time_ms = EXCLUDED.processing_time_ms,
                        analysis_version = EXCLUDED.analysis_version,
                        setfit_compliant = EXCLUDED.setfit_compliant,
                        setfit_confidence = EXCLUDED.setfit_confidence,
                        setfit_signal_text = EXCLUDED.setfit_signal_text,
                        prediction_source = EXCLUDED.prediction_source,
                        solicitation_summary = EXCLUDED.solicitation_summary,
                        procurement_description = EXCLUDED.procurement_description,
                        bm25_prediction = EXCLUDED.bm25_prediction,
                        bm25_probability = EXCLUDED.bm25_probability,
                        bm25_source = EXCLUDED.bm25_source,
                        bm25_avg_normalized_score = EXCLUDED.bm25_avg_normalized_score,
                        bm25_max_normalized_score = EXCLUDED.bm25_max_normalized_score,
                        determination_summary = EXCLUDED.determination_summary,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                """, (
                    solicitation_uuid, solicitation_id,
                    metadata.get('title', solicitation_id) if metadata else solicitation_id,
                    metadata.get('agency', 'Unknown') if metadata else 'Unknown',
                    primary_website,
                    ai_summary.get('procurement_type', 'Unknown') if ai_summary else 'Unknown',
                    ai_summary.get('procurement_complexity', 'Medium') if ai_summary else 'Medium',
                    ai_applicable, ai_compliant, ai_conflicts,
                    ai_summary.get('conflict_resolution_summary', '') if ai_summary else '',
                    ai_summary.get('procurement_type', '') if ai_summary else '',
                    ai_summary.get('primary_ict_types', []) if ai_summary else [],
                    ai_summary.get('has_cots_products', False) if ai_summary else any(self._safe_get(f, 'is_cots_product', False) for f in individual_analyses),
                    ai_summary.get('explicit_508_coverage', False) if ai_summary else any(self._safe_get(f, 'has_explicit_508_mention', False) for f in individual_analyses),
                    ai_summary.get('solicitation_explanation', '') if ai_summary else '',
                    ai_summary.get('key_findings', []) if ai_summary else [],
                    ai_summary.get('priority_recommendations', []) if ai_summary else [],
                    ai_summary.get('vendor_responsibilities', []) if ai_summary else [],
                    ai_summary.get('file_consistency_assessment', '') if ai_summary else '',
                    ai_summary.get('overall_risk_level', 'Medium') if ai_summary else 'Medium',
                    ai_summary.get('recommended_actions', []) if ai_summary else [],
                    total_files, applicable_files, compliant_files, total_matches,
                    self._convert_numpy_types(avg_quality), total_processing_time,
                    '4.1_bm25_ml',
                    ai_summary.get('setfit_compliant') if ai_summary else None,
                    ai_summary.get('setfit_confidence') if ai_summary else None,
                    ai_summary.get('setfit_signal_text', '')[:500] if ai_summary else '',
                    ai_summary.get('prediction_source', 'llm') if ai_summary else 'llm',
                    ai_summary.get('solicitation_summary', '') if ai_summary else '',
                    ai_summary.get('procurement_description', '') if ai_summary else '',
                    ai_summary.get('bm25_prediction', '') if ai_summary else '',
                    ai_summary.get('bm25_probability', 0) if ai_summary else 0,
                    ai_summary.get('bm25_source', '') if ai_summary else '',
                    self._safe_get_float([self._safe_get(a, 'bm25_normalized_score', 0) for a in individual_analyses], 'avg'),
                    self._safe_get_float([self._safe_get(a, 'bm25_normalized_score', 0) for a in individual_analyses], 'max'),
                    ai_summary.get('determination_summary', '') if ai_summary else '',
                ))
                
                result = cursor.fetchone()
                if result:
                    solicitation_uuid = str(result[0])
                    print("✅ RAG Database: Comprehensive solicitation record stored")

            # Delete any existing document rows (and their normalized children) for this
            # solicitation BEFORE inserting fresh ones. Without this, reprocessing a
            # solicitation appends a second set of "rag-documents" rows, which makes the
            # UI show duplicate file chips and stale bm25_prediction values. We delete the
            # children explicitly in case the FKs are not declared ON DELETE CASCADE.
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM "rag-vector-matches"
                    WHERE document_id IN (
                        SELECT id FROM "rag-documents" WHERE solicitation_id = %s
                    )
                """, (solicitation_uuid,))
                cursor.execute("""
                    DELETE FROM "rag-document-ict-types"
                    WHERE document_id IN (
                        SELECT id FROM "rag-documents" WHERE solicitation_id = %s
                    )
                """, (solicitation_uuid,))
                cursor.execute("""
                    DELETE FROM "rag-document-quality-metrics"
                    WHERE document_id IN (
                        SELECT id FROM "rag-documents" WHERE solicitation_id = %s
                    )
                """, (solicitation_uuid,))
                cursor.execute("""
                    DELETE FROM "rag-documents" WHERE solicitation_id = %s
                """, (solicitation_uuid,))
                print(f"🧹 RAG Database: Cleared existing document rows for solicitation {solicitation_uuid}")

            # Store individual document analyses with full normalization
            print(f"📄 RAG Database: Storing {len(individual_analyses)} comprehensive document analyses...")
            stored_documents = 0
            for i, analysis in enumerate(individual_analyses, 1):
                try:
                    file_name = self._safe_get(analysis, 'file_name', f'unknown_file_{i}')
                    print(f"  📄 Processing file {i}/{len(individual_analyses)}: {file_name}")
                    doc_uuid = self._store_comprehensive_document_analysis(solicitation_uuid, analysis)
                    if doc_uuid:
                        stored_documents += 1
                        print(f"  ✅ Stored comprehensive: {file_name}")
                    else:
                        print(f"  ❌ Failed: {file_name}")
                except Exception as e:
                    file_name = self._safe_get(analysis, 'file_name', 'unknown')
                    print(f"  ❌ Error storing {file_name}: {e}")
                    logger.error(f"Failed to store document analysis for {file_name}: {e}")
                    continue
            
            print(f"✅ RAG Database: Stored comprehensive solicitation {solicitation_id}: {stored_documents}/{total_files} documents")
            logger.info(f"✅ Stored comprehensive solicitation {solicitation_id}: {stored_documents}/{total_files} documents")
            return solicitation_uuid
            
        except Exception as e:
            print(f"❌ RAG Database: Failed to store comprehensive solicitation analysis: {e}")
            logger.error(f"Failed to store solicitation analysis: {e}")
            logger.error(traceback.format_exc())
            raise
        
    def _store_comprehensive_document_analysis(self, solicitation_uuid: str, analysis: Dict[str, Any]) -> Optional[str]:
        """Store individual document analysis using comprehensive normalized schema."""
        try:
            # Safely extract document information
            file_name = self._safe_get(analysis, 'file_name', 'unknown_file')
            file_path = self._safe_get(analysis, 'path', '')
            file_size_mb = self._safe_get(analysis, 'file_size_mb', 0.0)
            
            print(f"    🔍 RAG Database: Processing comprehensive analysis for {file_name}")
            
            # Parse modification date
            mod_date_str = self._safe_get(analysis, 'modification_date', '')
            modification_date = None
            if mod_date_str:
                try:
                    modification_date = datetime.fromisoformat(mod_date_str.replace('Z', '+00:00'))
                except:
                    modification_date = None
            
            # Extract comprehensive analysis results
            is_508_applicable = self._safe_get(analysis, 'is_508_applicable', False)
            is_compliant = self._safe_get(analysis, 'is_compliant', False)
            confidence_score = self._safe_get(analysis, 'confidence_score', 0)
            has_explicit_mention = self._safe_get(analysis, 'has_explicit_508_mention', False)
            
            # Extract explanations
            applicability_explanation = self._safe_get(analysis, 'applicability_explanation', '')
            compliance_explanation = self._safe_get(analysis, 'compliance_explanation', '')
            ict_explanation = self._safe_get(analysis, 'ict_explanation', '')
            
            # Extract context flags
            is_physical_only = self._safe_get(analysis, 'is_physical_only', False)
            is_discussing_508 = self._safe_get(analysis, 'is_discussing_508', False)
            is_cots_product = self._safe_get(analysis, 'is_cots_product', False)
            
            # Extract ICT analysis for hardware/software components
            ict_analysis = self._safe_get(analysis, 'ict_analysis', {})
            ict_types = ict_analysis.get('ict_types', {})
            hardware_component = ict_types.get('Hardware', False)
            software_component = ict_types.get('Software', False)
            
            # Extract arrays
            key_standards = self._safe_get(analysis, 'key_standards', [])
            recommendations = self._safe_get(analysis, 'recommendations', [])
            alternative_regs = self._safe_get(analysis, 'alternative_accessibility_regs', [])
            false_positives = self._safe_get(analysis, 'false_positives_filtered', [])
            
            # Extract quality and processing metrics
            matches_found = self._safe_get(analysis, 'matches_found', 0)
            match_strength = self._safe_get(analysis, 'match_strength', 'Low')
            vector_match_strength = self._safe_get(analysis, 'vector_match_strength', 'Low')
            
            # Extract conflict resolution details
            compliance_details = self._safe_get(analysis, 'compliance_details', {})

            # Extract v4 BM25 + ML model fields (per-file from pipeline.analyze_file)
            bm25_raw_score = self._safe_get(analysis, 'bm25_raw_score', None)
            bm25_normalized_score = self._safe_get(analysis, 'bm25_normalized_score', None)
            bm25_bucket = self._safe_get(analysis, 'bm25_bucket', '') or ''
            bm25_keyword_hits = self._safe_get(analysis, 'bm25_keyword_hits', {}) or {}
            bm25_prediction = self._safe_get(analysis, 'bm25_prediction', '') or ''
            bm25_probability = self._safe_get(analysis, 'bm25_probability', None)
            bm25_source = self._safe_get(analysis, 'bm25_source', '') or ''
            
            print(f"    📊 RAG Database: {file_name} - Applicable: {is_508_applicable}, Compliant: {is_compliant}, Matches: {matches_found}")
            
            # Store comprehensive document record
            document_uuid = str(uuid.uuid4())
            
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO "rag-documents" (
                        id, solicitation_id, file_name, file_path, file_size_mb,
                        modification_date, document_type,
                        is_508_applicable, confidence_score, is_compliant, has_explicit_508_mention,
                        applicability_explanation, compliance_explanation, ict_explanation,
                        is_physical_only, is_discussing_508, is_cots_product,
                        hardware_component, software_component,
                        key_standards, recommendations, alternative_accessibility_regs, false_positives_filtered,
                        matches_found, match_strength, vector_match_strength,
                        accessibility_risk_level, vendor_responsibility_level,
                        applicability_conflict_detected, applicability_resolution_method, applicability_override_reason,
                        compliance_conflict_detected, compliance_resolution_method, compliance_decision_reasoning,
                        analysis_completeness, text_quality_score, consistency_score, analysis_version,
                        bm25_raw_score, bm25_normalized_score, bm25_bucket, bm25_keyword_hits,
                        bm25_prediction, bm25_probability, bm25_source
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    document_uuid, solicitation_uuid, file_name, file_path,
                    float(file_size_mb) if file_size_mb else 0.0, modification_date,
                    analysis.get('file_type', 'Unknown'),
                    bool(is_508_applicable), int(confidence_score), bool(is_compliant), bool(has_explicit_mention),
                    applicability_explanation, compliance_explanation, ict_explanation,
                    bool(is_physical_only), bool(is_discussing_508), bool(is_cots_product),
                    bool(hardware_component), bool(software_component),
                    key_standards, recommendations, alternative_regs, false_positives,
                    int(matches_found), match_strength, vector_match_strength,
                    ict_analysis.get('accessibility_risk_level', 'Medium'),
                    'High' if is_cots_product else 'Standard',
                    bool(compliance_details.get('applicability_conflict_detected', False)),
                    compliance_details.get('applicability_resolution_method', 'original_assessment'),
                    compliance_details.get('applicability_override_reason', ''),
                    bool(compliance_details.get('compliance_conflict_detected', False)),
                    compliance_details.get('compliance_resolution_method', 'standard_logic'),
                    compliance_details.get('compliance_decision_reasoning', ''),
                    'Complete', 1.0, 1.0, '4.1_bm25_ml',
                    float(bm25_raw_score) if bm25_raw_score is not None else None,
                    float(bm25_normalized_score) if bm25_normalized_score is not None else None,
                    bm25_bucket,
                    json.dumps(bm25_keyword_hits) if bm25_keyword_hits else '{}',
                    bm25_prediction,
                    float(bm25_probability) if bm25_probability is not None else None,
                    bm25_source,
                ))
            
            # Store ICT types in normalized table
            self._store_document_ict_types(document_uuid, ict_types)
            
            # Store quality metrics in normalized table
            self._store_document_quality_metrics(document_uuid, analysis)
            
            # Store vector matches with comprehensive details
            matches = self._safe_get(analysis, 'matches', [])
            if matches:
                print(f"    🎯 RAG Database: Storing {len(matches)} comprehensive vector matches for {file_name}")
                self._store_comprehensive_vector_matches(document_uuid, matches)
            else:
                print(f"    📝 RAG Database: No vector matches for {file_name}")
            
            print(f"    ✅ RAG Database: Comprehensive document stored with UUID: {document_uuid}")
            logger.debug(f"✅ Stored comprehensive document: {file_name}")
            return document_uuid
            
        except Exception as e:
            file_name = self._safe_get(analysis, 'file_name', 'unknown')
            print(f"    ❌ RAG Database: Failed to store comprehensive {file_name}: {e}")
            logger.error(f"Failed to store comprehensive document analysis: {e}")
            return None
    
    def _store_comprehensive_vector_matches(self, document_uuid: str, matches: List[Dict[str, Any]]):
        """Store vector matches with comprehensive details in rag-vector-matches table."""
        try:
            meaningful_count = 0
            for i, match in enumerate(matches, 1):
                if not isinstance(match, dict):
                    print(f"      ⚠️  RAG Database: Skipping invalid match {i} (not a dict)")
                    continue
                    
                # Extract comprehensive match information
                chunk_index = self._safe_get(match, 'chunk_index', 0)
                chunk_text = self._safe_get(match, 'chunk_text', '')
                matched_standard = self._safe_get(match, 'matched_standard', '')
                similarity_score = self._safe_get(match, 'similarity_score', 0.0)
                explanation = self._safe_get(match, 'explanation', '')
                
                # Enhanced quality assessment fields
                match_quality_score = self._safe_get(match, 'match_quality_score', 0.0)
                chunk_relevance_category = self._safe_get(match, 'chunk_relevance_category', '')
                chunk_relevance_confidence = self._safe_get(match, 'chunk_relevance_confidence', 0.0)
                is_meaningful = self._safe_get(match, 'is_meaningful_match', False)
                llm_reasoning = self._safe_get(match, 'llm_validation_reasoning', '')
                false_positive_likelihood = self._safe_get(match, 'false_positive_likelihood', 0.0)
                
                # Enhanced similarity metrics
                base_similarity_score = self._safe_get(match, 'base_similarity_score', similarity_score)
                enhanced_similarity_score = self._safe_get(match, 'enhanced_similarity_score', 0.0)
                similarity_boost_factor = self._safe_get(match, 'similarity_boost_factor', 0.0)
                explicit_accessibility_mention = self._safe_get(match, 'explicit_accessibility_mention', False)
                accessibility_terms_found = self._safe_get(match, 'accessibility_terms_found', '')
                compliance_language_detected = self._safe_get(match, 'compliance_language_detected', False)
                
                # Standard classification
                matched_standard_category = self._safe_get(match, 'matched_standard_category', '')
                specific_508_section = self._safe_get(match, 'specific_508_section', '')
                wcag_level_mentioned = self._safe_get(match, 'wcag_level_mentioned', '')
                compliance_relationship_type = self._safe_get(match, 'compliance_relationship_type', '')
                
                # Context scoring
                ict_relevance_score = self._safe_get(match, 'ict_relevance_score', 0.0)
                navy_parts_indicator_score = self._safe_get(match, 'navy_parts_indicator_score', 0.0)
                cots_context_adjustment = self._safe_get(match, 'cots_context_adjustment', 0.0)
                
                # Processing metadata
                chunk_processing_time_ms = self._safe_get(match, 'chunk_processing_time_ms', 0)
                
                if is_meaningful:
                    meaningful_count += 1
                
                print(f"      🎯 Match {i}: Score {similarity_score:.3f}, Quality {match_quality_score:.3f}, Meaningful: {is_meaningful}")
                
                with self.connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO "rag-vector-matches" (
                            document_id, chunk_index, chunk_text, matched_standard,
                            similarity_score, match_explanation,
                            match_quality_score, chunk_relevance_category, chunk_relevance_confidence,
                            is_meaningful_match, llm_validation_reasoning, false_positive_likelihood,
                            base_similarity_score, enhanced_similarity_score, similarity_boost_factor,
                            explicit_accessibility_mention, accessibility_terms_found, compliance_language_detected,
                            matched_standard_category, specific_508_section, wcag_level_mentioned,
                            compliance_relationship_type, ict_relevance_score, navy_parts_indicator_score,
                            cots_context_adjustment, chunk_processing_time_ms
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        document_uuid,
                        int(chunk_index),
                        str(chunk_text)[:10000],  # Limit text length
                        str(matched_standard)[:500],
                        self._convert_numpy_types(similarity_score),
                        str(explanation)[:5000],  # Limit explanation length
                        self._convert_numpy_types(match_quality_score),
                        str(chunk_relevance_category)[:50],
                        self._convert_numpy_types(chunk_relevance_confidence),
                        bool(is_meaningful),
                        str(llm_reasoning)[:5000],  # Limit reasoning length
                        self._convert_numpy_types(false_positive_likelihood),
                        self._convert_numpy_types(base_similarity_score),
                        self._convert_numpy_types(enhanced_similarity_score),
                        self._convert_numpy_types(similarity_boost_factor),
                        bool(explicit_accessibility_mention),  # FIXED: This was missing!
                        str(accessibility_terms_found)[:500],
                        bool(compliance_language_detected),
                        str(matched_standard_category)[:100],
                        str(specific_508_section)[:50],
                        str(wcag_level_mentioned)[:10],
                        str(compliance_relationship_type)[:50],
                        self._convert_numpy_types(ict_relevance_score),
                        self._convert_numpy_types(navy_parts_indicator_score),
                        self._convert_numpy_types(cots_context_adjustment),
                        int(chunk_processing_time_ms) if chunk_processing_time_ms else 0
                    ))
            
            print(f"      ✅ RAG Database: Stored {len(matches)} comprehensive matches ({meaningful_count} meaningful)")
            logger.debug(f"✅ Stored {len(matches)} comprehensive vector matches")
            
        except Exception as e:
            print(f"      ❌ RAG Database: Failed to store comprehensive vector matches: {e}")
            logger.error(f"Failed to store comprehensive vector matches: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _store_document_ict_types(self, document_uuid: str, ict_types: Dict[str, Any]):
        """Store ICT types in normalized rag-document-ict-types table."""
        try:
            if not ict_types:
                return
                
            print(f"      📋 RAG Database: Storing ICT types: {list(ict_types.keys())}")
            
            with self.connection.cursor() as cursor:
                for ict_type, is_applicable in ict_types.items():
                    if isinstance(is_applicable, bool):
                        cursor.execute("""
                            INSERT INTO "rag-document-ict-types" (
                                document_id, ict_type, is_applicable, confidence_score
                            ) VALUES (%s, %s, %s, %s)
                            ON CONFLICT (document_id, ict_type) DO UPDATE SET
                                is_applicable = EXCLUDED.is_applicable,
                                confidence_score = EXCLUDED.confidence_score
                        """, (
                            document_uuid, ict_type, bool(is_applicable), 0.8
                        ))
            
            print(f"      ✅ RAG Database: Stored {len(ict_types)} ICT type associations")
            
        except Exception as e:
            print(f"      ❌ RAG Database: Failed to store ICT types: {e}")
            logger.error(f"Failed to store ICT types: {e}")
    
    def _store_document_quality_metrics(self, document_uuid: str, analysis: Dict[str, Any]):
        """Store quality metrics in normalized rag-document-quality-metrics table."""
        try:
            file_quality_metrics = self._safe_get(analysis, 'file_quality_metrics', {})
            processing_stats = self._safe_get(analysis, 'processing_stats', {})
            overall_compliance_score = self._safe_get(analysis, 'overall_compliance_score', {})
            
            print(f"      📊 RAG Database: Storing quality metrics")
            
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO "rag-document-quality-metrics" (
                        document_id, total_matches, average_match_quality,
                        high_quality_matches_count, meaningful_matches_ratio,
                        false_positive_matches_filtered, explicit_mentions_count,
                        compliance_language_count, average_ict_relevance,
                        processing_time_ms, total_chunks_processed, chunks_filtered_out,
                        filtering_efficiency_ratio, overall_compliance_score,
                        compliance_confidence, compliance_assessment
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    document_uuid,
                    int(file_quality_metrics.get('total_matches', 0)),
                    self._convert_numpy_types(file_quality_metrics.get('average_match_quality', 0.0)),
                    int(file_quality_metrics.get('high_quality_matches_count', 0)),
                    self._convert_numpy_types(file_quality_metrics.get('meaningful_matches_ratio', 0.0)),
                    int(file_quality_metrics.get('false_positive_matches_filtered', 0)),
                    int(file_quality_metrics.get('explicit_mentions_count', 0)),
                    int(file_quality_metrics.get('compliance_language_count', 0)),
                    self._convert_numpy_types(file_quality_metrics.get('average_ict_relevance', 0.0)),
                    int(processing_stats.get('processing_time_ms', 0)),
                    int(processing_stats.get('total_chunks_processed', 0)),
                    int(processing_stats.get('chunks_filtered_out', 0)),
                    self._convert_numpy_types(processing_stats.get('filtering_efficiency_ratio', 0.0)),
                    self._convert_numpy_types(overall_compliance_score.get('overall_score', 0.0)),
                    overall_compliance_score.get('confidence', 'low'),
                    overall_compliance_score.get('assessment', 'no_matches')
                ))
            
            print(f"      ✅ RAG Database: Stored comprehensive quality metrics")
            
        except Exception as e:
            print(f"      ❌ RAG Database: Failed to store quality metrics: {e}")
            logger.error(f"Failed to store quality metrics: {e}")
    def _safe_get_float(self, values, op: str = "avg") -> float:
        """Aggregate a list of numeric values with avg/max/min, ignoring None and non-numeric entries."""
        try:
            nums = [float(v) for v in (values or []) if v is not None and isinstance(v, (int, float))]
            if not nums:
                return 0.0
            if op == "max":
                return max(nums)
            if op == "min":
                return min(nums)
            return sum(nums) / len(nums)
        except Exception:
            return 0.0

    def _safe_get(self, data: Any, key: str, default: Any = None) -> Any:
        """Safely get value from data, handling None cases and converting numpy types."""
        if data is None:
            return default
        if isinstance(data, dict):
            value = data.get(key, default)
            return self._convert_numpy_types(value)
        return default
    
    def _convert_numpy_types(self, value: Any) -> Any:
        """Convert numpy types to Python native types for JSON serialization."""
        try:
            import numpy as np
            
            if isinstance(value, np.floating):
                return float(value)
            elif isinstance(value, np.integer):
                return int(value)
            elif isinstance(value, np.ndarray):
                return value.tolist()
            elif isinstance(value, list):
                return [self._convert_numpy_types(item) for item in value]
            elif isinstance(value, dict):
                return {k: self._convert_numpy_types(v) for k, v in value.items()}
            else:
                return value
        except ImportError:
            # numpy not available, return as-is
            return value
    
    def get_database_statistics(self) -> Dict[str, Any]:
        """Get comprehensive database statistics from all tables."""
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get solicitation counts
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_solicitations,
                        COUNT(*) FILTER (WHERE ai_applicable = true) as ai_applicable_solicitations,
                        COUNT(*) FILTER (WHERE ai_compliant = true) as ai_compliant_solicitations,
                        SUM(total_files) as total_documents,
                        SUM(applicable_files) as applicable_documents,
                        SUM(compliant_files) as compliant_documents,
                        SUM(total_matches) as total_vector_matches,
                        AVG(average_quality_score) as avg_quality_score
                    FROM "rag-solicitations"
                """)
                
                solicitation_stats = dict(cursor.fetchone())
                
                # Get document counts
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_documents_detailed,
                        COUNT(*) FILTER (WHERE is_508_applicable = true) as applicable_documents_detailed,
                        COUNT(*) FILTER (WHERE is_compliant = true) as compliant_documents_detailed,
                        COUNT(*) FILTER (WHERE is_cots_product = true) as cots_documents,
                        COUNT(*) FILTER (WHERE has_explicit_508_mention = true) as explicit_508_documents,
                        COUNT(*) FILTER (WHERE hardware_component = true) as hardware_documents,
                        COUNT(*) FILTER (WHERE software_component = true) as software_documents
                    FROM "rag-documents"
                """)
                
                document_stats = dict(cursor.fetchone())
                
                # Get ICT type statistics
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT ict_type) as unique_ict_types,
                        COUNT(*) as total_ict_associations,
                        COUNT(*) FILTER (WHERE is_applicable = true) as applicable_ict_associations
                    FROM "rag-document-ict-types"
                """)
                
                ict_stats = dict(cursor.fetchone())
                
                # Get vector match statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_matches_detailed,
                        COUNT(*) FILTER (WHERE is_meaningful_match = true) as meaningful_matches,
                        AVG(similarity_score) as avg_similarity_score,
                        AVG(match_quality_score) as avg_match_quality_score,
                        COUNT(*) FILTER (WHERE explicit_accessibility_mention = true) as explicit_accessibility_matches,
                        COUNT(*) FILTER (WHERE compliance_language_detected = true) as compliance_language_matches
                    FROM "rag-vector-matches"
                """)
                
                match_stats = dict(cursor.fetchone())
                
                # Get quality metrics statistics
                cursor.execute("""
                    SELECT 
                        AVG(average_match_quality) as avg_document_match_quality,
                        AVG(meaningful_matches_ratio) as avg_meaningful_ratio,
                        AVG(processing_time_ms) as avg_processing_time,
                        SUM(total_chunks_processed) as total_chunks_processed
                    FROM "rag-document-quality-metrics"
                """)
                
                quality_stats = dict(cursor.fetchone())
                
                # Combine all statistics
                stats = {
                    **solicitation_stats,
                    **document_stats,
                    **ict_stats,
                    **match_stats,
                    **quality_stats
                }
                
                # Calculate rates
                if stats['applicable_documents'] and stats['applicable_documents'] > 0:
                    stats['compliance_rate'] = (stats['compliant_documents'] / stats['applicable_documents']) * 100
                else:
                    stats['compliance_rate'] = 0
                
                if stats['total_matches_detailed'] and stats['total_matches_detailed'] > 0:
                    stats['meaningful_match_rate'] = (stats['meaningful_matches'] / stats['total_matches_detailed']) * 100
                else:
                    stats['meaningful_match_rate'] = 0
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get comprehensive database statistics: {e}")
            return {"error": str(e)}
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            print("🔌 RAG Database: Connection closed")
            logger.info("RAG database connection closed")

def create_rag_data_writer(connection_string: str = None) -> RAGDataWriter:
    """
    Factory function to create a comprehensive RAG data writer instance.
    
    Args:
        connection_string: Optional PostgreSQL connection string
        
    Returns:
        RAGDataWriter instance
    """
    return RAGDataWriter(connection_string)

def store_single_file_analysis(
    analysis_result: Dict[str, Any], 
    solicitation_id: str, 
    connection_string: str = None
) -> bool:
    """
    Store a single file analysis using comprehensive normalized schema.
    
    Args:
        analysis_result: Analysis result dictionary
        solicitation_id: Solicitation identifier
        connection_string: Optional database connection string
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"🗄️ RAG Database: Starting comprehensive single file storage for '{solicitation_id}'")
        
        # Validate analysis_result
        if analysis_result is None:
            print("❌ RAG Database: Analysis result is None")
            logger.error("Analysis result is None")
            return False
            
        if not isinstance(analysis_result, dict):
            print(f"❌ RAG Database: Analysis result is not a dictionary: {type(analysis_result)}")
            logger.error(f"Analysis result is not a dictionary: {type(analysis_result)}")
            return False
        
        file_name = analysis_result.get('file_name', 'unknown_file')
        print(f"📄 RAG Database: Processing comprehensive file: {file_name}")
        
        writer = create_rag_data_writer(connection_string)
        
        # Create metadata for single file storage
        metadata = {
            'title': solicitation_id,
            'agency': 'Unknown',
            'single_file_analysis': True
        }
        
        print(f"📊 RAG Database: File analysis summary - Applicable: {analysis_result.get('is_508_applicable', False)}, Compliant: {analysis_result.get('is_compliant', False)}")
        
        # Store as a single-file solicitation using comprehensive schema
        solicitation_uuid = writer.store_solicitation_analysis(
            solicitation_id=solicitation_id,
            individual_analyses=[analysis_result],
            ai_summary=None,
            metadata=metadata
        )
        
        writer.close()
        
        print(f"✅ RAG Database: Comprehensive single file analysis stored successfully (UUID: {solicitation_uuid})")
        logger.info(f"✅ Comprehensive single file analysis stored successfully (UUID: {solicitation_uuid})")
        return True
        
    except Exception as e:
        print(f"❌ RAG Database: Failed to store comprehensive single file analysis: {e}")
        logger.error(f"Failed to store comprehensive single file analysis: {e}")
        logger.error(traceback.format_exc())
        return False

def store_solicitation_folder_analysis(
    solicitation_result: Dict[str, Any], 
    connection_string: str = None
) -> bool:
    """
    Store solicitation folder analysis results using comprehensive normalized schema.
    
    Args:
        solicitation_result: Complete solicitation analysis result
        connection_string: Optional database connection string
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"🗄️ RAG Database: Starting comprehensive solicitation folder storage")
        
        # Validate solicitation_result
        if solicitation_result is None:
            print("❌ RAG Database: Solicitation result is None")
            logger.error("Solicitation result is None")
            return False
            
        if not isinstance(solicitation_result, dict):
            print(f"❌ RAG Database: Solicitation result is not a dictionary: {type(solicitation_result)}")
            logger.error(f"Solicitation result is not a dictionary: {type(solicitation_result)}")
            return False
        
        individual_analyses = solicitation_result.get('individual_file_analyses', [])
        if not individual_analyses:
            print("❌ RAG Database: No individual file analyses found in solicitation result")
            logger.error("No individual file analyses found in solicitation result")
            return False
        
        solicitation_id = solicitation_result.get('solicitation_id', 'unknown_solicitation')
        print(f"📁 RAG Database: Processing comprehensive solicitation: {solicitation_id} with {len(individual_analyses)} files")
        
        writer = create_rag_data_writer(connection_string)
        
        # Extract metadata
        metadata = {
            'title': solicitation_id,
            'agency': 'Unknown',
            'files_processed': solicitation_result.get('files_processed', 0),
            'compliance_status': solicitation_result.get('compliance_status', 'Unknown'),
            'total_matches': solicitation_result.get('total_matches', 0)
        }
        
        print(f"📊 RAG Database: Comprehensive solicitation summary - Status: {metadata['compliance_status']}, Total matches: {metadata['total_matches']}")
        
        # Store complete solicitation using comprehensive schema
        solicitation_uuid = writer.store_solicitation_analysis(
            solicitation_id=solicitation_id,
            individual_analyses=individual_analyses,
            ai_summary=None,  # Can be enhanced later with AI summary
            metadata=metadata
        )
        
        writer.close()
        
        print(f"✅ RAG Database: Comprehensive solicitation folder analysis stored successfully (UUID: {solicitation_uuid})")
        logger.info(f"✅ Comprehensive solicitation folder analysis stored successfully (UUID: {solicitation_uuid})")
        return True
        
    except Exception as e:
        print(f"❌ RAG Database: Failed to store comprehensive solicitation folder analysis: {e}")
        logger.error(f"Failed to store comprehensive solicitation folder analysis: {e}")
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    # Test the comprehensive RAG database functionality
    logging.basicConfig(level=logging.INFO)
    
    try:
        writer = create_rag_data_writer()
        stats = writer.get_database_statistics()
        print("Comprehensive RAG Database Statistics:")
        print(json.dumps(stats, indent=2, default=str))
        writer.close()
    except Exception as e:
        print(f"Failed to test comprehensive RAG database: {e}")
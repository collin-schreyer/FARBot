# SRT RAG USAI — Data Dictionary

All data captured by the pipeline across 7 normalized PostgreSQL tables.

---

## Table: rag-solicitations

Solicitation-level analysis results. One row per solicitation.

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| id | UUID | System | Primary key |
| solicitation_number | VARCHAR | SAM.gov | Unique solicitation identifier (e.g., 36C10B26R0023) |
| title | VARCHAR | SAM.gov | Solicitation title |
| agency | VARCHAR | SAM.gov | Issuing agency name |
| website_source | VARCHAR | Pipeline | Primary source website (SAM, FBO, etc.) |
| procurement_type | VARCHAR | LLM | Type of procurement (Services/Products/Mixed) |
| procurement_complexity | VARCHAR | LLM | Simple/Medium/Complex |
| ai_applicable | BOOLEAN | LLM | Whether LLM determined 508 is applicable |
| ai_compliant | BOOLEAN | LLM | Whether LLM determined solicitation includes 508 (legacy) |
| ai_conflicts_detected | BOOLEAN | LLM | Whether conflicting 508 references found across files |
| ai_conflict_resolution_summary | TEXT | LLM | How conflicts were resolved |
| ai_procurement_type | VARCHAR | LLM | LLM-determined procurement type |
| ai_primary_ict_types | ARRAY | LLM | List of ICT types identified (Web, Software, Hardware, etc.) |
| ai_has_cots_products | BOOLEAN | LLM | Whether COTS products are involved |
| ai_explicit_508_coverage | BOOLEAN | LLM | Whether 508 is explicitly mentioned |
| ai_solicitation_explanation | TEXT | LLM | AI-generated explanation of the solicitation and its 508 status |
| ai_key_findings | ARRAY | LLM | List of key findings from the analysis |
| ai_priority_recommendations | ARRAY | LLM | Priority recommendations (legacy, informational) |
| ai_vendor_responsibilities | ARRAY | LLM | Vendor accessibility responsibilities identified |
| ai_file_consistency_assessment | TEXT | LLM | Assessment of 508 consistency across files |
| ai_overall_risk_level | VARCHAR | LLM | High/Medium/Low risk assessment |
| ai_recommended_actions | ARRAY | LLM | Recommended actions (legacy) |
| total_files | INTEGER | Pipeline | Total number of files in the solicitation |
| applicable_files | INTEGER | Pipeline | Number of files where 508 applies |
| compliant_files | INTEGER | Pipeline | Number of files that include 508 language |
| total_matches | INTEGER | Pipeline | Total vector matches across all files |
| average_quality_score | FLOAT | Pipeline | Average match quality score across files |
| processing_time_ms | INTEGER | Pipeline | Total processing time in milliseconds |
| analysis_version | VARCHAR | Pipeline | Version of the analysis pipeline (3.0_setfit) |
| setfit_compliant | BOOLEAN | SetFit ML | SetFit model compliance prediction |
| setfit_confidence | FLOAT | SetFit ML | SetFit prediction confidence (0.0 to 1.0) |
| setfit_signal_text | TEXT | SetFit ML | Extracted signal text used for SetFit prediction |
| prediction_source | VARCHAR | Pipeline | Which model made the compliance call (setfit/llm) |
| solicitation_summary | TEXT | LLM | AI-generated summary of what the solicitation is about |
| procurement_description | TEXT | LLM | Description of what ICT is being procured |
| created_at | TIMESTAMP | System | Record creation timestamp |
| updated_at | TIMESTAMP | System | Last update timestamp |

---

## Table: rag-documents

Per-file analysis results. One row per document within a solicitation.

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| id | UUID | System | Primary key |
| solicitation_id | UUID | FK | Reference to rag-solicitations.id |
| file_name | VARCHAR | Pipeline | Original filename (e.g., SOW.pdf) |
| file_path | VARCHAR | Pipeline | Full file path during processing |
| file_size_mb | FLOAT | Pipeline | File size in megabytes |
| modification_date | TIMESTAMP | Pipeline | File modification date |
| document_type | VARCHAR | Pipeline | File extension (.pdf, .docx, .xlsx, .txt) |
| is_508_applicable | BOOLEAN | LLM | Whether 508 applies to this specific file |
| confidence_score | INTEGER | LLM | Applicability confidence (1-10) |
| is_compliant | BOOLEAN | LLM | Whether file includes 508 language |
| has_explicit_508_mention | BOOLEAN | LLM | Whether file explicitly mentions Section 508 |
| applicability_explanation | TEXT | LLM | Why 508 does or doesn't apply to this file |
| compliance_explanation | TEXT | LLM | Explanation of 508 inclusion status |
| ict_explanation | TEXT | LLM | Description of ICT types in this file |
| is_physical_only | BOOLEAN | LLM | Whether procurement is physical-only (no ICT) |
| is_discussing_508 | BOOLEAN | Pipeline | Whether vector matching found 508 discussion |
| is_cots_product | BOOLEAN | Pipeline | Whether file references COTS products |
| hardware_component | BOOLEAN | LLM | Whether hardware ICT is being procured |
| software_component | BOOLEAN | LLM | Whether software ICT is being procured |
| key_standards | ARRAY | LLM | Key accessibility standards referenced |
| recommendations | ARRAY | LLM | Accessibility recommendations |
| alternative_accessibility_regs | ARRAY | Pipeline | Alternative regulations found (VPAT, WCAG, etc.) |
| false_positives_filtered | ARRAY | Pipeline | Terms filtered as false positives (FedRAMP, Kaspersky) |
| matches_found | INTEGER | Pipeline | Number of vector matches for this file |
| match_strength | VARCHAR | Pipeline | High/Medium/Low match strength |
| vector_match_strength | VARCHAR | Pipeline | Vector-specific match strength |
| accessibility_risk_level | VARCHAR | LLM | Risk level for accessibility |
| vendor_responsibility_level | VARCHAR | Pipeline | High (COTS) or Standard |
| applicability_conflict_detected | BOOLEAN | Pipeline | Whether applicability conflicts exist |
| applicability_resolution_method | VARCHAR | Pipeline | How conflicts were resolved |
| applicability_override_reason | TEXT | Pipeline | Reason for any override |
| compliance_conflict_detected | BOOLEAN | Pipeline | Whether compliance conflicts exist |
| compliance_resolution_method | VARCHAR | Pipeline | How compliance conflicts were resolved |
| compliance_decision_reasoning | TEXT | Pipeline | Reasoning behind compliance decision |
| analysis_completeness | VARCHAR | Pipeline | Complete/Partial/Failed |
| text_quality_score | FLOAT | Pipeline | Quality of extracted text (0-1) |
| consistency_score | FLOAT | Pipeline | Consistency with other files (0-1) |
| analysis_version | VARCHAR | Pipeline | Pipeline version |
| created_at | TIMESTAMP | System | Record creation timestamp |

---

## Table: rag-document-ict-types

ICT type classifications per document. Multiple rows per document (one per ICT category).

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| id | SERIAL | System | Primary key |
| document_id | UUID | FK | Reference to rag-documents.id |
| ict_type | VARCHAR | LLM | ICT category name |
| is_applicable | BOOLEAN | LLM | Whether this ICT type is being procured |
| confidence_score | FLOAT | LLM | Classification confidence |
| created_at | TIMESTAMP | System | Record creation timestamp |

ICT categories: Web, Software, Hardware, Electronic_Content, Telecommunications, Multimedia, Medical_Devices

---

## Table: rag-vector-matches

Individual vector similarity matches between document chunks and 508 standards. Multiple rows per document.

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| id | SERIAL | System | Primary key |
| document_id | UUID | FK | Reference to rag-documents.id |
| chunk_index | INTEGER | Pipeline | Position of the chunk in the document |
| chunk_text | TEXT | Pipeline | The document text chunk (up to 10,000 chars) |
| matched_standard | TEXT | Pipeline | The 508 standard text it matched against |
| similarity_score | FLOAT | FAISS | Cosine similarity score (0-1) |
| match_explanation | TEXT | Pipeline | Explanation of the match |
| match_quality_score | FLOAT | Pipeline | Combined quality score |
| chunk_relevance_category | VARCHAR | Pipeline | Category of relevance |
| chunk_relevance_confidence | FLOAT | Pipeline | Confidence in relevance category |
| is_meaningful_match | BOOLEAN | LLM | Whether LLM determined this is a meaningful 508 reference |
| llm_validation_reasoning | TEXT | LLM | LLM's reasoning for meaningful/not meaningful |
| false_positive_likelihood | FLOAT | Pipeline | Probability this is a false positive (0-1) |
| base_similarity_score | FLOAT | FAISS | Raw similarity before adjustments |
| enhanced_similarity_score | FLOAT | Pipeline | Similarity after context adjustments |
| similarity_boost_factor | FLOAT | Pipeline | Boost applied based on context |
| explicit_accessibility_mention | BOOLEAN | Pipeline | Whether chunk explicitly mentions accessibility |
| accessibility_terms_found | VARCHAR | Pipeline | Specific accessibility terms found |
| compliance_language_detected | BOOLEAN | Pipeline | Whether compliance-specific language detected |
| matched_standard_category | VARCHAR | Pipeline | Category of the matched standard |
| specific_508_section | VARCHAR | Pipeline | Specific section of 508 referenced |
| wcag_level_mentioned | VARCHAR | Pipeline | WCAG level if mentioned (A, AA, AAA) |
| compliance_relationship_type | VARCHAR | Pipeline | Type of compliance relationship |
| ict_relevance_score | FLOAT | Pipeline | How relevant to ICT (0-1) |
| navy_parts_indicator_score | FLOAT | Pipeline | Navy parts list indicator (0-1) |
| cots_context_adjustment | FLOAT | Pipeline | COTS context adjustment factor |
| chunk_processing_time_ms | INTEGER | Pipeline | Processing time for this chunk |
| created_at | TIMESTAMP | System | Record creation timestamp |

---

## Table: rag-document-quality-metrics

Aggregate quality metrics per document. One row per document.

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| id | SERIAL | System | Primary key |
| document_id | UUID | FK | Reference to rag-documents.id |
| total_matches | INTEGER | Pipeline | Total vector matches found |
| average_match_quality | FLOAT | Pipeline | Average quality across all matches |
| high_quality_matches_count | INTEGER | Pipeline | Number of high-quality matches |
| meaningful_matches_ratio | FLOAT | Pipeline | Ratio of meaningful to total matches |
| false_positive_matches_filtered | INTEGER | Pipeline | Number of false positives removed |
| explicit_mentions_count | INTEGER | Pipeline | Count of explicit 508 mentions |
| compliance_language_count | INTEGER | Pipeline | Count of compliance language instances |
| average_ict_relevance | FLOAT | Pipeline | Average ICT relevance score |
| processing_time_ms | INTEGER | Pipeline | Processing time for this document |
| total_chunks_processed | INTEGER | Pipeline | Number of text chunks analyzed |
| chunks_filtered_out | INTEGER | Pipeline | Chunks skipped (over cap) |
| filtering_efficiency_ratio | FLOAT | Pipeline | Ratio of matches to chunks processed |
| overall_compliance_score | FLOAT | Pipeline | Combined compliance score (0-1) |
| compliance_confidence | VARCHAR | Pipeline | Confidence level (high/medium/low) |
| compliance_assessment | VARCHAR | Pipeline | Assessment category |
| created_at | TIMESTAMP | System | Record creation timestamp |

---

## Table: rag-website-sources

Website sources associated with solicitations.

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| id | SERIAL | System | Primary key |
| solicitation_id | UUID | FK | Reference to rag-solicitations.id |
| url | TEXT | Pipeline | Source URL |
| is_reachable | BOOLEAN | Pipeline | Whether URL was accessible |
| created_at | TIMESTAMP | System | Record creation timestamp |

---

## Table: rag-ict-types-reference

Reference table for ICT type definitions.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| type_name | VARCHAR | ICT type name (Web, Software, etc.) |
| description | TEXT | Description of the ICT type |

---

## Data Sources

| Source | Description |
|--------|-------------|
| System | Auto-generated (UUIDs, timestamps) |
| SAM.gov | Scraped from SAM.gov API |
| Pipeline | Computed by the processing pipeline (text extraction, pre-processing) |
| FAISS | Vector similarity search using Cohere embeddings |
| LLM | Generated by USAI API (Gemini 2.5 Pro / Flash) |
| SetFit ML | Predicted by the SetFit compliance model |

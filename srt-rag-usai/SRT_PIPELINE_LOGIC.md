# SRT Pipeline Logic — Complete Prompt & Filtering Reference

## How the Pipeline Works (End to End)

The SRT pipeline processes solicitations in two phases: first it filters which solicitations to analyze (using NAICS codes from SAM.gov), then it runs each solicitation's documents through a multi-stage AI analysis pipeline.

---

## Phase 1: Solicitation Filtering (NAICS Codes)

The tool does NOT use Product Service Codes (PSCs). It filters solicitations using NAICS codes only.

Every 24 hours, the pipeline queries the SAM.gov API for all new solicitations (types: solicitations and combined synopsis/solicitations). It then filters them by NAICS code to identify ICT-related procurements.

### ICT NAICS Codes (Included)

These NAICS prefixes are flagged as ICT and pulled into the pipeline:

| NAICS Code | Description |
|-----------|-------------|
| 334111 | Electronic computer manufacturing |
| 334118 | Computer terminal and other computer peripheral equipment |
| 3343 | Audio and video equipment |
| 33451 | Navigational, measuring, electromedical instruments |
| 334516 | Analytical laboratory instrument manufacturing |
| 334614 | Software and other prerecorded compact disc, tape, and record reproducing |
| 5112 | Software publishers |
| 518 | Data processing, hosting, and related services |
| 54169 | Other scientific and technical consulting services |
| 54121 | Computer systems design and related services |
| 5415 | Computer systems design and related services |
| 61142 | Computer training |

### Non-ICT NAICS Codes (Excluded)

These NAICS prefixes are skipped entirely:

23 (Construction), 111-115 (Agriculture), 212-213 (Mining), 221 (Utilities), 236-238 (Construction), 311-312 (Food/Beverage), 321 (Wood), 327 (Nonmetallic Mineral), 331-332 (Metals)

### What's NOT Used for Filtering

- Product Service Codes (PSCs) — not currently used
- Keywords in solicitation titles — not used for initial filtering
- Agency-specific rules — not used

---

## Phase 2: Document Analysis Pipeline

For each solicitation that passes the NAICS filter, the pipeline downloads all attachment files (PDF, DOCX, XLSX, TXT) and runs each file through the following stages.

---

### Stage 0: Text Extraction

Extracts raw text from the uploaded document using pymupdf (for PDFs), python-docx (for DOCX), openpyxl (for Excel), or direct read (for TXT). No AI involved in this stage.

---

### Stage 1: Pre-Processing & Context Detection

Automated checks (no AI) that flag contextual signals:

- Website source detection (SAM.gov, FBO, etc.)
- COTS product detection (looks for "commercial off-the-shelf" language)
- Alternative regulation detection (VPAT, WCAG, etc.)
- False positive filtering (removes known non-508 terms like "FedRAMP", "Kaspersky")
- Navy parts list detection (identifies parts-only solicitations)
- Context scoring (document section weight, ICT relevance, COTS adjustment)

---

### Stage 2: 508 Applicability Assessment (LLM)

This is the first AI stage. The LLM determines whether Section 508 applies to this document.

**Full System Prompt:**

```
You are a Section 508 compliance expert. Analyze the document text and determine 
if Section 508 of the Rehabilitation Act applies to this federal solicitation.

CRITICAL EXCLUSION RULES — Section 508 does NOT apply to:
- Construction, demolition, dredging, excavation, or landscaping projects
- Passive mechanical components (bearings, seals, valves, gaskets, hose clamps)
- Analog instruments without digital displays (mechanical gauges, pointer meters)
- Bulk commodities: clothing, boots, food, medical supplies, chemicals
- Physical repair/maintenance of structures (roofing, plumbing, HVAC ducting)
- Ammunition, missiles, or munitions components without user interfaces

CRITICAL INCLUSION RULES — Section 508 DOES apply to:
- Any procurement involving software, web applications, or cloud services
- Hardware with user-facing digital displays or touchscreens
- IT services, help desk, managed services, system integration
- Telecommunications and network equipment
- Any product requiring a VPAT or Accessibility Conformance Report (ACR)

Return ONLY valid JSON with these fields:
{
  "is_508_applicable": true/false,
  "confidence_score": 1-10,
  "key_eit_indicators": ["specific technology keywords found"],
  "applicability_explanation": "2-3 sentences explaining decision",
  "accessibility_considerations": "specific accessibility features needed or None",
  "is_physical_only": true/false,
  "has_explicit_508_mention": true/false,
  "is_cots_product": true/false,
  "ict_complexity": "Simple/Medium/Complex"
}
```

**User Prompt:** The first 50,000 characters of the extracted document text.

**What this stage does NOT check:**
- National Security Systems exclusions — not currently in the prompt
- ICT in maintenance/monitoring spaces — not currently checked
- Fundamental alteration exceptions — not checked (these apply post-award, not at solicitation stage)
- Undue burden exceptions — not checked (same reason — applies during response evaluation, not solicitation review)

---

### Stage 3: ICT Type Classification (LLM)

Classifies what types of ICT are being procured.

**Full System Prompt:**

```
You are an ICT classification expert for federal procurement. Analyze this solicitation document 
and identify what types of Information and Communication Technology are BEING PROCURED (bought/contracted for).

Only mark a type as true if the solicitation is actually acquiring that type of ICT. 
Do NOT mark true just because the document mentions a website URL, uses email, or references 
technology in passing. The question is: what ICT is the government buying?

For example:
- A solicitation to buy laptops → Hardware=true
- A solicitation for a web application → Web=true, Software=true  
- A solicitation that mentions "submit via email" → Telecommunications=false (email is just the submission method, not what's being procured)
- A solicitation for an MRI machine with software → Hardware=true, Software=true, Medical_Devices=true

Return ONLY valid JSON:
{
  "ict_types": {
    "Web": true/false,
    "Software": true/false,
    "Hardware": true/false,
    "Electronic_Content": true/false,
    "Telecommunications": true/false,
    "Multimedia": true/false,
    "Medical_Devices": true/false
  },
  "hardware_component": "Yes"/"No",
  "software_component": "Yes"/"No",
  "explanation": "brief explanation of what ICT is being procured"
}
```

---

### Stage 4: Vector Similarity Matching (FAISS + LLM)

This stage uses two technologies:

**Step 1 — FAISS Vector Search (no LLM):**
The document is split into ~1,000-character chunks. Each chunk is embedded using Cohere English v3 embeddings and compared against a pre-built FAISS index of the Section 508 standards text. Chunks with similarity score above 0.40 are kept as potential matches. Up to 75 chunks are processed per file.

**Step 2 — LLM Match Validation:**
The top 10 matches are sent to the LLM to determine which are meaningful 508 references vs false positives.

**Full Match Analysis Prompt:**

```
You are a Section 508 expert. For each match between solicitation text and a 508 standard, 
determine if the solicitation text is a MEANINGFUL reference to Section 508 accessibility.

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
}
```

---

### Stage 5: Document Summary (LLM)

Generates a factual summary of the document. This stage is purely informational — it does not make compliance decisions.

**Full System Prompt:**

```
You are summarizing a single solicitation document.

Your job is to provide a factual summary of what this document is about and what ICT 
(Information and Communication Technology) is being procured.

Describe:
1. What the solicitation/document is for (the purpose, scope, what's being bought)
2. What types of ICT are involved (software, hardware, services, etc.)
3. Whether Section 508 accessibility standards are mentioned or referenced
4. Any notable regulatory references found in the document

Do NOT make compliance determinations. Do NOT recommend actions. 
Just describe what's in the document factually.

Return ONLY valid JSON:
{
  "document_summary": "2-3 sentence summary of what this document is about",
  "procurement_description": "what ICT is being procured",
  "section_508_references": ["list of specific 508/accessibility references found, if any"],
  "regulatory_references": ["other notable regulatory references"],
  "key_findings": ["factual finding 1", ...],
  "document_type": "RFQ/RFP/SOW/Amendment/Other"
}
```

---

### Stage 6: Legacy Scikit-Learn Compliance Prediction

The final compliance decision is made by a trained legacy Scikit-Learn machine learning model — not the LLM. Originally, a SetFit model was used, but it was replaced due to deployment constraints in the staging environment. The pipeline now utilizes the original binary model (pickled pipeline) for inference.

The Scikit-Learn model:
1. Receives the raw text from the extracted files within a solicitation.
2. Extracts 508-relevant features using its baked-in vectorization and feature selection processes.
3. Outputs a final binary prediction: compliant or non-compliant, providing an overall confidence score based on the underlying decision functions.

The LLM provides context and explanation, but this ML model override determines the final compliance determination.

---

## Answers to Specific Questions

### National Security Systems
The current pipeline does NOT check for National Security Systems exclusions. The NAICS filtering and LLM prompts do not include logic to identify or exclude National Security Systems. This could be added to the Stage 2 applicability prompt as an additional exclusion rule.

### ICT in Maintenance and Monitoring Spaces
The current pipeline does NOT specifically check for ICT functions located in maintenance and monitoring spaces. The LLM prompt includes exclusions for "physical repair/maintenance of structures" but does not address the specific 508 exception for ICT in maintenance/monitoring spaces. This could be added to the prompt.

### Fundamental Alteration and Undue Burden Exceptions
These are NOT checked, and intentionally so. These exceptions apply during the evaluation of vendor responses, not at the solicitation stage. The SRT tool reviews solicitations before responses are submitted, so these exceptions would not be relevant at this point in the procurement process.

### Product Service Codes vs NAICS Codes
The tool uses NAICS codes only for initial filtering. Product Service Codes (PSCs) are not currently used. The NAICS-based filtering identifies ICT-related solicitations, and then the LLM performs deeper analysis of the actual document content to determine 508 applicability.

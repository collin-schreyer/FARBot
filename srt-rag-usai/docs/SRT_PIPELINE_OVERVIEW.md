# SRT Pipeline — Logic & Architecture

## How Solicitations Enter the Pipeline

1. Every 24 hours (6 AM UTC), the pipeline queries the SAM.gov API for all new solicitations
2. Solicitation types pulled: solicitations (type "o") and combined synopsis/solicitations (type "k")
3. Each solicitation is filtered by NAICS code to determine if it's ICT-related
4. Only solicitations matching ICT NAICS codes proceed to analysis

## NAICS Code Filtering

The tool uses NAICS codes — not Product Service Codes (PSCs) — to identify ICT solicitations.

### ICT NAICS Codes (Included)

| NAICS | Description |
|-------|-------------|
| 334111 | Electronic computer manufacturing |
| 334118 | Computer terminal and peripheral equipment |
| 3343 | Audio and video equipment |
| 33451 | Navigational, measuring, electromedical instruments |
| 334516 | Analytical laboratory instrument manufacturing |
| 334614 | Software and prerecorded media reproducing |
| 5112 | Software publishers |
| 518 | Data processing, hosting, and related services |
| 54169 | Other scientific and technical consulting services |
| 54121 | Computer systems design and related services |
| 5415 | Computer systems design and related services |
| 61142 | Computer training |

### Non-ICT NAICS Codes (Excluded)

Construction (23), Agriculture (111-115), Mining (212-213), Utilities (221), Specialty Construction (236-238), Food/Beverage (311-312), Wood (321), Nonmetallic Mineral (327), Metals (331-332)

## Processing Flow (Per Solicitation)

```
SAM.gov API → NAICS Filter → Download Attachments → For Each File:
  Stage 0: Text Extraction (pymupdf/docx/openpyxl)
  Stage 1: Pre-Processing (automated context detection, no AI)
  Stage 2: 508 Applicability (LLM — determines if 508 applies)
  Stage 3: ICT Classification (LLM — identifies what ICT is being procured)
  Stage 4: Vector Matching (FAISS similarity search + LLM validation)
  Stage 5: Document Summary (LLM — factual description, no compliance decision)
→ SetFit ML Model: Compliance Prediction (compliant / non-compliant)
→ Write to Database
→ Delete Attachments
→ Next Solicitation
```

## Key Design Decisions

### One-at-a-Time Processing
Solicitations are downloaded, processed, and deleted one at a time. This keeps memory usage constant regardless of batch size.

### SetFit Makes the Compliance Call
The LLM provides informational context (what the document is about, what ICT is involved, what 508 references exist). The SetFit ML model makes the binary compliance decision. This separation ensures consistency — the same input always produces the same compliance output.

### Vector Matching Against 508 Standards
The pipeline includes a pre-built FAISS index of the full Section 508 standards text. Document chunks are compared against this index using Cohere English v3 embeddings. Matches above 0.40 similarity are validated by the LLM to filter out false positives.

### False Positive Filtering
The pre-processing stage automatically filters known false positive terms that trigger similarity matches but aren't related to 508 compliance (e.g., "FedRAMP", "Kaspersky" bans, generic FAR boilerplate).

## What the Pipeline Outputs

For each solicitation, the pipeline stores:
- Solicitation-level: SetFit compliance prediction, AI summary, ICT types, 508 references found
- Per-file: Applicability assessment, ICT classification, vector matches, document summary
- Per-match: Similarity scores, meaningful/not meaningful determination, LLM reasoning

All data is stored in PostgreSQL across 7 normalized tables (see DATA_DICTIONARY.md).

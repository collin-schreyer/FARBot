# SRT RAG USAI

A self-contained daily pipeline that replaces the old SRT scraper's sklearn-based Section 508 prediction model with a modern RAG (Retrieval-Augmented Generation) pipeline powered by GSA's USAI gateway (Gemini LLMs + Cohere embeddings).

## Why This Exists

The original SRT system used a pickled sklearn model (`atc_estimator.pkl`) to predict whether a federal solicitation "includes" Section 508 accessibility requirements. That model produced a binary yes/no with a confidence score, but couldn't explain *why* or identify *which* 508 standards were referenced.

This pipeline replaces that with a 7-stage LLM + vector search approach that:
- Reads the actual text of every attachment in a solicitation
- Uses FAISS vector similarity to match solicitation language against the full Section 508 standards
- Uses LLM calls to assess applicability, classify ICT types, check for 508 inclusion, and synthesize findings
- Produces 77+ structured fields per file, plus a solicitation-level AI summary
- Writes everything to a normalized PostgreSQL schema (7 tables) and exports CSV

The key question we answer: **Does this solicitation package reference Section 508 accessibility standards?** If any file in the package contains a meaningful reference, the solicitation is marked as including 508.

## How It Works

### Daily Flow

```
6 AM UTC (cron) → SAM.gov API → Download Attachments → 7-Stage Analysis → PostgreSQL + CSV
```

1. **Scrape SAM.gov** — Fetches yesterday's solicitations, filters to ICT-relevant NAICS codes, downloads all attachments
2. **Analyze each file** — Runs the 7-stage pipeline on every PDF, DOCX, TXT, and XLSX
3. **Solicitation-level determination** — Applies the rule: one 508 reference in any file = solicitation includes 508
4. **AI summary** — Single LLM call synthesizes all per-file results into a factual solicitation summary
5. **Store results** — Writes to PostgreSQL (7 normalized tables) and exports a daily CSV

### The 7-Stage Pipeline

Each file goes through these stages:

| Stage | Name | LLM? | What It Does |
|-------|------|------|-------------|
| 0 | Text Extraction | No | Extracts text from PDF/DOCX/TXT/XLSX |
| 1 | Pre-Processing | No | Detects website source, COTS products, false positives, context scores |
| 2 | 508 Applicability | Yes | Determines if Section 508 applies to this procurement |
| 3 | ICT Classification | Yes | Identifies what ICT is being procured (Hardware, Software, Web, etc.) |
| 4 | Vector Matching | FAISS + Yes | Searches solicitation text against 508 standards using Cohere embeddings, then LLM analyzes top matches |
| 5 | 508 Inclusion Check | Yes | Checks if the document explicitly references Section 508, VPAT, WCAG, etc. |
| 6 | Final Synthesis | Yes | Synthesizes all stages into a final determination with key findings |

After all stages, the field enrichment module computes quality scores, false positive likelihood, compliance relationship types, and other derived fields for every vector match.

### SAM.gov Scraper

The scraper (`sam_scraper.py`) is extracted from the original `srt-fbo-scraper` and uses the same:
- SAM.gov Opportunities API v2 (`https://api.sam.gov/opportunities/v2/search`)
- NAICS code filtering for ICT-relevant solicitations (334111, 334118, 5112, 518, 5415, etc.)
- Non-ICT NAICS exclusion (construction, agriculture, mining, etc.)
- Attachment download with Content-Disposition filename parsing
- SSL retry session with legacy renegotiation workaround
- Per-solicitation folder organization (`{solicitationNumber}_attachments/`)

### USAI Gateway

All LLM calls go through GSA's USAI gateway (`https://api.gsa.usai.gov/api/v1`), which provides:
- **Gemini 2.5 Pro** — Used for applicability assessment and final synthesis (complex reasoning)
- **Gemini 2.5 Flash** — Used for ICT classification, vector match analysis, and inclusion checks (faster, cheaper)
- **Cohere embed-english-v3** — Used for vector embeddings (pre-built FAISS index + runtime query embeddings)

### Vector Matching (FAISS)

The pipeline includes a pre-built FAISS index (`data/faiss_index/`) containing 464 chunks of the full Section 508 standards text, embedded with Cohere's embed-english-v3 model. At runtime:
1. Each solicitation file is chunked (1000 chars, 100 overlap)
2. Each chunk is embedded via USAI's Cohere endpoint
3. FAISS similarity search finds the closest 508 standard for each chunk
4. Matches above the 0.40 threshold are kept
5. A single LLM call analyzes the top 10 matches for meaningfulness

### Database Schema

Results are stored in 7 normalized PostgreSQL tables:

| Table | Purpose |
|-------|---------|
| `rag-solicitations` | Solicitation-level record with AI summary fields |
| `rag-documents` | Per-file analysis (applicability, compliance, explanations) |
| `rag-document-ict-types` | ICT type classifications per file |
| `rag-vector-matches` | Individual vector matches with quality scores |
| `rag-document-quality-metrics` | Aggregated quality metrics per file |
| `rag-website-sources` | Website source reference data |
| `rag-ict-types-reference` | ICT type reference data |

## Architecture

```
main.py                          CLI entry point (--daily, --file-path, --batch-folder)
├── sam_scraper.py               SAM.gov API + attachment download
├── batch_runner.py              Iterates solicitation folders, writes CSV + DB
│   ├── solicitation_processor.py    Multi-file logic per solicitation
│   │   └── pipeline.py             7-stage single-file analysis
│   │       ├── text_extractor.py       PDF/DOCX/TXT/XLSX extraction
│   │       ├── preprocessor.py         Website source, COTS, false positives
│   │       ├── usai_adapter.py         USAI gateway (Gemini + Cohere)
│   │       ├── vector_matching.py      FAISS search + LLM match analysis
│   │       └── field_enrichment.py     77+ derived fields per match
│   └── rag_data_writer.py          PostgreSQL writer (7 normalized tables)
├── Dockerfile                   Container with cron
├── entrypoint.sh                Health server + cron + initial run
└── manifest.yml                 cloud.gov deployment config
```

## File Descriptions

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point. Supports `--daily` (scrape + analyze), `--batch-folder` (analyze existing), `--file-path` (single file) |
| `sam_scraper.py` | Fetches ICT solicitations from SAM.gov API, downloads attachments into per-solicitation folders |
| `pipeline.py` | Runs all 7 stages on a single file, returns 77+ field report dict |
| `solicitation_processor.py` | Processes all files in a solicitation folder, applies "one file is enough" rule, generates AI summary |
| `batch_runner.py` | Iterates solicitation folders, manages CSV export and database writes |
| `usai_adapter.py` | USAI gateway client with all LLM prompts (applicability, ICT, compliance, synthesis) |
| `vector_matching.py` | Loads pre-built FAISS index, runs similarity search, single LLM call for match analysis |
| `field_enrichment.py` | Computes match quality scores, false positive likelihood, compliance relationship types |
| `preprocessor.py` | Detects website source (SAM, DIBBS, NECO), COTS products, alternative regs, context scores |
| `text_extractor.py` | Extracts text from PDF (pdfplumber), DOCX (python-docx), XLSX (openpyxl), TXT |
| `rag_data_writer.py` | PostgreSQL writer using the full 7-table normalized schema with upsert support |
| `Dockerfile` | Python 3.9 slim + system deps + cron |
| `entrypoint.sh` | Starts health server (foreground), cron daemon, and initial pipeline run (background) |
| `manifest.yml` | cloud.gov deployment: 1G memory, 2G disk, bound to srt-postgres15-dev |
| `data/508_standards.txt` | Full text of the Section 508 accessibility standards |
| `data/faiss_index/` | Pre-built FAISS index with Cohere embed-english-v3 embeddings (464 chunks) |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `USAI_API` | Yes | USAI gateway API key |
| `USAI_BASE_URL` | Yes | USAI gateway URL (`https://api.gsa.usai.gov/api/v1`) |
| `SAM_API_KEY` | Yes | SAM.gov API key |
| `DATABASE_URL` | Auto | PostgreSQL connection (auto-injected by cloud.gov service binding) |
| `RUN_MODE` | No | `daily` (default) — runs pipeline on startup + cron |
| `SCRAPE_FROM_DATE` | No | Override scrape start date (`YYYY-MM-DD`). Defaults to yesterday |
| `SCRAPE_TO_DATE` | No | Override scrape end date (`YYYY-MM-DD`). Defaults to yesterday |
| `SCRAPE_LIMIT` | No | Max solicitations to process (for testing) |

## Deployment

### Build and push Docker image

```bash
docker buildx build --platform linux/amd64 -t collinschreyer/srt-rag-usai:latest --push .
```

### Deploy to cloud.gov

```bash
cf push -f manifest.yml
```

### Set environment variables (first time only)

```bash
cf set-env srt-rag-usai-dev USAI_API "your-usai-api-key"
cf set-env srt-rag-usai-dev SAM_API_KEY "your-sam-api-key"
cf set-env srt-rag-usai-dev USAI_BASE_URL "https://api.gsa.usai.gov/api/v1"
cf restage srt-rag-usai-dev
```

### Backfill a date range

```bash
cf set-env srt-rag-usai-dev SCRAPE_FROM_DATE "2026-03-24"
cf set-env srt-rag-usai-dev SCRAPE_TO_DATE "2026-03-30"
cf restage srt-rag-usai-dev
```

Then unset the overrides so cron defaults to yesterday:

```bash
cf unset-env srt-rag-usai-dev SCRAPE_FROM_DATE
cf unset-env srt-rag-usai-dev SCRAPE_TO_DATE
```

## Monitoring

The container exposes a health check server with these endpoints:

| Endpoint | Description |
|----------|-------------|
| `/health` | Health check (JSON) |
| `/output` | Full pipeline log (startup run + cron runs) |
| `/csv` | Latest CSV output |
| `/attachments` | List of downloaded attachment folders |

Access at: `https://srt-rag-usai-dev.app.cloud.gov/`

### Logs

```bash
cf logs srt-rag-usai-dev --recent
```

### Database queries

```sql
-- All solicitations analyzed today
SELECT solicitation_number, ai_applicable, ai_compliant,
       ai_overall_risk_level, ai_solicitation_explanation,
       total_files, total_matches
FROM "rag-solicitations"
WHERE updated_at::date = CURRENT_DATE;

-- Per-file results for a solicitation
SELECT d.file_name, d.is_508_applicable, d.is_compliant,
       d.matches_found, d.match_strength
FROM "rag-documents" d
JOIN "rag-solicitations" s ON d.solicitation_id = s.id
WHERE s.solicitation_number = 'YOUR_SOL_NUMBER';
```

## Daily Schedule

The cron job runs at **6:00 AM UTC** daily. It:
1. Scrapes yesterday's solicitations from SAM.gov
2. Filters to ICT-relevant NAICS codes
3. Downloads attachments for solicitations that have them
4. Runs the 7-stage analysis on every file
5. Writes results to PostgreSQL and CSV

Typical daily volume: ~150-200 solicitations posted, ~10-30 match ICT NAICS codes, ~5-15 have downloadable attachments.

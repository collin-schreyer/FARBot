# Answers to Laura's Questions

---

## Q: How do we check for National Security Systems? Do we use the definition of National Security Systems and have the AI determine if those definitions apply (and therefore that Section 508 is not applied)?

**A:** The current pipeline does not check for National Security Systems exclusions. The NAICS code filter and the LLM applicability prompt do not include logic to identify or exclude National Security Systems.

This could be added. The approach would be to include the definition of National Security Systems (per 44 U.S.C. § 3552) in the Stage 2 applicability prompt as an additional exclusion rule. The LLM would then evaluate whether the solicitation falls under that definition and exclude it from 508 requirements if so.

---

## Q: Do we check for ICT functions located in Maintenance and monitoring spaces? And if so, what are the parameters we set to determine that?

**A:** The current pipeline does not specifically check for the Section 508 exception for ICT located in maintenance and monitoring spaces.

The Stage 2 applicability prompt includes a general exclusion for "physical repair/maintenance of structures (roofing, plumbing, HVAC ducting)" but this does not address the specific 508 exception under E202.5 for ICT functions located in spaces that are frequented only by service personnel for maintenance, repair, or occasional monitoring of equipment.

This could be added to the prompt. The parameters would need to define what constitutes a "maintenance and monitoring space" in the context of the solicitation language — for example, looking for references to server rooms, equipment closets, or monitoring stations that are not accessed by the general public or employees performing typical job functions.

---

## Q: Are fundamental alteration exceptions and undue burden exceptions called out in the SRT tool?

**A:** Not currently, and this is intentional for the solicitation review stage — but this is a great idea and something we should definitely explore adding.

Right now, the SRT tool reviews solicitations before responses are submitted. At this point in the procurement process:
- **Fundamental alteration** (E202.6) — A vendor would claim this when responding, arguing that making their product accessible would fundamentally alter its nature. This isn't something that typically appears in the solicitation itself.
- **Undue burden** (E202.6) — Similarly, this is claimed by the agency or vendor when the cost of accessibility would be an undue burden. This determination happens after reviewing what's available in the market, not at the solicitation drafting stage.

The SRT tool's current purpose is to ensure solicitations contain the required 508 language. Whether exceptions apply comes later in the procurement lifecycle.

That said, there's real value in having the tool flag when a solicitation might be a candidate for these exceptions — for example, if the procurement involves highly specialized equipment where accessible alternatives may not exist. This could help agencies proactively plan for exception documentation rather than discovering it late in the process. This is something we can build into the pipeline as we expand its capabilities.

---

## Q: Is it scanning the Product Service code or the NAICS code to determine if it's ICT products or ICT services?

**A:** NAICS codes are the primary filter. Product Service Codes (PSCs) exist in the codebase but are not active in normal operation.

The production scraper filters solicitations using the `opportunity_filter_function` which checks: `psc_match or naics_match`. However, the PSC code list defaults to empty (`psc_codes = []`), so in practice only NAICS codes are used for filtering. PSC filtering was built for an EPA-specific demo mode and can be activated by calling `set_psc_code_download_list()` with a list of PSC codes, but this is not enabled in the current daily production run.

The pipeline queries SAM.gov for all new solicitations and filters them by NAICS code prefix to identify ICT-related procurements. The specific NAICS codes used are (verified in both `srt-fbo-scraper/src/fbo_scraper/sam_utils.py` and `srt-rag-usai/sam_scraper.py`):

- 334111 — Electronic computer manufacturing
- 334118 — Computer terminal and peripheral equipment
- 3343 — Audio and video equipment
- 33451 — Navigational, measuring, electromedical instruments
- 334516 — Analytical laboratory instrument manufacturing
- 334614 — Software and prerecorded media reproducing
- 5112 — Software publishers
- 518 — Data processing, hosting, and related services
- 54169 — Other scientific and technical consulting services
- 54121 — Computer systems design and related services
- 5415 — Computer systems design and related services
- 61142 — Computer training

After NAICS filtering, the LLM performs deeper analysis of the actual document content to determine 508 applicability. The LLM is not constrained by the NAICS code — it reads the full document text and makes its own determination based on what's actually being procured.

---

## Q: Can you send me a text version of the prompt logic?

**A:** See the companion document `SRT_PROMPTS.md` which contains every LLM prompt used in the pipeline, exactly as they appear in the code. The prompts cover:

1. **508 Applicability** — Determines if Section 508 applies to the document
2. **ICT Classification** — Identifies what types of ICT are being procured
3. **Vector Match Analysis** — Validates whether text matches to 508 standards are meaningful
4. **Document Summary** — Generates a factual description of the solicitation
5. **Solicitation Summary** — Summarizes the full solicitation package across all files

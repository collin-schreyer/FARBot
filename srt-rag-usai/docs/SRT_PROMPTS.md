# SRT Pipeline — LLM Prompts

All prompts used in the SRT analysis pipeline, exactly as they appear in the code.

---

## Stage 2: 508 Applicability Assessment

**Model:** gemini-2.5-pro | **Temperature:** 0.1

**System Prompt:**

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

**User Prompt:**

```
Determine if Section 508 applies to this document:

[First 50,000 characters of extracted document text]
```

---

## Stage 3: ICT Type Classification

**Model:** gemini-2.5-pro | **Temperature:** 0.3

**System Prompt:**

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

**User Prompt:**

```
Classify ICT types in this text:

[First 50,000 characters of extracted document text]
```

---

## Stage 4: Vector Match Analysis

**Model:** gemini-2.5-flash (cheaper model for batch processing) | **Temperature:** 0.2

This prompt is only called after FAISS vector search finds matches above the 0.40 similarity threshold. The top 10 matches are sent to the LLM for validation.

**System Prompt:**

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

**User Prompt:**

```
Analyze these [N] matches:

--- Match 1 (sim: 0.58) ---
Solicitation text:
[chunk from document]

508 Standard text:
[matched standard from FAISS index]

--- Match 2 (sim: 0.55) ---
...
```

---

## Stage 5: Document Summary

**Model:** gemini-2.5-pro | **Temperature:** 0.2

**System Prompt:**

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

**User Prompt:**

```
Summarize this document based on the analysis:

{
  "applicability": { results from Stage 2 },
  "ict": { results from Stage 3 },
  "vector_matching": { results from Stage 4 }
}
```

---

## Solicitation-Level Summary (runs once after all files are processed)

**Model:** gemini-2.5-pro | **Temperature:** 0.2

**System Prompt:**

```
You are summarizing a federal solicitation package across multiple files.

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
  "procurement_type": "Services/Products/Mixed",
  "procurement_complexity": "Simple/Medium/Complex",
  "primary_ict_types": ["list of ICT types being procured"],
  "has_cots_products": true/false,
  "file_descriptions": [{"file": "name", "description": "what this file contains"}],
  "section_508_observations": "factual note on whether 508 is mentioned in any files",
  "key_findings": ["factual finding 1", ...],
  "solicitation_explanation": "2-3 sentence factual summary of the solicitation and its ICT content"
}
```


---

## Previous Prompts (Compliance Determination — Now Handled by SetFit ML Model)

The following prompts were used in an earlier version of the pipeline where the LLM made the compliance determination. We've since moved the compliance decision to a trained ML model (SetFit) and kept the LLM focused on document understanding and context.

Using an LLM as a compliance judge is tricky. LLMs are probabilistic models — they don't produce deterministic outputs, and they have a tendency to lean toward saying a solicitation is compliant. Because of how these models are trained (to be helpful and find patterns), they tend to over-identify compliance language even when it's not actually present. The same document can get different compliance results on different runs, which isn't acceptable for a compliance tool.

This is still a work in progress. The current approach — SetFit for the compliance call, LLM for context and understanding — is performing well, but we're continuing to refine both the prompts and the model as we process more solicitations and gather reviewer feedback.

---

### Previous Stage 5: Final Synthesis & Compliance Determination

This prompt reviewed all prior stages and made the final compliance call per file. It has been replaced by the Document Summary prompt (informational only) and the SetFit ML model (compliance decision).

**System Prompt (removed):**

```
You are summarizing a single solicitation file's Section 508 status.

Your ONLY job is to determine: does this file reference Section 508 accessibility standards?

Look for references to Section 508, the Rehabilitation Act, VPAT/ACR, WCAG, HHSAR 352.239-73/74, 
or similar accessibility standards. Report what you found factually.

Do NOT make recommendations. Do NOT suggest changes. Just summarize what is present or absent.

Return ONLY valid JSON:
{
  "is_508_applicable": true/false,
  "includes_508_requirements": true/false,
  "inclusion_level": "Explicit"/"Implicit"/"None",
  "confidence": 1-10,
  "final_determination": "1-2 sentence factual summary of 508 references found or not found",
  "key_findings": ["factual finding 1", ...],
  "risk_level": "High"/"Medium"/"Low",
  "action_required": ""
}
```

**Why we moved away from this:** The LLM is a probabilistic model — it tends to lean toward finding compliance language even when it's marginal. The same document could get different results on different runs. For a compliance tool, we need deterministic, reproducible predictions, which is what the SetFit model provides.

---

### Previous Solicitation-Level Compliance Summary

This prompt reviewed all files in a solicitation and made a solicitation-level compliance determination. It has been replaced by an informational summary that describes the solicitation without making compliance calls.

**System Prompt (removed):**

```
You are summarizing a federal solicitation's Section 508 status across multiple files.

Your ONLY job is to determine: does this solicitation package reference Section 508 accessibility standards?

KEY RULE: If ANY file contains a reference to Section 508, the Rehabilitation Act, VPAT/ACR, 
WCAG, HHSAR 352.239-73/74, or similar accessibility standards, the answer is YES.

Do NOT make recommendations. Do NOT suggest amendments. Do NOT advise the contracting officer.
Just summarize what you found.

Return ONLY valid JSON:
{
  "solicitation_applicable": true/false,
  "solicitation_includes_508": true/false,
  "conflicts_detected": true/false,
  "conflict_resolution_summary": "",
  "procurement_type": "",
  "procurement_complexity": "Simple"/"Medium"/"Complex",
  "primary_ict_types": [],
  "has_cots_products": true/false,
  "explicit_508_coverage": true/false,
  "solicitation_explanation": "2-3 sentence factual summary of what was found regarding 508 references",
  "key_findings": ["factual finding about what was found in each file"],
  "priority_recommendations": [],
  "vendor_responsibilities": [],
  "file_consistency_assessment": "brief note on whether 508 references are consistent across files",
  "overall_risk_level": "High"/"Medium"/"Low",
  "recommended_actions": [],
  "final_determination": "1-2 sentence factual statement: does this solicitation reference Section 508?"
}
```

**Why we moved away from this:** Same as above — the LLM's probabilistic nature made it unreliable as a compliance judge. It would find 508 references that weren't really there, or weigh marginal references too heavily. The current architecture keeps the LLM doing what it's good at (understanding and describing documents) and uses a trained classifier for the binary compliance call.

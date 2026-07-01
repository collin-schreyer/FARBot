import { converseJson, converseText, parseJson } from "@/lib/bedrock";
import type { FarHit } from "@/lib/farRetrieval";

// Issue-area registry — the Topic Pack seeds. Port of ISSUE_AREAS in
// srt-rag-usai/solicitation_review.py.
export type IssueArea = {
  id: string;
  label: string;
  keywords: string[];
  farQuery: string;
};

export const ISSUE_AREAS: IssueArea[] = [
  {
    id: "section_508",
    label: "Section 508 / ICT Accessibility",
    keywords: ["508", "accessibility", "vpat", "wcag", "acr", "accessible", "screen reader", "rehabilitation act", "ict"],
    farQuery: "Section 508 accessibility standards for information and communication technology",
  },
  {
    id: "cybersecurity",
    label: "Cybersecurity / Information Protection",
    keywords: ["cybersecurity", "cyber", "nist 800-171", "cmmc", "cui", "controlled unclassified", "fedramp", "security control", "supply chain", "52.204-21", "information system"],
    farQuery: "cybersecurity safeguarding covered contractor information systems controlled unclassified information",
  },
  {
    id: "agency_deviation",
    label: "Agency Acquisition-Regulation Deviations",
    keywords: ["hhsar", "vaar", "dfars", "gsam", "agency supplement", "deviation", "class deviation"],
    farQuery: "agency FAR supplement deviations acquisition regulation clauses",
  },
  {
    id: "small_business",
    label: "Small Business / Set-Asides",
    keywords: ["small business", "set-aside", "set aside", "8(a)", "hubzone", "sdvosb", "wosb", "socioeconomic", "subcontracting plan"],
    farQuery: "small business set-aside programs socioeconomic subcontracting",
  },
  {
    id: "privacy",
    label: "Privacy / PII Handling",
    keywords: ["privacy act", "pii", "personally identifiable", "system of records", "privacy impact", "safeguarding personal"],
    farQuery: "Privacy Act handling of personally identifiable information system of records",
  },
  {
    id: "labor_standards",
    label: "Labor Standards",
    keywords: ["service contract act", "sca", "wage determination", "davis-bacon", "prevailing wage", "fair labor"],
    farQuery: "Service Contract Labor Standards wage determination prevailing wage",
  },
];

export type DetectedArea = {
  id: string;
  label: string;
  confidence: "high" | "medium" | "low";
  evidence: string[];
  method: "llm" | "keyword";
};

export function inferIssueAreasKeyword(text: string): DetectedArea[] {
  const low = text.toLowerCase();
  const out: DetectedArea[] = [];
  for (const area of ISSUE_AREAS) {
    const hits = [...new Set(area.keywords.filter((kw) => low.includes(kw)))].sort();
    if (hits.length) {
      const confidence = hits.length >= 3 ? "high" : hits.length === 2 ? "medium" : "low";
      out.push({ id: area.id, label: area.label, confidence, evidence: hits, method: "keyword" });
    }
  }
  return out;
}

export async function inferIssueAreas(text: string): Promise<DetectedArea[]> {
  const catalog = ISSUE_AREAS.map((a) => `- ${a.id}: ${a.label}`).join("\n");
  const system =
    "You are a federal acquisition analyst. Given solicitation text, decide which regulatory " +
    "issue areas a contracting officer should review. Only mark an area applicable if the " +
    "solicitation's subject matter actually implicates it — not because a term is mentioned in " +
    `passing.\n\nIssue areas:\n${catalog}\n\n` +
    'Return ONLY valid JSON: {"areas":[{"id":"<id>","applicable":true|false,"confidence":"high|medium|low","reasoning":"one sentence"}]}';
  try {
    const result = await converseJson<{
      areas: { id: string; applicable: boolean; confidence?: string; reasoning?: string }[];
    }>(system, `Solicitation text:\n\n${text.slice(0, 50000)}`, { maxTokens: 1200 });
    const byId = new Map(ISSUE_AREAS.map((a) => [a.id, a]));
    const out: DetectedArea[] = [];
    for (const a of result?.areas ?? []) {
      if (a.applicable && byId.has(a.id)) {
        out.push({
          id: a.id,
          label: byId.get(a.id)!.label,
          confidence: (a.confidence as DetectedArea["confidence"]) ?? "medium",
          evidence: [a.reasoning ?? ""],
          method: "llm",
        });
      }
    }
    if (out.length) return out;
  } catch {
    /* fall through to keyword */
  }
  return inferIssueAreasKeyword(text);
}

function suggestTemplate(area: IssueArea, farHits: FarHit[]): string[] {
  const cites =
    farHits.slice(0, 4).map((h) => `FAR ${h.section}`).join(", ") || "the governing FAR sections";
  return [
    `This solicitation appears to implicate ${area.label}. Have you confirmed the requirements in ${cites}?`,
    `Does the draft include the clauses prescribed for ${area.label}, or state why they don't apply?`,
    `Is there anything the reviewer needs from you to assess ${area.label} (system type, data handled, agency)?`,
  ];
}

export async function suggestQuestions(
  area: IssueArea,
  farHits: FarHit[],
  docText: string,
): Promise<string[]> {
  const farContext = farHits
    .slice(0, 8)
    .map((h) => `- FAR ${h.section} (${h.title})` + (h.text ? ` [${h.text.slice(0, 300)}]` : ""))
    .join("\n");
  const system =
    `You are helping a contracting officer draft a compliant solicitation. Focus area: ${area.label}. ` +
    "Using the retrieved FAR context, produce the questions the officer should be asking but may not " +
    "know to ask, and the concrete things to check in the draft. Be specific and cite FAR sections. " +
    "This is prescriptive guidance — the AI prompting the user, not answering a question.\n\n" +
    'Return ONLY valid JSON: {"suggestions":["...","..."]}';
  const user = `Retrieved FAR context:\n${farContext}\n\nSolicitation excerpt:\n${docText.slice(0, 6000)}`;
  try {
    const text = await converseText(system, user, { maxTokens: 1500, temperature: 0.2 });
    const result = parseJson<{ suggestions?: string[] }>(text);
    if (result?.suggestions?.length) return result.suggestions;
  } catch {
    /* fall through to template */
  }
  return suggestTemplate(area, farHits);
}

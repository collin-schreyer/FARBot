import { retrieveFar, type FarHit } from "@/lib/farRetrieval";
import {
  ISSUE_AREAS,
  inferIssueAreas,
  suggestQuestions,
  type DetectedArea,
} from "@/lib/issueAreas";
import {
  agencySuggestions,
  deviationsFor,
  matchAgency,
  type Deviation,
} from "@/lib/agency";

// The blended review — port of srt-rag-usai/solicitation_review.py's
// review_package, but the per-area fan-out runs in parallel (fixes the serial
// Bedrock throttling we hit in Python).
export type AreaReview = {
  id: string;
  label: string;
  farSections: { section: string; title: string; source: string; via?: string }[];
  suggestions: string[];
  agencyDeviations?: { agency: string; suggestions: string[] };
};

export type ReviewResult = {
  chars: number;
  inferenceMethod: "llm" | "keyword";
  agency: string | null;
  agencyLayer: {
    agency: string;
    source: string;
    deviationCount: number;
    deviations: Deviation[];
    suggestions: string[];
  } | null;
  issueAreas: DetectedArea[];
  reviews: AreaReview[];
};

export async function reviewPackage(text: string, agency?: string): Promise<ReviewResult> {
  const areas = await inferIssueAreas(text);

  const reviews = await Promise.all(
    areas.map(async (a): Promise<AreaReview> => {
      const def = ISSUE_AREAS.find((x) => x.id === a.id)!;
      let hits: FarHit[] = [];
      try {
        hits = await retrieveFar(def.farQuery, 6);
      } catch {
        hits = [];
      }
      const suggestions = await suggestQuestions(def, hits, text);
      return {
        id: a.id,
        label: a.label,
        farSections: hits.map((h) => ({
          section: h.section,
          title: h.title,
          source: h.source,
          via: h.via,
        })),
        suggestions,
      };
    }),
  );

  // Agency scoping: layer the acquiring agency's deviations on top.
  const agencyKey = agency ? matchAgency(agency) : matchAgency(text);
  const devs = deviationsFor(agencyKey);
  let agencyLayer: ReviewResult["agencyLayer"] = null;
  if (agencyKey && devs.length) {
    const suggestions = agencySuggestions(agencyKey, devs);
    agencyLayer = {
      agency: agencyKey,
      source: agency ? "explicit" : "detected from text",
      deviationCount: devs.length,
      deviations: devs,
      suggestions,
    };
    const five08 = reviews.find((r) => r.id === "section_508");
    if (five08) five08.agencyDeviations = { agency: agencyKey, suggestions };
  }

  return {
    chars: text.length,
    inferenceMethod: areas[0]?.method ?? "llm",
    agency: agencyKey,
    agencyLayer,
    issueAreas: areas,
    reviews,
  };
}

import agencyData from "@/data/agency_deviations.json";

// Agency scoping — layer the acquiring agency's acquisition-regulation
// deviations (508/ACR supplements) onto the review. Port of srt-rag-usai/
// agency_packs.py. Data: SRT ACR Repo Agency Expansion workbook -> JSON.
export type Deviation = {
  part: string;
  section: string;
  language: string;
  requirement: string;
  vpat_acr_mention: string;
  vpat_acr_required: string;
  remediation_required: string;
  deliverables_508_required: string;
};

const AGENCIES = (agencyData as { agencies: Record<string, Deviation[]> }).agencies;

// Canonical agency key -> match aliases. Supplement acronyms are strongest;
// bare abbreviations match on word boundaries so "va" doesn't hit "evaluation".
const ALIASES: Record<string, { strong: string[]; name: string[]; abbr: string[] }> = {
  "HHS (HHSAR)": { strong: ["hhsar"], name: ["health and human services", "department of health"], abbr: ["hhs"] },
  "Transportation (TAR)": { strong: ["tar "], name: ["department of transportation", "transportation"], abbr: ["dot"] },
  "Veterans Affairs (VAAR)": { strong: ["vaar"], name: ["veterans affairs", "veterans administration"], abbr: ["va"] },
  "USAID (AIDAR)": { strong: ["aidar"], name: ["agency for international development", "usaid"], abbr: [] },
  "Department of Labor (DOLAR)": { strong: ["dolar"], name: ["department of labor"], abbr: ["dol"] },
  "Defense Logistics Aquisition Directive (DLAD)": { strong: ["dlad"], name: ["defense logistics"], abbr: ["dla"] },
  "Department of Treasury (DTAR)": { strong: ["dtar"], name: ["department of treasury", "treasury"], abbr: [] },
  EPA: { strong: [], name: ["environmental protection agency"], abbr: ["epa"] },
  "Defense (DARS)": { strong: ["dars", "dfars"], name: ["department of defense"], abbr: ["dod"] },
  "Army (AFARS)": { strong: ["afars"], name: ["department of the army", "u.s. army", "us army"], abbr: ["army"] },
  "Commerce (CAR)": { strong: [], name: ["department of commerce", "commerce"], abbr: [] },
};

export function agencyList(): string[] {
  return Object.keys(AGENCIES).sort();
}

export function matchAgency(nameOrText: string | null | undefined): string | null {
  if (!nameOrText) return null;
  const low = nameOrText.toLowerCase();
  let best: string | null = null;
  let bestScore = 0;
  for (const [key, al] of Object.entries(ALIASES)) {
    let score = 0;
    for (const s of al.strong) if (low.includes(s)) score += 5;
    for (const n of al.name) if (low.includes(n)) score += 3;
    for (const a of al.abbr) {
      const re = new RegExp(`\\b${a.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`);
      if (re.test(low)) score += 1;
    }
    if (score > bestScore) {
      best = key;
      bestScore = score;
    }
  }
  return bestScore > 0 ? best : null;
}

export function deviationsFor(agencyKey: string | null): Deviation[] {
  if (!agencyKey) return [];
  if (AGENCIES[agencyKey]) return AGENCIES[agencyKey];
  const canon = matchAgency(agencyKey);
  return canon ? AGENCIES[canon] ?? [] : [];
}

function relevance508(d: Deviation): number {
  let score = 0;
  if (d.vpat_acr_required === "y") score += 3;
  if (d.deliverables_508_required === "y") score += 2;
  if (d.remediation_required === "y") score += 2;
  if (d.vpat_acr_mention === "y") score += 1;
  const blob = `${d.section} ${d.language}`.toLowerCase();
  if (/508|accessib|vpat|acr|electronic and information|information and communication|\beit|\(eit/.test(blob))
    score += 2;
  return score;
}

export function agencySuggestions(agencyKey: string, devs: Deviation[]): string[] {
  if (!devs.length) return [];
  const ranked = [...devs].sort((a, b) => relevance508(b) - relevance508(a));
  const out = [
    `This is a ${agencyKey} acquisition — FAR is the baseline, but the agency supplement adds requirements the FAR-level review won't surface on its own:`,
  ];
  for (const d of ranked.slice(0, 6)) {
    const bits: string[] = [];
    if (d.vpat_acr_required === "y") bits.push("requires a VPAT/ACR");
    if (d.remediation_required === "y") bits.push("requires remediation");
    if (d.deliverables_508_required === "y") bits.push("deliverables must be 508-conformant");
    const extra = bits.length ? ` — ${bits.join(", ")}` : "";
    const sec = d.section || d.part;
    out.push(`Confirm ${sec}${extra}. (${d.requirement || d.language.slice(0, 80)})`);
  }
  return out;
}

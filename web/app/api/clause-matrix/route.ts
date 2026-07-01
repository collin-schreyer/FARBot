import { NextRequest } from "next/server";
import {
  BedrockAgentRuntimeClient,
  RetrieveCommand,
} from "@aws-sdk/client-bedrock-agent-runtime";
import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";
import { candidatesForSections, addClauseCandidate, titleOf, type Candidate } from "@/lib/graph";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const REGION = process.env.AWS_REGION ?? "us-east-1";
const agent = new BedrockAgentRuntimeClient({ region: REGION });
const bedrock = new BedrockRuntimeClient({ region: REGION });

type Attrs = {
  contractType?: string;
  commercial?: string;
  supplyService?: string;
  value?: string;
  setAside?: string;
  agency?: string;
};
type RawClause = { clause?: string; status?: string; reason?: string; prescribedBy?: string };

function profileLines(a: Attrs): string {
  return (
    [
      ["Contract type", a.contractType],
      ["Commercial status", a.commercial],
      ["Supplies or services", a.supplyService],
      ["Estimated value", a.value],
      ["Set-aside", a.setAside],
      ["Agency", a.agency],
    ] as [string, string | undefined][]
  )
    .filter(([, v]) => v)
    .map(([k, v]) => `- ${k}: ${v}`)
    .join("\n");
}

function retrievalQuery(a: Attrs): string {
  return [
    a.commercial,
    a.supplyService,
    "acquisition",
    a.contractType,
    a.value ? `estimated value ${a.value}` : "",
    a.setAside && a.setAside !== "None" ? `${a.setAside} set-aside` : "",
    a.agency,
    "required FAR solicitation provisions and contract clauses",
  ]
    .filter(Boolean)
    .join(", ");
}

function parseJsonLoose(text: string): { clauses?: RawClause[] } | null {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const body = fenced ? fenced[1] : text;
  const s = body.indexOf("{");
  const e = body.lastIndexOf("}");
  if (s >= 0 && e > s) {
    try {
      return JSON.parse(body.slice(s, e + 1));
    } catch {
      return null;
    }
  }
  return null;
}

export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as { attributes?: Attrs };
  const a: Attrs = body.attributes ?? {};
  const kbId = process.env.FAR_KB_ID;
  const modelArn = process.env.BEDROCK_MODEL_ARN;
  if (!kbId || !modelArn) {
    return Response.json({ error: "Knowledge Base not configured" }, { status: 503 });
  }

  const t0 = Date.now();

  // 1 — retrieve relevant FAR sections (prescribing sections + policy)
  const rr = await agent.send(
    new RetrieveCommand({
      knowledgeBaseId: kbId,
      retrievalQuery: { text: retrievalQuery(a) },
      retrievalConfiguration: {
        vectorSearchConfiguration: { numberOfResults: 25, overrideSearchType: "HYBRID" },
      },
    }),
  );
  const sections: string[] = [];
  const snippets: string[] = [];
  for (const r of rr.retrievalResults ?? []) {
    const md = (r.metadata ?? {}) as Record<string, unknown>;
    const sec = String(md.section ?? "");
    if (sec && !sections.includes(sec)) {
      sections.push(sec);
      const sn = (r.content?.text ?? "").replace(/\s+/g, " ").slice(0, 220);
      if (sn) snippets.push(`${sec} (${titleOf(sec)}): ${sn}`);
    }
  }

  // 2 — candidate clauses from the graph (only these may be chosen)
  const candidates: Candidate[] = candidatesForSections(sections);
  for (const sec of sections) if (/^52\./.test(sec)) addClauseCandidate(candidates, sec);

  if (!candidates.length) {
    return Response.json({
      profile: a,
      retrievedSections: sections,
      candidateCount: 0,
      clauses: [],
      note: "No prescribed clauses mapped from the retrieved sections — try a more specific profile.",
      latencyMs: Date.now() - t0,
    });
  }

  // 3 — Claude judges applicability over the fixed candidate pool
  const system =
    "You are a U.S. federal contracting specialist who builds FAR clause matrices. " +
    "Given an acquisition profile and a fixed pool of candidate FAR Part 52 clauses (with their prescribing sections), " +
    "decide which apply. Only use clauses from the provided pool — never invent clause numbers. Be precise and conservative.";
  const user =
    `Acquisition profile:\n${profileLines(a)}\n\n` +
    `Relevant FAR policy excerpts:\n${snippets.slice(0, 14).join("\n")}\n\n` +
    `Candidate clauses (clause — title — prescribed in):\n` +
    candidates.map((c) => `- ${c.clause} — ${c.title} — prescribed in ${c.prescribedBy}`).join("\n") +
    `\n\nReturn ONLY JSON, no prose:\n` +
    `{"clauses":[{"clause":"52.xxx-x","status":"required|conditional","reason":"one sentence citing the prescribing section","prescribedBy":"x.xxx"}]}\n` +
    `Include only clauses that apply or may apply to THIS acquisition. Use "conditional" when applicability depends on a factor not fully specified. List required first.`;

  let raw: RawClause[] = [];
  try {
    const resp = await bedrock.send(
      new ConverseCommand({
        modelId: modelArn,
        system: [{ text: system }],
        messages: [{ role: "user", content: [{ text: user }] }],
        inferenceConfig: { maxTokens: 2500, temperature: 0 },
      }),
    );
    const text = resp.output?.message?.content?.[0]?.text ?? "";
    const parsed = parseJsonLoose(text);
    raw = Array.isArray(parsed?.clauses) ? (parsed!.clauses as RawClause[]) : [];
  } catch (e) {
    return Response.json({ error: e instanceof Error ? e.message : "model error" }, { status: 500 });
  }

  // 4 — keep only real candidates, enrich with title + link
  const pool = new Map(candidates.map((c) => [c.clause, c]));
  const clauses = raw
    .filter((c): c is RawClause & { clause: string } => Boolean(c?.clause && pool.has(c.clause)))
    .map((c) => {
      const cand = pool.get(c.clause)!;
      return {
        clause: c.clause,
        title: cand.title,
        status: c.status === "required" ? "required" : "conditional",
        reason: String(c.reason ?? ""),
        prescribedBy: cand.prescribedBy || String(c.prescribedBy ?? ""),
        url: `https://www.acquisition.gov/far/${c.clause}`,
      };
    })
    .sort((x, y) => (x.status === y.status ? 0 : x.status === "required" ? -1 : 1));

  return Response.json({
    profile: a,
    retrievedSections: sections,
    candidateCount: candidates.length,
    clauses,
    latencyMs: Date.now() - t0,
  });
}

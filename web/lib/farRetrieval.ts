import {
  BedrockAgentRuntimeClient,
  RetrieveCommand,
} from "@aws-sdk/client-bedrock-agent-runtime";
import { expandSections, titleOf } from "@/lib/graph";

// FAR retrieval for the review pipeline — the same Bedrock HYBRID + FAR-graph
// retrieval the chat route (app/api/ask/route.ts) uses, factored for reuse.
const REGION = process.env.AWS_REGION ?? "us-east-1";
const agent = new BedrockAgentRuntimeClient({ region: REGION });
const clean = (s: string) => s.replace(/\s+/g, " ").trim();

export type FarHit = {
  section: string;
  title: string;
  score: number | null;
  text: string;
  source: "semantic" | "graph";
  via?: string;
  from?: string;
};

export async function retrieveFar(query: string, topK = 6): Promise<FarHit[]> {
  const kbId = process.env.FAR_KB_ID;
  if (!kbId) return [];

  // 1 — semantic HYBRID retrieval
  const rr = await agent.send(
    new RetrieveCommand({
      knowledgeBaseId: kbId,
      retrievalQuery: { text: query },
      retrievalConfiguration: {
        vectorSearchConfiguration: { numberOfResults: topK, overrideSearchType: "HYBRID" },
      },
    }),
  );
  const semantic: FarHit[] = [];
  const seen = new Set<string>();
  for (const r of rr.retrievalResults ?? []) {
    const md = (r.metadata ?? {}) as Record<string, unknown>;
    const section = String(md.section ?? "");
    if (!section || seen.has(section)) continue;
    seen.add(section);
    const text = clean(r.content?.text ?? "");
    semantic.push({
      section,
      title: titleOf(section),
      score: r.score ?? null,
      text,
      source: "semantic",
    });
  }

  // 2 — expand along the FAR graph (prescriptions + cross-refs)
  const graph: FarHit[] = [];
  if (semantic.length) {
    const seed = semantic.slice(0, 8).map((c) => c.section);
    const expansions = expandSections(seed, 12);
    for (const e of expansions) {
      graph.push({
        section: e.section,
        title: titleOf(e.section),
        score: null,
        text: "",
        source: "graph",
        via: e.via,
        from: e.from,
      });
    }
  }
  return [...semantic, ...graph];
}

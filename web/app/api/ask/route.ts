import { NextRequest } from "next/server";
import { BedrockAgentRuntimeClient, RetrieveCommand } from "@aws-sdk/client-bedrock-agent-runtime";
import { BedrockRuntimeClient, ConverseStreamCommand } from "@aws-sdk/client-bedrock-runtime";
import { expandSections, subgraphFor, titleOf } from "@/lib/graph";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const REGION = process.env.AWS_REGION ?? "us-east-1";
const TOP_K = 12;
const agent = new BedrockAgentRuntimeClient({ region: REGION });
const bedrock = new BedrockRuntimeClient({ region: REGION });

const CITE = /\b(\d{1,2}\.\d{2,4}(?:-\d+)?)\b/g;
const clean = (s: string) => s.replace(/\s+/g, " ").trim();
const farUrl = (s: string) => (s ? `https://www.acquisition.gov/far/${s}` : "");

export async function POST(req: NextRequest) {
  const { question } = await req.json().catch(() => ({ question: "" }));
  if (!question || typeof question !== "string") {
    return new Response(JSON.stringify({ error: "missing question" }), { status: 400 });
  }
  const kbId = process.env.FAR_KB_ID;
  const modelArn = process.env.BEDROCK_MODEL_ARN;
  if (!kbId || !modelArn) {
    return new Response(JSON.stringify({ error: "Knowledge Base not configured" }), { status: 503 });
  }

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (o: unknown) => controller.enqueue(encoder.encode(JSON.stringify(o) + "\n"));
      const t0 = Date.now();
      try {
        send({
          t: "meta",
          v: { kb: kbId, model: modelArn.split("/").pop(), region: REGION, searchType: "HYBRID + graph", topK: TOP_K },
        });

        // 1 — semantic retrieval
        const rr = await agent.send(
          new RetrieveCommand({
            knowledgeBaseId: kbId,
            retrievalQuery: { text: question },
            retrievalConfiguration: {
              vectorSearchConfiguration: { numberOfResults: TOP_K, overrideSearchType: "HYBRID" },
            },
          }),
        );
        type Chunk = { section: string; title: string; score: number; snippet: string; text: string; source: string; via?: string; from?: string };
        const semantic: Chunk[] = [];
        for (const r of rr.retrievalResults ?? []) {
          const md = (r.metadata ?? {}) as Record<string, unknown>;
          const section = String(md.section ?? "");
          if (!section || semantic.some((c) => c.section === section)) continue;
          const text = clean(r.content?.text ?? "");
          semantic.push({ section, title: titleOf(section), score: r.score ?? 0, snippet: text.slice(0, 240), text, source: "semantic" });
        }

        // 2 — graph expansion along prescription / cross-reference edges
        const seed = semantic.slice(0, 8).map((c) => c.section);
        const expansions = expandSections(seed, 12);

        // 3 — fetch text for the graph-added sections (best-effort metadata filter)
        const graphChunks: Chunk[] = [];
        if (expansions.length) {
          const wantedSections = expansions.map((e) => e.section);
          let textBySection: Record<string, string> = {};
          try {
            const fr = await agent.send(
              new RetrieveCommand({
                knowledgeBaseId: kbId,
                retrievalQuery: { text: question },
                retrievalConfiguration: {
                  vectorSearchConfiguration: {
                    numberOfResults: Math.min(wantedSections.length, 20),
                    filter: { in: { key: "section", value: wantedSections } },
                  },
                },
              }),
            );
            for (const r of fr.retrievalResults ?? []) {
              const md = (r.metadata ?? {}) as Record<string, unknown>;
              const sec = String(md.section ?? "");
              if (sec) textBySection[sec] = clean(r.content?.text ?? "");
            }
          } catch {
            textBySection = {};
          }
          for (const e of expansions) {
            const text = textBySection[e.section] ?? "";
            graphChunks.push({
              section: e.section,
              title: titleOf(e.section),
              score: 0,
              snippet: text.slice(0, 200) || `(added via FAR graph — ${e.via} ${e.from})`,
              text,
              source: "graph",
              via: e.via,
              from: e.from,
            });
          }
        }

        send({
          t: "retrieval",
          v: [...semantic, ...graphChunks].map((c) => ({
            section: c.section,
            title: c.title,
            score: c.score,
            snippet: c.snippet,
            source: c.source,
            via: c.via,
            from: c.from,
          })),
        });

        // 4 — generate over the graph-expanded context
        const ctxParts = [
          ...semantic.map((c) => `[FAR ${c.section}] (${c.title})\n${c.text}`),
          ...graphChunks.filter((c) => c.text).map((c) => `[FAR ${c.section}] (${c.title}) — linked via FAR graph (${c.via})\n${c.text}`),
        ];
        const contextSections = new Set([...semantic, ...graphChunks].map((c) => c.section));

        const system =
          "You are an expert on the U.S. Federal Acquisition Regulation (FAR). Answer ONLY from the provided FAR context. " +
          "Cite the specific FAR section inline in the form 'FAR 19.507' or 'FAR 52.219-6' immediately after each claim it supports. " +
          "When a policy section prescribes a clause, name both. If the answer is not in the context, say so plainly.";
        const user = `Question: ${question}\n\nFAR context:\n${ctxParts.join("\n\n")}`;

        const resp = await bedrock.send(
          new ConverseStreamCommand({
            modelId: modelArn,
            system: [{ text: system }],
            messages: [{ role: "user", content: [{ text: user }] }],
            inferenceConfig: { maxTokens: 2200, temperature: 0 },
          }),
        );
        let full = "";
        for await (const ev of resp.stream ?? []) {
          const delta = ev.contentBlockDelta?.delta?.text;
          if (delta) {
            full += delta;
            send({ t: "text", v: delta });
          }
        }

        // 5 — citation subgraph from the sections the answer actually cited
        const cited: string[] = [];
        for (const m of full.matchAll(CITE)) {
          const sec = m[1];
          if (contextSections.has(sec) && !cited.includes(sec)) cited.push(sec);
        }
        if (cited.length) {
          const sg = subgraphFor(cited);
          send({
            t: "subgraph",
            v: {
              nodes: sg.nodes.map((n) => ({ ...n, url: farUrl(n.id), cited: cited.includes(n.id) })),
              links: sg.links,
            },
          });
        }

        send({
          t: "done",
          v: { latencyMs: Date.now() - t0, semantic: semantic.length, graphAdded: graphChunks.length, cited: cited.length },
        });
      } catch (err) {
        send({ t: "error", v: err instanceof Error ? err.message : "error" });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "application/x-ndjson; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
    },
  });
}

"use client";

import { useEffect, useRef, useState } from "react";
import { renderAnswerHtml } from "@/lib/citations";
import SubGraph from "@/components/SubGraph";
import BranchView from "@/components/BranchView";

type Meta = { kb: string; model: string; region: string; searchType: string; topK: number };
type Chunk = { section: string; title: string; score: number; snippet: string; source: string; via?: string; from?: string };
type SubNode = { id: string; title: string; part: string; url: string; cited: boolean };
type SubData = { nodes: SubNode[]; links: { source: string; target: string; type: string }[] };
type Stats = { latencyMs: number; semantic: number; graphAdded: number; cited: number };
type Turn = {
  question: string;
  answer: string;
  retrieval: Chunk[];
  subgraph: SubData | null;
  meta: Meta | null;
  stats: Stats | null;
  done: boolean;
};

const SAMPLES = [
  "When can I use sole source procurement?",
  "What clauses apply to a small business set-aside?",
  "How do I protest a contract award?",
  "What is required for a justification and approval (J&A)?",
];
const RET = 6;

export default function Home() {
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(0);
  const [showInspector, setShowInspector] = useState(true);
  const [retPage, setRetPage] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => setRetPage(0), [active]);

  function update(idx: number, fn: (t: Turn) => Turn) {
    setTurns((t) => t.map((turn, i) => (i === idx ? fn(turn) : turn)));
  }
  function stickToBottom() {
    const box = boxRef.current;
    if (!box) return;
    if (box.scrollHeight - box.scrollTop - box.clientHeight < 120) box.scrollTop = box.scrollHeight;
  }

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setBusy(true);
    setQ("");
    const idx = turns.length;
    setActive(idx);
    setTurns((t) => [...t, { question, answer: "", retrieval: [], subgraph: null, meta: null, stats: null, done: false }]);
    requestAnimationFrame(() => {
      const box = boxRef.current;
      if (box) box.scrollTop = box.scrollHeight;
    });

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok || !res.body) {
        const msg = await res.text().catch(() => "request failed");
        update(idx, (c) => ({ ...c, answer: `Error: ${msg}`, done: true }));
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          let ev: { t: string; v: unknown };
          try {
            ev = JSON.parse(line);
          } catch {
            continue;
          }
          if (ev.t === "text") update(idx, (c) => ({ ...c, answer: c.answer + (ev.v as string) }));
          else if (ev.t === "retrieval") update(idx, (c) => ({ ...c, retrieval: ev.v as Chunk[] }));
          else if (ev.t === "subgraph") update(idx, (c) => ({ ...c, subgraph: ev.v as SubData }));
          else if (ev.t === "meta") update(idx, (c) => ({ ...c, meta: ev.v as Meta }));
          else if (ev.t === "done") update(idx, (c) => ({ ...c, stats: ev.v as Stats }));
          else if (ev.t === "error") update(idx, (c) => ({ ...c, answer: c.answer + `\n\n*Error: ${ev.v as string}*` }));
        }
        stickToBottom();
      }
    } finally {
      update(idx, (c) => ({ ...c, done: true }));
      setBusy(false);
    }
  }

  const a = turns[active];
  const retrieval = a?.retrieval ?? [];
  const citedSet = new Set((a?.subgraph?.nodes ?? []).filter((n) => n.cited).map((n) => n.id));
  const maxScore = Math.max(0, ...retrieval.filter((c) => c.source === "semantic").map((c) => c.score));

  const titleBySection = new Map(retrieval.map((c) => [c.section, c.title]));
  const groupsMap = new Map<string, { seed: string; seedTitle: string; branches: { section: string; title: string; relation: string }[] }>();
  for (const c of retrieval) {
    if (c.source === "graph" && c.from) {
      if (!groupsMap.has(c.from)) groupsMap.set(c.from, { seed: c.from, seedTitle: titleBySection.get(c.from) ?? "", branches: [] });
      groupsMap.get(c.from)!.branches.push({ section: c.section, title: c.title, relation: c.via ?? "" });
    }
  }
  const groups = [...groupsMap.values()];

  const retPages = Math.max(1, Math.ceil(retrieval.length / RET));
  const page = Math.min(retPage, retPages - 1);
  const pageItems = retrieval.slice(page * RET, page * RET + RET);

  return (
    <div className="grid-container-widescreen usa-section">
      <div className="far-toolbar">
        <button
          type="button"
          className="usa-button usa-button--outline usa-button--small"
          onClick={() => setShowInspector((v) => !v)}
        >
          {showInspector ? "Hide pipeline inspector" : "Show pipeline inspector"}
        </button>
      </div>

      <div className={`far-layout${showInspector ? "" : " far-layout--full"}`}>
        <section className="far-chat">
          <div className="far-chat-box" ref={boxRef}>
            {turns.length === 0 ? (
              <div className="far-chat-empty">
                <h1 className="font-heading-lg margin-bottom-1">Federal Acquisition Regulation Assistant</h1>
                <p className="usa-intro measure-5">
                  Ask a question about the FAR. Retrieval is expanded along the FAR knowledge graph
                  (prescriptions &amp; cross-references), and each answer comes with a citation map.
                </p>
                <p className="text-bold margin-top-3 margin-bottom-1">Try asking</p>
                <ul className="usa-button-group">
                  {SAMPLES.map((s) => (
                    <li className="usa-button-group__item" key={s}>
                      <button type="button" className="usa-button usa-button--outline" onClick={() => ask(s)}>
                        {s}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              turns.map((t, i) => (
                <div key={i} className="far-turn">
                  <button
                    type="button"
                    className={`far-question${i === active ? " far-question--active" : ""}`}
                    onClick={() => setActive(i)}
                    title="Inspect this answer's pipeline"
                  >
                    {t.question}
                  </button>
                  <div
                    className={`far-answer usa-prose${!t.done ? " far-streaming" : ""}`}
                    dangerouslySetInnerHTML={{
                      __html:
                        renderAnswerHtml(t.answer) ||
                        (t.done ? "" : "<span class='text-base-light'>Searching the FAR graph…</span>"),
                    }}
                  />
                  {t.subgraph && t.subgraph.nodes.length > 0 && (
                    <div className="far-citemap">
                      <div className="far-citemap__head">
                        Citation map — {t.subgraph.nodes.filter((n) => n.cited).length} cited sections and their
                        FAR-graph links
                      </div>
                      <SubGraph nodes={t.subgraph.nodes} links={t.subgraph.links} />
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          <form
            className="usa-form usa-form--large far-chat-form"
            onSubmit={(e) => {
              e.preventDefault();
              ask(q);
            }}
          >
            <div className="display-flex flex-align-end">
              <input
                id="far-q"
                className="usa-input flex-fill margin-top-0"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Ask about the FAR…"
                autoComplete="off"
                aria-label="Your question"
              />
              <button type="submit" className="usa-button margin-left-1" disabled={busy}>
                {busy ? "Working…" : "Ask"}
              </button>
            </div>
          </form>
        </section>

        {showInspector && (
          <aside className="far-inspector" aria-label="GraphRAG pipeline inspector">
            <div className="far-insp-title">Pipeline inspector</div>
            {!a ? (
              <p className="far-insp-empty">Ask a question to see the GraphRAG pipeline.</p>
            ) : (
              <>
                <div className="far-insp-block">
                  <div className="far-insp-h">Configuration</div>
                  <dl className="far-kv">
                    <dt>Model</dt>
                    <dd className="far-mono">{a.meta?.model ?? "—"}</dd>
                    <dt>Retrieval</dt>
                    <dd>{a.meta?.searchType ?? "—"}</dd>
                    <dt>Latency</dt>
                    <dd>{a.stats ? `${(a.stats.latencyMs / 1000).toFixed(1)}s` : "…"}</dd>
                  </dl>
                </div>

                {groups.length > 0 && (
                  <div className="far-insp-block">
                    <div className="far-insp-h">
                      Graph expansion <span className="far-insp-count">semantic → graph</span>
                    </div>
                    <p className="far-branch-cap">
                      How each graph-added section branches off an initial semantic result.
                    </p>
                    <BranchView groups={groups} />
                    <div className="far-branch-legend">
                      <span><i style={{ background: "#e8731f" }} /> prescription</span>
                      <span><i style={{ background: "#3a7bbf" }} /> cross-reference</span>
                    </div>
                  </div>
                )}

                <div className="far-insp-block">
                  <div className="far-insp-h">
                    Retrieved chunks{" "}
                    <span className="far-insp-count">
                      {a.stats ? `${a.stats.semantic} semantic + ${a.stats.graphAdded} graph` : `${retrieval.length}`}
                    </span>
                  </div>
                  {retrieval.length === 0 ? (
                    <p className="far-insp-empty">Retrieving…</p>
                  ) : (
                    <>
                      {pageItems.map((c, idx) => {
                        const cited = citedSet.has(c.section);
                        const w = c.source === "semantic" && maxScore ? Math.round((c.score / maxScore) * 100) : 0;
                        return (
                          <div key={idx} className={`far-chunk${cited ? " far-chunk--cited" : ""}`}>
                            <div className="far-chunk__top">
                              <a
                                href={`https://www.acquisition.gov/far/${c.section}`}
                                target="_blank"
                                rel="noreferrer"
                                className="far-chunk__sec"
                              >
                                FAR {c.section}
                              </a>
                              <span className={`far-src far-src--${c.source}`}>{c.source}</span>
                              {cited && <span className="far-chunk__badge">cited</span>}
                            </div>
                            {c.source === "semantic" ? (
                              <div className="far-bar">
                                <div className="far-bar__fill" style={{ width: `${w}%` }} />
                              </div>
                            ) : (
                              <div className="far-chunk__via">via {c.via} {c.from}</div>
                            )}
                            {c.title && <div className="far-chunk__title">{c.title}</div>}
                            <div className="far-chunk__snip">{c.snippet}</div>
                          </div>
                        );
                      })}
                      {retPages > 1 && (
                        <div className="far-pager">
                          <button type="button" onClick={() => setRetPage(Math.max(0, page - 1))} disabled={page === 0}>
                            ‹
                          </button>
                          <span>
                            {page * RET + 1}–{Math.min(retrieval.length, page * RET + RET)} of {retrieval.length}
                          </span>
                          <button
                            type="button"
                            onClick={() => setRetPage(Math.min(retPages - 1, page + 1))}
                            disabled={page >= retPages - 1}
                          >
                            ›
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>

                <div className="far-insp-block">
                  <div className="far-insp-h">Generation</div>
                  <dl className="far-kv">
                    <dt>Cited sections</dt>
                    <dd>{a.stats?.cited ?? citedSet.size}</dd>
                    <dt>Knowledge Base</dt>
                    <dd className="far-mono">{a.meta?.kb ?? "—"}</dd>
                  </dl>
                </div>
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import dynamic from "next/dynamic";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false }) as unknown as ComponentType<any>;

type GNode = { id: string; part: string; title: string; clause: boolean; x?: number; y?: number };
type GLink = { source: string | GNode; target: string | GNode; type: string };
type Data = { nodes: GNode[]; links: GLink[] };

const sid = (v: string | GNode) => (typeof v === "object" ? v.id : v);

function partColor(part: string): string {
  const p = parseInt(part, 10) || 0;
  return `hsl(${(p * 53) % 360}, 62%, 52%)`;
}

export default function GraphPage() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 800, h: 600 });
  const [data, setData] = useState<Data | null>(null);
  const [part, setPart] = useState("all");
  const [showXref, setShowXref] = useState(true);
  const [showPresc, setShowPresc] = useState(true);
  const [selected, setSelected] = useState<GNode | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("/far_graph_viz.json")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ nodes: [], links: [] }));
  }, []);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setDims({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [data]);

  const parts = useMemo(
    () => (data ? Array.from(new Set(data.nodes.map((n) => n.part))).sort((a, b) => +a - +b) : []),
    [data],
  );

  const view = useMemo<Data>(() => {
    if (!data) return { nodes: [], links: [] };
    const nodes = part === "all" ? data.nodes : data.nodes.filter((n) => n.part === part);
    const ids = new Set(nodes.map((n) => n.id));
    const types = new Set<string>([...(showXref ? ["xref"] : []), ...(showPresc ? ["presc"] : [])]);
    const links = data.links
      .filter((l) => types.has(l.type) && ids.has(sid(l.source)) && ids.has(sid(l.target)))
      .map((l) => ({ source: sid(l.source), target: sid(l.target), type: l.type }));
    return { nodes, links };
  }, [data, part, showXref, showPresc]);

  const neighborIds = useMemo(() => {
    const s = new Set<string>();
    if (!selected) return s;
    for (const l of view.links) {
      if (sid(l.source) === selected.id) s.add(sid(l.target));
      if (sid(l.target) === selected.id) s.add(sid(l.source));
    }
    return s;
  }, [selected, view]);

  const neighbors = useMemo(() => {
    if (!selected) return [] as { id: string; rel: string }[];
    const out: { id: string; rel: string }[] = [];
    for (const l of view.links) {
      const s = sid(l.source);
      const t = sid(l.target);
      if (s === selected.id) out.push({ id: t, rel: l.type === "presc" ? "prescribed in" : "references" });
      else if (t === selected.id) out.push({ id: s, rel: l.type === "presc" ? "prescribes" : "referenced by" });
    }
    return out.slice(0, 40);
  }, [selected, view]);

  function runSearch() {
    if (!data) return;
    const q = search.trim();
    const hit = data.nodes.find((n) => n.id === q) ?? data.nodes.find((n) => n.id.startsWith(q));
    if (hit) {
      setPart("all");
      setSelected(hit);
    }
  }

  return (
    <div className="grid-container-widescreen usa-section">
      <h1 className="font-heading-xl margin-bottom-1">FAR knowledge graph</h1>
      <p className="usa-intro measure-5">
        Every FAR section is a node; edges are cross-references and clause prescriptions. Drag to explore,
        scroll to zoom, click a node to see what it links to.
      </p>

      <div className="far-graph-controls">
        <input
          className="usa-input far-graph-search"
          placeholder="Find a section, e.g. 52.219-6"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
        />
        <button type="button" className="usa-button usa-button--outline" onClick={runSearch}>
          Find
        </button>
        <select className="usa-select far-graph-part" value={part} onChange={(e) => setPart(e.target.value)}>
          <option value="all">All parts</option>
          {parts.map((p) => (
            <option key={p} value={p}>
              Part {p}
            </option>
          ))}
        </select>
        <label className="far-graph-toggle">
          <input type="checkbox" checked={showPresc} onChange={(e) => setShowPresc(e.target.checked)} />{" "}
          Prescriptions
        </label>
        <label className="far-graph-toggle">
          <input type="checkbox" checked={showXref} onChange={(e) => setShowXref(e.target.checked)} />{" "}
          Cross-references
        </label>
        <span className="far-graph-count">
          {view.nodes.length} nodes · {view.links.length} edges
        </span>
      </div>

      <div className="far-graph-stage" ref={wrapRef}>
        {!data ? (
          <div className="far-graph-loading">Loading the FAR graph…</div>
        ) : (
          <ForceGraph2D
            graphData={view}
            width={dims.w}
            height={dims.h}
            cooldownTicks={120}
            nodeRelSize={3}
            nodeVal={(n: GNode) => (n.clause ? 2.4 : 1)}
            nodeLabel={(n: GNode) => `${n.id} — ${n.title}`}
            nodeColor={(n: GNode) =>
              selected && n.id !== selected.id && !neighborIds.has(n.id)
                ? "rgba(140,140,150,0.18)"
                : partColor(n.part)
            }
            linkColor={(l: GLink) => {
              const on = selected && (sid(l.source) === selected.id || sid(l.target) === selected.id);
              if (selected && !on) return "rgba(150,150,150,0.05)";
              return l.type === "presc" ? "rgba(250,148,65,0.55)" : "rgba(120,140,170,0.22)";
            }}
            linkWidth={(l: GLink) => (l.type === "presc" ? 1.4 : 0.6)}
            onNodeClick={(n: GNode) => setSelected(n)}
            onBackgroundClick={() => setSelected(null)}
          />
        )}

        {selected && (
          <div className="far-graph-info">
            <button className="far-graph-info__close" onClick={() => setSelected(null)} aria-label="Close">
              ×
            </button>
            <div className="far-graph-info__id">
              <span className="far-graph-dot" style={{ background: partColor(selected.part) }} />
              FAR {selected.id}
            </div>
            <div className="far-graph-info__title">{selected.title}</div>
            <a
              className="usa-link usa-link--external far-graph-info__link"
              href={`https://www.acquisition.gov/far/${selected.id}`}
              target="_blank"
              rel="noreferrer"
            >
              Open on acquisition.gov
            </a>
            <div className="far-graph-info__rel">
              {neighbors.length === 0 ? (
                <span className="far-graph-info__none">No edges in the current view.</span>
              ) : (
                neighbors.map((nb, i) => (
                  <button
                    key={`${nb.id}-${i}`}
                    className="far-graph-neighbor"
                    onClick={() => {
                      const hit = data?.nodes.find((n) => n.id === nb.id);
                      if (hit) setSelected(hit);
                    }}
                  >
                    <span className="far-graph-neighbor__rel">{nb.rel}</span> {nb.id}
                  </button>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      <div className="far-graph-legend">
        <span><span className="far-graph-key" style={{ background: "rgba(250,148,65,0.8)" }} /> prescription edge</span>
        <span><span className="far-graph-key" style={{ background: "rgba(120,140,170,0.7)" }} /> cross-reference</span>
        <span>Node color = FAR part · larger nodes = Part 52 clauses</span>
      </div>
    </div>
  );
}

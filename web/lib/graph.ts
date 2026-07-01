import graphData from "@/data/far_graph.json";

type GraphIndex = {
  prescribes: Record<string, string[]>;
  prescribedBy: Record<string, string[]>;
  titles: Record<string, string>;
};
type GraphData = {
  meta: Record<string, number>;
  index: GraphIndex;
  edges: { crossReferences: [string, string][]; prescribedBy: [string, string][] };
};

const graph = graphData as unknown as GraphData;

export const graphMeta = graph.meta;

export function titleOf(section: string): string {
  return graph.index.titles[section] ?? "";
}
export function partOf(section: string): string {
  return section.split(".")[0] ?? "";
}
export function prescribingOf(clause: string): string {
  return (graph.index.prescribedBy[clause] ?? [])[0] ?? "";
}

// Cross-reference adjacency (both directions), built once at module load.
const xrefOut = new Map<string, string[]>();
const xrefIn = new Map<string, string[]>();
for (const [f, t] of graph.edges.crossReferences) {
  (xrefOut.get(f) ?? xrefOut.set(f, []).get(f)!).push(t);
  (xrefIn.get(t) ?? xrefIn.set(t, []).get(t)!).push(f);
}

// ---- clause-matrix candidate helpers (unchanged API) ----
export type Candidate = { clause: string; title: string; prescribedBy: string; prescribedByTitle: string };

export function candidatesForSections(sections: string[], cap = 60): Candidate[] {
  const out: Candidate[] = [];
  const seen = new Set<string>();
  for (const s of sections) {
    for (const c of graph.index.prescribes[s] ?? []) {
      if (seen.has(c)) continue;
      seen.add(c);
      out.push({ clause: c, title: titleOf(c), prescribedBy: s, prescribedByTitle: titleOf(s) });
      if (out.length >= cap) return out;
    }
  }
  return out;
}
export function addClauseCandidate(list: Candidate[], clause: string) {
  if (list.some((c) => c.clause === clause)) return;
  const pb = prescribingOf(clause);
  list.push({ clause, title: titleOf(clause), prescribedBy: pb, prescribedByTitle: titleOf(pb) });
}

// ---- GraphRAG expansion ----
export type Expansion = { section: string; via: string; from: string };

// Expand a seed set of retrieved sections along the graph: prescriptions first
// (highest value for the FAR — policy<->clause), then cross-references.
export function expandSections(seed: string[], maxAdd = 12): Expansion[] {
  const seen = new Set(seed);
  const added: Expansion[] = [];
  const push = (section: string, via: string, from: string) => {
    if (seen.has(section)) return;
    seen.add(section);
    added.push({ section, via, from });
  };
  for (const s of seed) {
    for (const sec of graph.index.prescribedBy[s] ?? []) push(sec, "prescribed by", s);
    for (const c of graph.index.prescribes[s] ?? []) push(c, "prescribes", s);
    if (added.length >= maxAdd) return added.slice(0, maxAdd);
  }
  for (const s of seed) {
    for (const t of xrefOut.get(s) ?? []) {
      push(t, "references", s);
      if (added.length >= maxAdd) return added.slice(0, maxAdd);
    }
  }
  return added.slice(0, maxAdd);
}

export type SubNode = { id: string; title: string; part: string };
export type SubLink = { source: string; target: string; type: string };

// The citation subgraph: the cited sections, their prescription partners, and the
// edges among them — small enough to render inline under an answer.
export function subgraphFor(sections: string[], maxNodes = 22): { nodes: SubNode[]; links: SubLink[] } {
  const cited = new Set(sections);
  const nodes = new Map<string, SubNode>();
  const add = (id: string) => {
    if (!nodes.has(id) && nodes.size < maxNodes) nodes.set(id, { id, title: titleOf(id), part: partOf(id) });
  };
  sections.forEach(add);

  const linkKey = new Set<string>();
  const links: SubLink[] = [];
  const link = (source: string, target: string, type: string) => {
    if (!nodes.has(source) || !nodes.has(target)) return;
    const k = `${source}|${target}|${type}`;
    if (linkKey.has(k)) return;
    linkKey.add(k);
    links.push({ source, target, type });
  };

  for (const s of sections) {
    for (const sec of graph.index.prescribedBy[s] ?? []) {
      add(sec);
      link(s, sec, "presc");
    }
    for (const c of graph.index.prescribes[s] ?? []) {
      if (cited.has(c)) {
        add(c);
        link(c, s, "presc");
      }
    }
  }
  for (const s of sections) {
    for (const t of xrefOut.get(s) ?? []) if (cited.has(t)) link(s, t, "xref");
  }

  return { nodes: [...nodes.values()], links };
}

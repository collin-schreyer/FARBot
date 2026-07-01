#!/usr/bin/env python3
"""Build the FAR knowledge graph from the corpus manifest + Part 52 prescriptions.

Nodes  : every FAR section (from kb_corpus/manifest.jsonl), with part/subpart/title.
Edges  :
  - crossReferences : section -> referenced section (from "see X.XXX" / <a class=xref>)
  - prescribedBy    : Part 52 clause -> the prescribing section ("As prescribed in X.XXX")

Plus lookup indexes that power the clause-matrix generator:
  - prescribes   : prescribing section -> [clauses it prescribes]
  - prescribedBy : clause -> [prescribing sections]
  - titles       : section -> title

Output: web/data/far_graph.json (imported by the Next.js clause-matrix route).
"""
import os
import re
import json
import glob
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DITA = os.path.join(REPO, "dita_html")
MANIFEST = os.path.join(REPO, "kb_corpus", "manifest.jsonl")
OUT_DIR = os.path.join(REPO, "web", "data")
OUT = os.path.join(OUT_DIR, "far_graph.json")

# "As prescribed in <section>, insert ..." — capture the section href after the phrase.
PRESC = re.compile(
    r'prescribed in(?:[^<]|<[^>]+>)*?<a[^>]+href="([0-9][^"#]*)\.html',
    re.IGNORECASE | re.DOTALL,
)


def extract_prescriptions():
    presc = {}
    for f in glob.glob(os.path.join(DITA, "52.*.html")):
        base = os.path.basename(f)[:-len(".html")]
        if not re.match(r"52\.\d", base):
            continue
        refs = PRESC.findall(open(f, encoding="utf-8").read())
        if refs:
            # keep order-stable unique prescribing sections
            seen, ordered = set(), []
            for r in refs:
                if r not in seen:
                    seen.add(r)
                    ordered.append(r)
            presc[base] = ordered
    return presc


def main():
    rows = [json.loads(l) for l in open(MANIFEST, encoding="utf-8") if l.strip()]

    nodes, ids, titles = [], set(), {}
    for r in rows:
        sec = r["section"]
        ids.add(sec)
        titles[sec] = r.get("title", "")
        nodes.append({
            "id": sec,
            "part": r.get("part", ""),
            "subpart": r.get("subpart", ""),
            "title": r.get("title", ""),
            "isClause": r.get("part") == "52",
        })

    cross = []
    for r in rows:
        for ref in r.get("cross_refs", []):
            cross.append([r["section"], ref])

    presc = extract_prescriptions()
    prescribed_by_edges = []
    prescribes = defaultdict(list)
    for clause, secs in presc.items():
        for s in secs:
            prescribed_by_edges.append([clause, s])
            prescribes[s].append(clause)

    graph = {
        "meta": {
            "nodes": len(nodes),
            "crossRefEdges": len(cross),
            "prescriptionEdges": len(prescribed_by_edges),
            "clausesWithPrescription": len(presc),
            "prescribingSections": len(prescribes),
        },
        "nodes": nodes,
        "edges": {"crossReferences": cross, "prescribedBy": prescribed_by_edges},
        "index": {
            "prescribes": {k: sorted(set(v)) for k, v in prescribes.items()},
            "prescribedBy": presc,
            "titles": titles,
        },
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False)

    # Viz-optimized subset for the client graph explorer (valid links only).
    VIZ = os.path.join(REPO, "web", "public", "far_graph_viz.json")
    idset = {n["id"] for n in nodes}
    viz_nodes = [
        {"id": n["id"], "part": n["part"], "title": n["title"], "clause": n["isClause"]}
        for n in nodes
    ]
    viz_links = []
    for frm, to in cross:
        if frm in idset and to in idset and frm != to:
            viz_links.append({"source": frm, "target": to, "type": "xref"})
    for clause, sec in prescribed_by_edges:
        if clause in idset and sec in idset and clause != sec:
            viz_links.append({"source": clause, "target": sec, "type": "presc"})
    os.makedirs(os.path.dirname(VIZ), exist_ok=True)
    with open(VIZ, "w", encoding="utf-8") as f:
        json.dump({"nodes": viz_nodes, "links": viz_links}, f, ensure_ascii=False)
    print(f"Viz: {len(viz_nodes)} nodes, {len(viz_links)} links -> {VIZ} ({os.path.getsize(VIZ)/1024:.0f} KB)")

    print(json.dumps(graph["meta"], indent=2))
    # spot-check: what does subpart 19.5 (small business set-asides) prescribe?
    for s in ("19.508", "19.708", "52.301"):
        cl = graph["index"]["prescribes"].get(s, [])
        print(f"  {s} prescribes {len(cl)} clauses: {cl[:6]}{'…' if len(cl) > 6 else ''}")
    size = os.path.getsize(OUT) / 1024
    print(f"Wrote {OUT} ({size:.0f} KB)")


if __name__ == "__main__":
    main()

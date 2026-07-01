"use client";

type SNode = { id: string; title: string; part: string; url: string; cited: boolean };
type SLink = { source: string; target: string; type: string };

function partColor(part: string): string {
  return `hsl(${((parseInt(part, 10) || 0) * 53) % 360}, 62%, 52%)`;
}

// Compact deterministic node-link diagram for an answer's citation map.
export default function SubGraph({ nodes, links }: { nodes: SNode[]; links: SLink[] }) {
  if (!nodes.length) return null;
  const W = 400;
  const H = Math.max(220, Math.min(360, 90 + nodes.length * 16));
  const cx = W / 2;
  const cy = H / 2;
  const R = Math.min(W, H) / 2 - 42;
  const pos: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n, i) => {
    const a = (i / nodes.length) * 2 * Math.PI - Math.PI / 2;
    pos[n.id] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
  });

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="far-subgraph" role="img" aria-label="Citation map">
      {links.map((l, i) => {
        const s = pos[l.source];
        const t = pos[l.target];
        if (!s || !t) return null;
        return (
          <line
            key={i}
            x1={s.x}
            y1={s.y}
            x2={t.x}
            y2={t.y}
            stroke={l.type === "presc" ? "#fa9441" : "#9fb3c8"}
            strokeWidth={l.type === "presc" ? 1.8 : 1}
            opacity={0.75}
          />
        );
      })}
      {nodes.map((n) => {
        const p = pos[n.id];
        return (
          <g
            key={n.id}
            transform={`translate(${p.x},${p.y})`}
            style={{ cursor: "pointer" }}
            onClick={() => window.open(n.url, "_blank", "noreferrer")}
          >
            <circle
              r={n.cited ? 7 : 5}
              fill={partColor(n.part)}
              stroke={n.cited ? "#1b1b1b" : "#ffffff"}
              strokeWidth={n.cited ? 1.6 : 1}
            />
            <text y={-11} textAnchor="middle" fontSize="9.5" fontWeight={n.cited ? 700 : 400} fill="#1b1b1b">
              {n.id}
            </text>
            <title>
              {n.id} — {n.title}
            </title>
          </g>
        );
      })}
    </svg>
  );
}

"use client";

type Branch = { section: string; title: string; relation: string };
type Group = { seed: string; seedTitle: string; branches: Branch[] };

const relColor = (r: string) => (r.includes("prescrib") ? "#e8731f" : "#3a7bbf");
const open = (s: string) => window.open(`https://www.acquisition.gov/far/${s}`, "_blank", "noreferrer");

// Horizontal bipartite diagram: semantic seed sections (left) branch out to the
// graph-expanded sections (right) along prescription / cross-reference edges.
export default function BranchView({ groups }: { groups: Group[] }) {
  const flat: { seed: string; b: Branch }[] = [];
  groups.forEach((g) => g.branches.forEach((b) => flat.push({ seed: g.seed, b })));
  if (!flat.length) return null;

  const rowH = 30;
  const padY = 16;
  const W = 360;
  const leftX = 70;
  const rightX = 286;
  const H = flat.length * rowH + padY * 2;

  const branchY = new Map<string, number>();
  flat.forEach((f, i) => branchY.set(f.seed + "|" + f.b.section, padY + i * rowH + rowH / 2));
  const seedY = new Map<string, number>();
  groups.forEach((g) => {
    const ys = g.branches.map((b) => branchY.get(g.seed + "|" + b.section)!);
    seedY.set(g.seed, ys.reduce((a, b) => a + b, 0) / ys.length);
  });

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="far-branch" role="img" aria-label="Graph expansion branches">
      {groups.flatMap((g) =>
        g.branches.map((b) => {
          const sy = seedY.get(g.seed)!;
          const by = branchY.get(g.seed + "|" + b.section)!;
          const mx = (leftX + rightX) / 2;
          return (
            <path
              key={g.seed + b.section}
              d={`M ${leftX} ${sy} C ${mx} ${sy}, ${mx} ${by}, ${rightX} ${by}`}
              fill="none"
              stroke={relColor(b.relation)}
              strokeWidth={1.4}
              opacity={0.8}
            />
          );
        }),
      )}
      {groups.map((g) => {
        const sy = seedY.get(g.seed)!;
        return (
          <g key={"s" + g.seed} onClick={() => open(g.seed)} style={{ cursor: "pointer" }}>
            <circle cx={leftX} cy={sy} r={3.2} fill="#1a4480" />
            <text x={leftX - 7} y={sy + 3} textAnchor="end" fontSize="10.5" fontWeight={600} fill="#1a4480">
              {g.seed}
            </text>
            <title>
              {g.seed} — {g.seedTitle} (semantic seed)
            </title>
          </g>
        );
      })}
      {flat.map((f) => {
        const by = branchY.get(f.seed + "|" + f.b.section)!;
        return (
          <g key={"b" + f.seed + f.b.section} onClick={() => open(f.b.section)} style={{ cursor: "pointer" }}>
            <circle cx={rightX} cy={by} r={3.2} fill={relColor(f.b.relation)} />
            <text x={rightX + 7} y={by + 2} textAnchor="start" fontSize="10.5" fill="#1b1b1b">
              {f.b.section}
            </text>
            <text x={rightX + 7} y={by + 12} textAnchor="start" fontSize="7.5" fill="#71767a">
              {f.b.relation}
            </text>
            <title>
              {f.b.section} — {f.b.title}
            </title>
          </g>
        );
      })}
    </svg>
  );
}

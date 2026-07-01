"use client";

import { useState } from "react";

type Clause = {
  clause: string;
  title: string;
  status: string;
  reason: string;
  prescribedBy: string;
  url: string;
};
type Result = {
  clauses: Clause[];
  retrievedSections: string[];
  candidateCount: number;
  latencyMs: number;
  note?: string;
};
type Attrs = Record<string, string>;

const FIELDS: { key: string; label: string; options: string[] }[] = [
  { key: "contractType", label: "Contract type", options: ["Firm-fixed-price", "Time-and-materials", "Labor-hour", "Cost-plus-fixed-fee", "Cost-plus-incentive-fee", "IDIQ"] },
  { key: "commercial", label: "Commercial status", options: ["Commercial products", "Commercial services", "Non-commercial"] },
  { key: "supplyService", label: "Supplies or services", options: ["Supplies", "Services", "Construction"] },
  { key: "value", label: "Estimated value", options: ["Micro-purchase (≤ $10K)", "At or below SAT (≤ $250K)", "$250K – $2M", "$2M – $7.5M", "Above $7.5M"] },
  { key: "setAside", label: "Set-aside", options: ["None", "Small business", "8(a)", "HUBZone", "SDVOSB", "WOSB"] },
  { key: "agency", label: "Agency", options: ["Civilian agency", "Department of Defense"] },
];

const DEFAULTS: Attrs = {
  contractType: "Firm-fixed-price",
  commercial: "Commercial services",
  supplyService: "Services",
  value: "At or below SAT (≤ $250K)",
  setAside: "Small business",
  agency: "Department of Defense",
};

function ClauseCard({ c }: { c: Clause }) {
  return (
    <div className={`far-clause far-clause--${c.status}`}>
      <div className="far-clause__head">
        <a className="far-clause__id" href={c.url} target="_blank" rel="noreferrer">
          {c.clause}
        </a>
        <span className={`far-clause__status far-clause__status--${c.status}`}>{c.status}</span>
      </div>
      <div className="far-clause__title">{c.title}</div>
      {c.reason && <div className="far-clause__reason">{c.reason}</div>}
      {c.prescribedBy && (
        <div className="far-clause__presc">
          Prescribed in{" "}
          <a href={`https://www.acquisition.gov/far/${c.prescribedBy}`} target="_blank" rel="noreferrer">
            {c.prescribedBy}
          </a>
        </div>
      )}
    </div>
  );
}

export default function Clauses() {
  const [attrs, setAttrs] = useState<Attrs>(DEFAULTS);
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    setRes(null);
    try {
      const r = await fetch("/api/clause-matrix", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ attributes: attrs }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error ?? "request failed");
      setRes(d);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "error");
    } finally {
      setLoading(false);
    }
  }

  const required = (res?.clauses ?? []).filter((c) => c.status === "required");
  const conditional = (res?.clauses ?? []).filter((c) => c.status !== "required");

  return (
    <div className="grid-container usa-section">
      <h1 className="font-heading-xl margin-bottom-1">FAR clause matrix generator</h1>
      <p className="usa-intro measure-5">
        Describe the acquisition and generate a draft FAR Part 52 clause list. Every clause is grounded
        in the FAR knowledge graph (its prescribing section) and links to acquisition.gov.
      </p>

      <form className="usa-form usa-form--large margin-top-3" onSubmit={generate}>
        <fieldset className="usa-fieldset">
          <div className="far-form-grid">
            {FIELDS.map((f) => (
              <div key={f.key}>
                <label className="usa-label margin-top-0" htmlFor={f.key}>
                  {f.label}
                </label>
                <select
                  id={f.key}
                  className="usa-select"
                  value={attrs[f.key]}
                  onChange={(e) => setAttrs((a) => ({ ...a, [f.key]: e.target.value }))}
                >
                  {f.options.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <button className="usa-button margin-top-3" type="submit" disabled={loading}>
            {loading ? "Generating…" : "Generate clause matrix"}
          </button>
        </fieldset>
      </form>

      {err && (
        <div className="usa-alert usa-alert--error margin-top-3" role="alert">
          <div className="usa-alert__body">{err}</div>
        </div>
      )}

      {res && (
        <div className="margin-top-4">
          <div className="far-matrix-meta">
            {res.clauses.length} clauses from {res.candidateCount} candidates across{" "}
            {res.retrievedSections.length} retrieved sections · {(res.latencyMs / 1000).toFixed(1)}s
          </div>

          {res.clauses.length === 0 ? (
            <p>{res.note ?? "No clauses found for this profile."}</p>
          ) : (
            <>
              <h2 className="far-matrix-h">Required <span>{required.length}</span></h2>
              <div className="far-clause-grid">
                {required.map((c) => (
                  <ClauseCard key={c.clause} c={c} />
                ))}
              </div>
              {conditional.length > 0 && (
                <>
                  <h2 className="far-matrix-h">Conditional <span>{conditional.length}</span></h2>
                  <div className="far-clause-grid">
                    {conditional.map((c) => (
                      <ClauseCard key={c.clause} c={c} />
                    ))}
                  </div>
                </>
              )}
            </>
          )}

          <p className="far-matrix-disclaimer">
            AI-generated draft grounded in the FAR knowledge graph — always verify against the official{" "}
            <a href="https://www.acquisition.gov/far/52.301" target="_blank" rel="noreferrer">
              FAR 52.301
            </a>{" "}
            matrix.
          </p>
        </div>
      )}
    </div>
  );
}

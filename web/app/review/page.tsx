"use client";

import { useState } from "react";

type AreaReview = {
  id: string;
  label: string;
  farSections: { section: string; title: string; source: string; via?: string }[];
  suggestions: string[];
  agencyDeviations?: { agency: string; suggestions: string[] };
};
type Deviation = {
  part: string;
  section: string;
  vpat_acr_required: string;
  remediation_required: string;
  deliverables_508_required: string;
};
type ReviewResult = {
  chars: number;
  inferenceMethod: string;
  agency: string | null;
  agencyLayer: { agency: string; source: string; deviationCount: number; deviations: Deviation[] } | null;
  issueAreas: { id: string; label: string; confidence: string }[];
  reviews: AreaReview[];
};

const SAMPLE = `DEPARTMENT OF HEALTH AND HUMAN SERVICES (HHS) — REQUEST FOR QUOTE
Cloud-based case management web application with a public portal and internal
dashboards. The system will process controlled unclassified information (CUI)
and personally identifiable information (PII).

Section 508: All electronic content and the user interface must conform to the
Revised Section 508 Standards (WCAG 2.0 AA). Vendor shall provide a VPAT/ACR.
Cybersecurity: The contractor's information system must comply with NIST SP
800-171, consistent with FAR 52.204-21.
This acquisition is a total small business set-aside under NAICS 541511.`;

const farUrl = (s: string) => `https://www.acquisition.gov/far/${s}`;

export default function ReviewPage() {
  const [text, setText] = useState("");
  const [agency, setAgency] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReviewResult | null>(null);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setText(await f.text());
  }

  async function runReview() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, agency: agency.trim() || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "review failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid-container" style={{ maxWidth: "56rem", paddingTop: "1.5rem", paddingBottom: "3rem" }}>
      <h1 className="font-heading-xl margin-bottom-05">Review a solicitation</h1>
      <p className="usa-intro" style={{ fontSize: "1rem", color: "#565c65", marginTop: 0 }}>
        Paste or upload a draft solicitation. The assistant infers which regulatory areas apply,
        pulls the governing FAR (with graph-linked clauses), layers on the acquiring agency&apos;s
        deviations, and surfaces the questions you should be asking.
      </p>

      <textarea
        className="usa-textarea"
        style={{ minHeight: "12rem", fontFamily: "inherit" }}
        placeholder="Paste solicitation text here…"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="display-flex flex-wrap" style={{ display: "flex", gap: "1rem", alignItems: "flex-end", marginTop: "0.75rem", flexWrap: "wrap" }}>
        <div>
          <label className="usa-label margin-top-0" htmlFor="agency">Acquiring agency (optional)</label>
          <input id="agency" className="usa-input" style={{ maxWidth: "16rem" }}
            placeholder="auto-detected (e.g. HHS, VA)" value={agency}
            onChange={(e) => setAgency(e.target.value)} />
        </div>
        <div>
          <label className="usa-label margin-top-0" htmlFor="file">Or upload a .txt</label>
          <input id="file" className="usa-file-input" type="file" accept=".txt,.md,text/plain" onChange={onFile} />
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button className="usa-button" onClick={runReview} disabled={loading || !text.trim()}>
            {loading ? "Reviewing…" : "Review"}
          </button>
          <button className="usa-button usa-button--outline" type="button"
            onClick={() => setText(SAMPLE)} disabled={loading}>
            Load sample
          </button>
        </div>
      </div>

      {error && (
        <div className="usa-alert usa-alert--error usa-alert--slim margin-top-2" role="alert">
          <div className="usa-alert__body"><p className="usa-alert__text">{error}</p></div>
        </div>
      )}

      {result && (
        <section className="margin-top-3">
          <div className="usa-summary-box" role="region" aria-label="Review summary">
            <div className="usa-summary-box__body">
              <h2 className="usa-summary-box__heading">Summary</h2>
              <div className="usa-summary-box__text">
                <p style={{ margin: 0 }}>
                  <strong>{result.reviews.length}</strong> issue area(s) detected
                  {" "}({result.inferenceMethod}). Agency:{" "}
                  <strong>{result.agency ?? "not detected"}</strong>
                  {result.agencyLayer ? ` (${result.agencyLayer.source}, ${result.agencyLayer.deviationCount} deviation clauses)` : ""}.
                </p>
              </div>
            </div>
          </div>

          {result.reviews.map((rv) => (
            <div key={rv.id} className="margin-top-2 padding-2" style={{ border: "1px solid #dfe1e2", borderRadius: 6 }}>
              <h3 className="margin-top-0 margin-bottom-1">{rv.label}</h3>

              {rv.farSections.length > 0 && (
                <>
                  <p className="text-bold margin-bottom-05" style={{ fontSize: ".9rem" }}>Relevant FAR</p>
                  <ul className="usa-list" style={{ marginTop: 0 }}>
                    {rv.farSections.slice(0, 8).map((h, i) => (
                      <li key={i} style={{ fontSize: ".92rem" }}>
                        <a href={farUrl(h.section)} target="_blank" rel="noreferrer">FAR {h.section}</a>{" "}
                        {h.title}
                        {h.source === "graph" && (
                          <span style={{ color: "#71767a" }}> — via graph ({h.via})</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}

              <p className="text-bold margin-bottom-05" style={{ fontSize: ".9rem" }}>
                Questions you should be asking
              </p>
              <ul className="usa-list" style={{ marginTop: 0 }}>
                {rv.suggestions.map((s, i) => (
                  <li key={i} style={{ fontSize: ".92rem" }}>{s}</li>
                ))}
              </ul>

              {rv.agencyDeviations && (
                <div className="padding-2 margin-top-1" style={{ background: "#f0f6fb", borderRadius: 6 }}>
                  <p className="text-bold margin-top-0 margin-bottom-05" style={{ fontSize: ".9rem" }}>
                    Agency layer — {rv.agencyDeviations.agency}
                  </p>
                  <ul className="usa-list" style={{ marginTop: 0 }}>
                    {rv.agencyDeviations.suggestions.map((s, i) => (
                      <li key={i} style={{ fontSize: ".92rem" }}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}

          {result.agencyLayer && (
            <div className="margin-top-2 padding-2" style={{ border: "1px solid #dfe1e2", borderRadius: 6 }}>
              <h3 className="margin-top-0">Agency deviations — {result.agencyLayer.agency}</h3>
              <ul className="usa-list" style={{ marginTop: 0 }}>
                {result.agencyLayer.deviations.slice(0, 12).map((d, i) => {
                  const flags = [
                    d.vpat_acr_required === "y" && "VPAT/ACR",
                    d.remediation_required === "y" && "remediation",
                    d.deliverables_508_required === "y" && "508-deliverables",
                  ].filter(Boolean);
                  return (
                    <li key={i} style={{ fontSize: ".92rem" }}>
                      {d.section || d.part}
                      {flags.length > 0 && <span style={{ color: "#005ea2" }}> [{flags.join(", ")}]</span>}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

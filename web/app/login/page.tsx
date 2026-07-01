"use client";

import { useState } from "react";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (r.ok) {
        const next = new URLSearchParams(window.location.search).get("next") || "/";
        window.location.href = next.startsWith("/") ? next : "/";
        return;
      }
      const d = await r.json().catch(() => ({}));
      setError(d.error ?? "Sign in failed.");
    } catch {
      setError("Sign in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="far-login">
      <div className="far-login__card">
        <div className="far-login__brand">Acquisition.gov</div>
        <h1 className="far-login__title">FAR Assistant</h1>
        <p className="far-login__sub">Sign in to continue.</p>

        {error && (
          <div className="usa-alert usa-alert--error usa-alert--slim margin-bottom-2" role="alert">
            <div className="usa-alert__body">
              <p className="usa-alert__text">{error}</p>
            </div>
          </div>
        )}

        <form className="usa-form" onSubmit={submit}>
          <label className="usa-label margin-top-1" htmlFor="username">
            Username
          </label>
          <input
            className="usa-input"
            id="username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
          <label className="usa-label" htmlFor="password">
            Password
          </label>
          <input
            className="usa-input"
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button className="usa-button far-login__btn margin-top-3" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

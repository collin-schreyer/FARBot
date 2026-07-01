"use client";

export default function SignOut() {
  async function out() {
    await fetch("/api/logout", { method: "POST" }).catch(() => {});
    window.location.href = "/login";
  }
  return (
    <button type="button" className="usa-nav__link far-signout" onClick={out}>
      <span>Sign out</span>
    </button>
  );
}

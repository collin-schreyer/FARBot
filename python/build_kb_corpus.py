#!/usr/bin/env python3
"""Build a Bedrock Knowledge Base ingestion corpus from the FAR DITA-HTML.

For each FAR section file in dita_html/*.html (excluding Part_*/Subpart_* index
pages), emit into kb_corpus/:
  - <section>.md             — a contextual document (hierarchy header + body text)
  - <section>.md.metadata.json — Bedrock KB metadata sidecar for filtering

Bedrock Knowledge Bases ingest each S3 object and, if a companion
`<object>.metadata.json` exists in the same prefix, attach its
`metadataAttributes` for metadata-filtered retrieval. The contextual header is
embedded with the chunk (Anthropic-style contextual retrieval), and the metadata
(part/subpart/title/cross_refs) powers filtered queries and, later, the FAR graph.

Hierarchy + cross-refs are parsed from the DITA markup:
  - section/title : <title> and <h1 class="title"> + <span class="ph autonumber">
  - part/subpart  : the parent-topic anchor classes (FAR_Part_19 FAR_Subpart_19_5)
  - cross_refs    : <a class="xref" href="19.203.html#...">

Usage:  python3 build_kb_corpus.py [--limit N] [--out kb_corpus]
"""
import os
import re
import sys
import json
import argparse

from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DITA_DIR = os.path.join(REPO_ROOT, "dita_html")

INDEX_PREFIXES = ("Part_", "Subpart_", "Subchapter_", "Chapter_")
_WS = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WS.sub(" ", (text or "").replace("\xa0", " ")).strip()


def _title_of(html_path: str) -> str:
    """Return the <title> text of an index page (for part/subpart names)."""
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "lxml")
        return _clean(soup.title.get_text()) if soup.title else ""
    except Exception:
        return ""


def build_hierarchy_titles():
    """Map '19' -> 'Part 19 - Small Business Programs', '19.5' -> 'Subpart 19.5 - ...'."""
    parts, subparts = {}, {}
    for name in os.listdir(DITA_DIR):
        if not name.endswith(".html"):
            continue
        if name.startswith("Part_"):
            num = name[len("Part_"):-len(".html")]
            parts[num] = _title_of(os.path.join(DITA_DIR, name))
        elif name.startswith("Subpart_"):
            num = name[len("Subpart_"):-len(".html")]
            subparts[num] = _title_of(os.path.join(DITA_DIR, name))
    return parts, subparts


def parse_section(html_path):
    """Extract structured metadata + body text from a FAR section file."""
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    stem = os.path.basename(html_path)[:-len(".html")]

    # Section number: prefer the h1 autonumber span, fall back to <title>/filename.
    section = stem
    h1 = soup.find("h1", class_="title")
    if h1:
        auto = h1.find("span", class_="autonumber")
        if auto and _clean(auto.get_text()):
            section = _clean(auto.get_text())

    # Title: <title> text minus the leading section number.
    raw_title = _clean(soup.title.get_text()) if soup.title else _clean(h1.get_text() if h1 else "")
    title = raw_title
    if title.startswith(section):
        title = title[len(section):].strip(" .-—")

    # Part / Subpart from the parent-topic anchor classes (most reliable).
    part = subpart = ""
    parent = soup.find("a", class_=lambda c: c and "FAR_Part_" in " ".join(c if isinstance(c, list) else [c]))
    classes = " ".join(parent.get("class", [])) if parent else ""
    mp = re.search(r"FAR_Part_(\d+)", classes)
    ms = re.search(r"FAR_Subpart_(\d+_\d+)", classes)
    if mp:
        part = mp.group(1)
    if ms:
        subpart = ms.group(1).replace("_", ".")
    # Part fallback from the section number (reliable: leading digits). Subpart is
    # NOT derivable from the section number (19.502 lives in subpart 19.5, not 19.502),
    # so we only trust the parent-link class token and otherwise leave it blank.
    if not part:
        m = re.match(r"(\d+)", section)
        part = m.group(1) if m else ""

    # Cross-references: xref hrefs -> target section ids (exclude self).
    refs = []
    for a in soup.find_all("a", class_=lambda c: c and "xref" in (c if isinstance(c, list) else [c])):
        href = a.get("href", "")
        base = href.split("#", 1)[0]
        if base.endswith(".html"):
            ref = base[:-len(".html")]
            if ref and ref != section and not ref.startswith(INDEX_PREFIXES):
                refs.append(ref)
    cross_refs = sorted(set(refs))

    # Body text.
    body = soup.find("div", class_="body")
    body_text = _clean(body.get_text(" ")) if body else _clean(soup.get_text(" "))

    return {
        "section": section,
        "title": title,
        "part": part,
        "subpart": subpart,
        "cross_refs": cross_refs,
        "text": body_text,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="process only N sections (smoke test)")
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "kb_corpus"))
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    part_titles, subpart_titles = build_hierarchy_titles()
    print(f"Hierarchy: {len(part_titles)} parts, {len(subpart_titles)} subparts")

    files = sorted(
        n for n in os.listdir(DITA_DIR)
        if n.endswith(".html") and not n.startswith(INDEX_PREFIXES)
    )
    if args.limit:
        files = files[:args.limit]

    written, skipped, total_refs = 0, 0, 0
    manifest = []
    for name in files:
        path = os.path.join(DITA_DIR, name)
        try:
            meta = parse_section(path)
        except Exception as e:
            print(f"  skip {name}: {e}")
            skipped += 1
            continue
        if not meta["text"] or len(meta["text"]) < 15:
            skipped += 1
            continue

        part_t = part_titles.get(meta["part"], f"Part {meta['part']}")
        subpart_t = subpart_titles.get(meta["subpart"], f"Subpart {meta['subpart']}")
        header = (
            f"# FAR {meta['section']} — {meta['title']}\n\n"
            f"{part_t} › {subpart_t}\n\n"
        )
        doc = header + meta["text"] + "\n"

        base = meta["section"]
        with open(os.path.join(args.out, f"{base}.md"), "w", encoding="utf-8") as f:
            f.write(doc)
        # Bedrock KB metadata attributes must be scalars (string/number/boolean),
        # never arrays — so join cross_refs and omit empty fields.
        attrs = {
            "section": meta["section"],
            "part": meta["part"],
            "title": meta["title"],
            "source_url": f"https://www.acquisition.gov/far/{meta['section']}",
        }
        if meta["subpart"]:
            attrs["subpart"] = meta["subpart"]
        if meta["cross_refs"]:
            attrs["cross_refs"] = ",".join(meta["cross_refs"])
        sidecar = {"metadataAttributes": attrs}
        with open(os.path.join(args.out, f"{base}.md.metadata.json"), "w", encoding="utf-8") as f:
            json.dump(sidecar, f, ensure_ascii=False)

        manifest.append({k: meta[k] for k in ("section", "part", "subpart", "title", "cross_refs")})
        written += 1
        total_refs += len(meta["cross_refs"])

    with open(os.path.join(args.out, "manifest.jsonl"), "w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {written} docs (+ metadata sidecars), skipped {skipped}.")
    print(f"Cross-references captured: {total_refs} (avg {total_refs / max(written,1):.1f}/section).")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()

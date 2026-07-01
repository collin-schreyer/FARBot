#!/usr/bin/env python3
"""
FAR retrieval — the seam between FAR_BOT and the SRT v4.1 pipeline.

FAR_BOT's Next.js app (web/app/api/ask/route.ts) retrieves FAR sections from a
Bedrock Knowledge Base with HYBRID search, then expands the result set along the
FAR knowledge graph (policy<->clause prescriptions and cross-references). This
module reproduces that retrieval in Python so the SRT pipeline can use FAR_BOT's
retrieval as the "retrieval stage" of a FAR / agency Topic Pack — instead of the
508-only FAISS-over-508_standards.txt stage.

Two backends:
  - "bedrock" (live): mirrors route.ts — boto3 bedrock-agent-runtime.retrieve
    (HYBRID) + graph expansion. Needs AWS_REGION, FAR_KB_ID (and creds / profile).
  - "offline": keyword search over the 3,496 FAR node titles in far_graph.json +
    the same graph expansion. No network. Lets the whole upload->check->suggest
    flow run and prove the wiring before live creds are wired in.

The FAR graph (web/data/far_graph.json) is the same artifact FAR_BOT ships; we
just read it from Python. titleOf() and expand_sections() are direct ports of
web/lib/graph.ts.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default graph location: engine lives at FAR_BOT/srt-rag-usai/, graph at FAR_BOT/web/data/
_DEFAULT_GRAPH = Path(__file__).resolve().parent.parent / "web" / "data" / "far_graph.json"
_CITE = re.compile(r"\b(\d{1,2}\.\d{2,4}(?:-\d+)?)\b")


class FARGraph:
    """Port of web/lib/graph.ts — titles, prescriptions, cross-references."""

    def __init__(self, graph_path: Optional[str] = None):
        path = Path(graph_path or os.getenv("FAR_GRAPH_PATH") or _DEFAULT_GRAPH)
        self.loaded = False
        self.titles: Dict[str, str] = {}
        self.prescribes: Dict[str, List[str]] = {}
        self.prescribed_by: Dict[str, List[str]] = {}
        self.xref_out: Dict[str, List[str]] = {}
        try:
            g = json.loads(Path(path).read_text(encoding="utf-8"))
            idx = g.get("index", {})
            self.titles = idx.get("titles", {}) or {}
            self.prescribes = idx.get("prescribes", {}) or {}
            self.prescribed_by = idx.get("prescribedBy", {}) or {}
            for pair in g.get("edges", {}).get("crossReferences", []) or []:
                if len(pair) == 2:
                    f, t = pair
                    self.xref_out.setdefault(f, []).append(t)
            self.loaded = True
            logger.info(f"[FARGraph] loaded {len(self.titles)} titles from {path}")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"[FARGraph] could not load {path}: {e}")

    def title_of(self, section: str) -> str:
        return self.titles.get(section, "")

    @staticmethod
    def part_of(section: str) -> str:
        return section.split(".")[0] if section else ""

    def expand_sections(self, seed: List[str], max_add: int = 12) -> List[Dict[str, str]]:
        """Prescriptions first (policy<->clause), then cross-references. Mirrors graph.ts."""
        seen = set(seed)
        added: List[Dict[str, str]] = []

        def push(section: str, via: str, frm: str):
            if section in seen:
                return
            seen.add(section)
            added.append({"section": section, "via": via, "from": frm})

        for s in seed:
            for sec in self.prescribed_by.get(s, []):
                push(sec, "prescribed by", s)
            for c in self.prescribes.get(s, []):
                push(c, "prescribes", s)
            if len(added) >= max_add:
                return added[:max_add]
        for s in seed:
            for t in self.xref_out.get(s, []):
                push(t, "references", s)
                if len(added) >= max_add:
                    return added[:max_add]
        return added[:max_add]

    def search_titles(self, query: str, limit: int = 8) -> List[str]:
        """Offline retrieval: score FAR sections by keyword overlap with their titles."""
        terms = [w for w in re.findall(r"[a-z0-9]{3,}", query.lower()) if w not in _STOP]
        if not terms:
            return []
        scored = []
        for section, title in self.titles.items():
            tl = title.lower()
            hits = sum(1 for w in terms if w in tl)
            if hits:
                # prefer clause/policy sections with more term hits, then shorter titles
                scored.append((hits, -len(tl), section))
        scored.sort(reverse=True)
        return [s for _, _, s in scored[:limit]]


_STOP = {
    "the", "and", "for", "with", "that", "this", "are", "any", "all", "shall",
    "will", "from", "not", "was", "were", "has", "have", "such", "which", "including",
}


class FARRetriever:
    """Retrieve relevant FAR sections for a query, with FAR-graph expansion."""

    def __init__(
        self,
        region: Optional[str] = None,
        kb_id: Optional[str] = None,
        model_arn: Optional[str] = None,
        graph_path: Optional[str] = None,
        offline: Optional[bool] = None,
    ):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.kb_id = kb_id or os.getenv("FAR_KB_ID")
        self.model_arn = model_arn or os.getenv("BEDROCK_MODEL_ARN")
        self.profile = os.getenv("AWS_PROFILE")
        self.graph = FARGraph(graph_path)
        # offline unless explicitly live-capable; caller can force with offline=False
        self._forced_offline = offline
        self._agent = None

    @property
    def offline(self) -> bool:
        if self._forced_offline is not None:
            return self._forced_offline
        return not bool(self.kb_id)

    def _client(self):
        if self._agent is None:
            import boto3
            session = boto3.Session(
                profile_name=self.profile or None, region_name=self.region
            )
            self._agent = session.client("bedrock-agent-runtime")
        return self._agent

    def backend(self) -> str:
        return "offline (FAR graph keyword search)" if self.offline else "bedrock HYBRID + FAR graph"

    def retrieve(self, query: str, top_k: int = 8, expand_graph: bool = True) -> Dict[str, Any]:
        """
        Returns {backend, semantic: [...], graph: [...]} where each item is
        {section, title, score, text, source, via?, from?}.
        """
        if self.offline:
            return self._retrieve_offline(query, top_k, expand_graph)
        return self._retrieve_bedrock(query, top_k, expand_graph)

    # ── live: mirror web/app/api/ask/route.ts ──────────────────────────────
    def _retrieve_bedrock(self, query: str, top_k: int, expand_graph: bool) -> Dict[str, Any]:
        agent = self._client()
        rr = agent.retrieve(
            knowledgeBaseId=self.kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": top_k,
                    "overrideSearchType": "HYBRID",
                }
            },
        )
        semantic: List[Dict[str, Any]] = []
        seen = set()
        for r in rr.get("retrievalResults", []):
            md = r.get("metadata", {}) or {}
            section = str(md.get("section", ""))
            if not section or section in seen:
                continue
            seen.add(section)
            text = _clean(r.get("content", {}).get("text", ""))
            semantic.append({
                "section": section, "title": self.graph.title_of(section),
                "score": r.get("score", 0.0), "text": text,
                "snippet": text[:240], "source": "semantic",
            })

        graph_items: List[Dict[str, Any]] = []
        if expand_graph and semantic:
            seed = [c["section"] for c in semantic[:8]]
            expansions = self.graph.expand_sections(seed, 12)
            wanted = [e["section"] for e in expansions]
            text_by_section = {}
            if wanted:
                try:
                    fr = agent.retrieve(
                        knowledgeBaseId=self.kb_id,
                        retrievalQuery={"text": query},
                        retrievalConfiguration={
                            "vectorSearchConfiguration": {
                                "numberOfResults": min(len(wanted), 20),
                                "filter": {"in": {"key": "section", "value": wanted}},
                            }
                        },
                    )
                    for r in fr.get("retrievalResults", []):
                        md = r.get("metadata", {}) or {}
                        sec = str(md.get("section", ""))
                        if sec:
                            text_by_section[sec] = _clean(r.get("content", {}).get("text", ""))
                except Exception as e:  # pragma: no cover - best effort
                    logger.warning(f"[FARRetriever] graph text fetch failed: {e}")
            for e in expansions:
                text = text_by_section.get(e["section"], "")
                graph_items.append({
                    "section": e["section"], "title": self.graph.title_of(e["section"]),
                    "score": 0.0, "text": text,
                    "snippet": text[:200] or f"(added via FAR graph — {e['via']} {e['from']})",
                    "source": "graph", "via": e["via"], "from": e["from"],
                })
        return {"backend": self.backend(), "semantic": semantic, "graph": graph_items}

    # ── offline: FAR graph keyword search + same expansion ─────────────────
    def _retrieve_offline(self, query: str, top_k: int, expand_graph: bool) -> Dict[str, Any]:
        sections = self.graph.search_titles(query, top_k)
        semantic = [{
            "section": s, "title": self.graph.title_of(s), "score": None,
            "text": "", "snippet": f"(FAR {s} — {self.graph.title_of(s)})",
            "source": "semantic",
        } for s in sections]
        graph_items: List[Dict[str, Any]] = []
        if expand_graph and sections:
            for e in self.graph.expand_sections(sections[:8], 12):
                graph_items.append({
                    "section": e["section"], "title": self.graph.title_of(e["section"]),
                    "score": None, "text": "",
                    "snippet": f"(added via FAR graph — {e['via']} {e['from']})",
                    "source": "graph", "via": e["via"], "from": e["from"],
                })
        return {"backend": self.backend(), "semantic": semantic, "graph": graph_items}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

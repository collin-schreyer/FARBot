#!/usr/bin/env python3
"""
Bedrock gateway — the single LLM + embedding provider for the blended system.

The SRT pipeline was built against USAIAdapter (GSA USAI API). FAR_BOT already
runs entirely on AWS Bedrock (KB retrieval + Converse generation in
web/app/api/ask/route.ts). To make one cohesive system we drop USAI and route
every LLM/embedding call through Bedrock too.

BedrockAdapter subclasses USAIAdapter purely to inherit its domain logic — the
v4.1 applicability prompt (assess_508_applicability), ICT classification,
synthesis, the JSON-retry wrapper, stage logging, and the default responses.
None of that is USAI-specific: it all calls self._chat. We override only the
transport (__init__ + _chat) and add Bedrock embeddings, so nothing about the
pipeline's behavior changes except where the tokens come from.

Config (env; FAR_BOT/web/.env is auto-loaded):
  AWS_REGION, AWS_PROFILE            — AWS session
  BEDROCK_MODEL_ARN | BEDROCK_MODEL_ID       — main model (Converse)
  BEDROCK_CHEAP_MODEL_ID             — cheaper model for high-volume stages
  BEDROCK_EMBED_MODEL_ID             — default cohere.embed-english-v3 (1024-dim,
                                       matches the prebuilt 508 FAISS index)
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from usai_adapter import USAIAdapter  # base class: prompts + domain logic only

logger = logging.getLogger(__name__)


def _load_env() -> None:
    """Best-effort: pull FAR_BOT/web/.env then engine .env into the environment."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    here = Path(__file__).resolve().parent
    # web/.env.local holds the live app's Bedrock config (KB id, model ARN, profile)
    for p in (here.parent / "web" / ".env.local", here.parent / "web" / ".env",
              here / ".env"):
        if p.exists():
            load_dotenv(p, override=False)


_load_env()

DEFAULT_MODEL = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
DEFAULT_EMBED_MODEL = os.getenv("BEDROCK_EMBED_MODEL_ID", "cohere.embed-english-v3")


class BedrockAdapter(USAIAdapter):
    """USAIAdapter's interface, backed by AWS Bedrock (Converse + embeddings)."""

    def __init__(self, model: str = None, cheap_model: str = None,
                 region: str = None, profile: str = None):
        # NOTE: deliberately does NOT call super().__init__ — that path requires
        # USAI_API. We stand up a Bedrock client and mirror the base attributes.
        import boto3
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.profile = profile or os.getenv("AWS_PROFILE")
        # Main model: prefer an explicit inference-profile ARN (what web/.env has)
        self.model = (model or os.getenv("BEDROCK_MODEL_ARN")
                      or os.getenv("BEDROCK_MODEL_ID") or DEFAULT_MODEL)
        self.cheap_model = (cheap_model or os.getenv("BEDROCK_CHEAP_MODEL_ID")
                            or self.model)
        self.embed_model_id = DEFAULT_EMBED_MODEL

        session = boto3.Session(profile_name=self.profile or None, region_name=self.region)
        self._runtime = session.client("bedrock-runtime")

        self._call_count = 0
        self._total_tokens = 0
        self._stage_logs: List[Dict[str, Any]] = []
        logger.info(f"Bedrock adapter initialized (model={self.model}, "
                    f"cheap={self.cheap_model}, embed={self.embed_model_id}, region={self.region})")

    # ── transport override: Bedrock Converse instead of USAI chat ──────────
    def _chat(self, system: str, user: str, model: str = None,
              temperature: float = 0.0, max_tokens: int = 1000,
              json_mode: bool = False, stage_name: str = "unknown") -> str:
        model = model or self.model
        self._call_count += 1
        start = time.time()
        try:
            resp = self._runtime.converse(
                modelId=model,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
            )
            text = resp["output"]["message"]["content"][0]["text"]
            usage = resp.get("usage", {}) or {}
            tokens = usage.get("totalTokens", 0)
            self._total_tokens += tokens
            elapsed = time.time() - start
            self._log_stage(stage_name, elapsed, tokens, model,
                            system_prompt=system, user_prompt=user, raw_response=text)
            logger.info(f"    ✅ Bedrock #{self._call_count}: {stage_name} — {elapsed:.1f}s, {tokens} tok")
            return text
        except Exception as e:
            elapsed = time.time() - start
            self._log_stage(f"{stage_name}_ERROR", elapsed, 0, model,
                            system_prompt=system, user_prompt=user, raw_response=str(e))
            logger.error(f"    ❌ Bedrock error after {elapsed:.1f}s: {stage_name} — {type(e).__name__}: {e}")
            raise

    # ── embeddings via Bedrock (Cohere English v3 → 1024-dim) ──────────────
    def embed(self, texts: List[str], input_type: str = "search_document") -> List[List[float]]:
        out: List[List[float]] = []
        for t in texts:
            if not t or not t.strip():
                continue
            body = json.dumps({"texts": [t], "input_type": input_type, "truncate": "END"})
            resp = self._runtime.invoke_model(modelId=self.embed_model_id, body=body)
            data = json.loads(resp["body"].read())
            embs = data.get("embeddings", [])
            if embs:
                out.append(embs[0])
        return out


class BedrockLCEmbeddings:
    """Minimal LangChain Embeddings shim over BedrockAdapter.embed for FAISS.

    The prebuilt data/faiss_index was created with Cohere English v3; Bedrock's
    cohere.embed-english-v3 is the same model (1024-dim), so query embeddings
    stay compatible with the stored document vectors.
    """

    def __init__(self, adapter: Optional[BedrockAdapter] = None):
        self._adapter = adapter or BedrockAdapter()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._adapter.embed(texts, input_type="search_document")

    def embed_query(self, text: str) -> List[float]:
        res = self._adapter.embed([text], input_type="search_query")
        return res[0] if res else []


def make_client(**kwargs) -> BedrockAdapter:
    """Single factory for the system's LLM/embedding gateway."""
    return BedrockAdapter(**kwargs)

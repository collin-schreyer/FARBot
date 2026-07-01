#!/usr/bin/env python3
"""Parity eval: run the golden set against the Bedrock Knowledge Base (Retrieve)
and score with the SAME metrics as the local baseline (eval/run_eval.py).

Retrieval-only (uses bedrock-agent-runtime Retrieve, not RetrieveAndGenerate), so
the numbers are directly comparable to the MiniLM+FAISS baseline. Shells out to the
AWS CLI to avoid a boto3 dependency.

Usage:  python3 eval/run_eval_bedrock.py --kb 87TRELNWTT [--top-k 10]
"""
import os
import sys
import json
import argparse
import subprocess

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS_DIR)
import metrics as M  # noqa: E402


def retrieve(kb, query, region, profile, k, search_type):
    vsc = {"numberOfResults": k}
    if search_type:
        vsc["overrideSearchType"] = search_type
    cmd = [
        "aws", "bedrock-agent-runtime", "retrieve",
        "--knowledge-base-id", kb,
        "--retrieval-query", json.dumps({"text": query}),
        "--retrieval-configuration", json.dumps({"vectorSearchConfiguration": vsc}),
        "--region", region, "--profile", profile, "--output", "json",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    data = json.loads(out.stdout)
    return [str((r.get("metadata") or {}).get("section", "")) for r in data.get("retrievalResults", [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default="87TRELNWTT")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--profile", default="default")
    ap.add_argument("--golden", default=os.path.join(THIS_DIR, "golden_set.jsonl"))
    args = ap.parse_args()

    golden = [json.loads(l) for l in open(args.golden) if l.strip()]

    # Probe HYBRID; fall back to default (semantic) if the store doesn't support it.
    search = "HYBRID"
    try:
        retrieve(args.kb, "test", args.region, args.profile, 1, "HYBRID")
    except Exception as e:
        print(f"HYBRID unavailable ({str(e)[:70]}); using SEMANTIC.")
        search = None

    k = args.top_k
    print("\n" + "=" * 96)
    print(f"BEDROCK KB PARITY EVAL  |  {len(golden)} queries  |  top_k={k}  |  search={search or 'SEMANTIC'}  |  kb={args.kb}")
    print("=" * 96)
    print(f"{'query id':<16}{'rec@5':>7}{'rec@10':>8}{'hit@10':>8}{'MRR':>7}{'rel@3':>7}{'base@3':>8}")
    print("-" * 96)

    agg = {"rec5": 0.0, "rec10": 0.0, "hit10": 0.0, "mrr": 0.0, "rel3": 0.0}
    for item in golden:
        expected = item["expected_sections"]
        try:
            citations = retrieve(args.kb, item["query"], args.region, args.profile, k, search)
        except Exception as e:
            print(f"{item['id']:<16}  ERROR: {str(e)[:60]}")
            continue
        rec5 = M.recall_at_k(citations, expected, 5)
        rec10 = M.recall_at_k(citations, expected, 10)
        hit10 = M.hit_at_k(citations, expected, 10)
        mrr = M.mrr(citations, expected)
        rel3 = M.precision_relevant_at_k(citations, expected, 3)
        base = item.get("baseline_top3_pct")
        agg["rec5"] += rec5; agg["rec10"] += rec10; agg["hit10"] += hit10
        agg["mrr"] += mrr; agg["rel3"] += rel3
        print(f"{item['id']:<16}{rec5:>7.2f}{rec10:>8.2f}{hit10:>8.0f}{mrr:>7.2f}"
              f"{rel3*100:>6.0f}%{(str(base)+'%') if base is not None else '-':>8}")

    n = len(golden)
    print("-" * 96)
    print(f"{'MEAN':<16}{agg['rec5']/n:>7.2f}{agg['rec10']/n:>8.2f}"
          f"{agg['hit10']/n:>8.2f}{agg['mrr']/n:>7.2f}{agg['rel3']/n*100:>6.0f}%")
    print("=" * 96)
    print("Baseline to beat (local MiniLM+FAISS): recall@10=0.72, MRR=0.76, rel@3=49%.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Offline retrieval eval for the FAR bot.

Retrieval-only (no LLM calls, no cost): loads the current FARChatbot, runs each
golden query through `search_similar`, and scores the returned citations against
expected FAR sections. Prints a per-query table plus aggregate recall@k / MRR, and
compares to the documented baselines (docs/IMPROVEMENT_SUMMARY.md).

This is the acceptance bar that the AWS Bedrock Knowledge Base rebuild must match
or beat. Run:  python3 eval/run_eval.py  [--top-k 10]
"""
import os
import sys
import json
import argparse

# macOS guard: faiss + torch both bundle OpenMP; without this the model load
# can segfault (exit 139) when run as a plain script. Set before any heavy import.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
sys.path.insert(0, THIS_DIR)                       # for metrics.py
sys.path.insert(0, os.path.join(REPO_ROOT, "python"))  # for far_chatbot.py

import metrics as M  # noqa: E402


def load_golden(path):
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def main():
    ap = argparse.ArgumentParser(description="FAR bot retrieval eval")
    ap.add_argument("--top-k", type=int, default=10, help="retrieval depth to score")
    ap.add_argument("--golden", default=os.path.join(THIS_DIR, "golden_set.jsonl"))
    args = ap.parse_args()

    from far_chatbot import FARChatbot  # noqa: E402

    index_path = os.path.join(REPO_ROOT, "dita_html", "faiss_index.index")
    texts_path = os.path.join(REPO_ROOT, "dita_html", "texts.txt")

    print(f"Loading FARChatbot (index={os.path.basename(index_path)}) ...")
    bot = FARChatbot(faiss_index_path=index_path, texts_path=texts_path)

    golden = load_golden(args.golden)
    k = args.top_k

    print("\n" + "=" * 96)
    print(f"FAR BOT RETRIEVAL EVAL  |  {len(golden)} queries  |  top_k={k}  |  current MiniLM + FAISS")
    print("=" * 96)
    header = f"{'query id':<16}{'rec@5':>7}{'rec@10':>8}{'hit@10':>8}{'MRR':>7}{'rel@3':>7}{'base@3':>8}"
    print(header)
    print("-" * 96)

    agg = {"rec5": 0.0, "rec10": 0.0, "hit10": 0.0, "mrr": 0.0, "rel3": 0.0}
    for item in golden:
        q = item["query"]
        expected = item["expected_sections"]
        results = bot.search_similar(q, top_k=k, use_context=False)
        citations = [bot.extract_citation(t) for t, _ in results]

        rec5 = M.recall_at_k(citations, expected, 5)
        rec10 = M.recall_at_k(citations, expected, 10)
        hit10 = M.hit_at_k(citations, expected, 10)
        mrr = M.mrr(citations, expected)
        rel3 = M.precision_relevant_at_k(citations, expected, 3)
        base = item.get("baseline_top3_pct")
        base_s = f"{base}%" if base is not None else "-"

        agg["rec5"] += rec5
        agg["rec10"] += rec10
        agg["hit10"] += hit10
        agg["mrr"] += mrr
        agg["rel3"] += rel3

        print(f"{item['id']:<16}{rec5:>7.2f}{rec10:>8.2f}{hit10:>8.0f}{mrr:>7.2f}"
              f"{rel3*100:>6.0f}%{base_s:>8}")

    n = len(golden)
    print("-" * 96)
    print(f"{'MEAN':<16}{agg['rec5']/n:>7.2f}{agg['rec10']/n:>8.2f}"
          f"{agg['hit10']/n:>8.2f}{agg['mrr']/n:>7.2f}{agg['rel3']/n*100:>6.0f}%")
    print("=" * 96)
    print("rel@3 = % of top-3 citations relevant (comparable to documented baseline base@3).")
    print("This baseline is the bar the AWS Bedrock KB rebuild must match or beat.")


if __name__ == "__main__":
    main()

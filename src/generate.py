"""Produce candidate SQL for a stratified subset of BIRD dev.

Writes one JSONL trace per example with full cost and latency instrumentation.
Retrofitting that later is painful and the cost analysis is one of the more
interesting things this repo will have to say, so it goes in from line one.

    python src/generate.py                      # 200 examples, claude-sonnet-5
    python src/generate.py --limit 5            # smoke test
    python src/generate.py --model claude-opus-4-8 --out data/traces/opus.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from sample import select_baseline
from schema import REPO_ROOT, schema_ddl

# USD per million tokens, (input, output).
# Sonnet 5 carries introductory pricing through 2026-08-31 ($2/$10); the
# standard rate is $3/$15. Recorded costs use whatever is listed here, so the
# table is the thing to update when intro pricing lapses — otherwise every
# historical trace silently misstates its cost.
PRICING = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_OUT = REPO_ROOT / "data" / "traces" / "baseline.jsonl"

SYSTEM = (
    "You are a SQL expert. Given a SQLite schema and a question, write one "
    "SQLite query that answers it.\n\n"
    "Respond with the query and nothing else — no explanation, no markdown "
    "fences, no trailing semicolon."
)

PROMPT = """Schema:

{ddl}

Question: {question}

Hint: {evidence}"""


def build_prompt(rec: dict) -> str:
    return PROMPT.format(
        ddl=schema_ddl(rec["db_id"]),
        question=rec["question"],
        evidence=rec["evidence"] or "(none)",
    )


def strip_fence(text: str) -> str:
    """Drop a markdown fence if the model added one despite instructions.

    Recording how often this fires is itself worth knowing — it is a cheap
    proxy for instruction-following, and it is the sort of preprocessing that
    usually happens silently and then confounds the pass rate.
    """
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def generate_one(client: anthropic.Anthropic, rec: dict, model: str) -> dict:
    prompt = build_prompt(rec)
    started = time.perf_counter()
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM,
        # SQL generation is a short, well-specified task: thinking off keeps
        # latency and cost honest for the baseline. Phase 4 can sweep this.
        thinking={"type": "disabled"},
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = round((time.perf_counter() - started) * 1000)

    raw = "".join(b.text for b in resp.content if b.type == "text")
    generated_sql = strip_fence(raw)

    in_rate, out_rate = PRICING[model]
    usage = resp.usage
    cost = (usage.input_tokens * in_rate + usage.output_tokens * out_rate) / 1e6

    return {
        "id": f"bird_dev_{rec['question_id']:04d}",
        "db_id": rec["db_id"],
        "difficulty": rec["difficulty"],
        "question": rec["question"],
        "evidence": rec["evidence"],
        "gold_sql": rec["SQL"],
        "prompt": prompt,
        "model": model,
        "generated_sql": generated_sql,
        "raw_response": raw,
        "was_fenced": raw.strip() != generated_sql,
        "stop_reason": resp.stop_reason,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
        "latency_ms": latency_ms,
        "cost_usd": round(cost, 6),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(PRICING))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, help="generate fewer than the full sample")
    args = parser.parse_args()

    records = select_baseline()
    if args.limit:
        records = records[: args.limit]

    # Resume rather than regenerate: an interrupted run costs money to redo.
    done: set[str] = set()
    if args.out.exists():
        with args.out.open(encoding="utf-8") as f:
            done = {json.loads(line)["id"] for line in f if line.strip()}
        if done:
            print(f"{len(done)} traces already in {args.out}, skipping those")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()

    total_cost = 0.0
    written = 0
    with args.out.open("a", encoding="utf-8") as f:
        for i, rec in enumerate(records, 1):
            trace_id = f"bird_dev_{rec['question_id']:04d}"
            if trace_id in done:
                continue
            trace = generate_one(client, rec, args.model)
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
            f.flush()
            total_cost += trace["cost_usd"]
            written += 1
            print(
                f"[{i:>3}/{len(records)}] {trace_id} "
                f"{trace['latency_ms']:>5}ms ${trace['cost_usd']:.4f} "
                f"running=${total_cost:.3f}"
            )

    print(f"\nwrote {written} traces to {args.out}")
    print(f"cost ${total_cost:.4f}" + (f" over {written} calls" if written else ""))


if __name__ == "__main__":
    main()

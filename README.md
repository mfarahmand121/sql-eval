# Text-to-SQL Evaluation

**Evaluation is a measurement problem, not a testing problem.**

Most LLM eval writing treats evaluation as testing: write assertions, watch them
pass. That framing is why so many published eval numbers can't be interpreted.

An automated judge is a noisy instrument measuring a latent quantity — whether
the system is actually correct. If you don't know the instrument's error rates,
the measurement means nothing. If you do know them, you can correct for them and
put uncertainty bounds on the result.

This repo builds that argument end to end on the BIRD text-to-SQL benchmark:
hand-label a few hundred model outputs, measure how often the automated judge is
wrong, and report a pass rate with an honest credible interval instead of a
point estimate.

The claim it builds toward: **I can tell you how wrong your eval results are.**

## Why text-to-SQL

Ground truth is *partly* mechanical — execute both queries, compare result sets
— which forces the interesting question of where mechanical grading is wrong.
That gap is where the findings live. Two buckets in particular:

- **Correct-but-different**: semantically equivalent to gold, different syntax.
- **Gold is wrong**: the benchmark's own annotation is incorrect.

The second is not hypothetical. Recent work documents annotation error rates
above 50% in widely-used text-to-SQL benchmarks, and shows that correcting them
reshuffles leaderboard rankings. Every number published against these benchmarks
inherits that noise, and almost nobody propagates it.

## Status

Phase 0 (setup and baseline generation) — in progress.

| Phase | What | State |
| --- | --- | --- |
| 0 | Data, generation harness, cost instrumentation | scaffolded |
| 1 | Open coding: 100 traces read by hand, taxonomy, self-agreement rate | not started |
| 2 | Execution-based grading + database perturbation → spurious pass rate | not started |
| 3 | LLM judge, 150 hand labels, sensitivity/specificity, prevalence correction | not started |
| 4 | Stratified sampling, regression suite, cost analysis, model comparison | not started |
| 5 | Framework migration, writeup | not started |

## Setup

Requires Python 3.11+ and the BIRD dev set. SQLite ships with Python, so there's
no database server to run.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt    # Windows
```

Download the BIRD dev set from https://bird-bench.github.io (`dev.zip`, ~330MB)
and extract it to `data/bird/dev_20240627/`, then extract the nested
`dev_databases.zip` in place. The dev split is 1,534 question/SQL pairs over 11
databases — do not download the full benchmark (12,751 pairs, 33GB); dev is
enough and stays manageable on a laptop.

Copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY`.

## Generating traces

```bash
.venv/Scripts/python src/generate.py --limit 5      # smoke test first
.venv/Scripts/python src/generate.py                # full 200
```

Writes JSONL to `data/traces/baseline.jsonl`, one trace per line, with cost and
latency recorded per call. Runs are resumable — re-running skips IDs already
present rather than paying for them twice.

**200 examples, not 1,534.** These get read by hand. Depth beats coverage here,
and nobody is impressed by scale in an error analysis.

The subset is a deterministic stratified sample across (database, difficulty),
proportional to the dev split — `simple` / `moderate` / `challenging` land at
120 / 60 / 20. Stratifying matters: `challenging` is under 10% of dev, and the
failure modes worth studying concentrate in the harder strata.

## Layout

```
data/
  bird/          downloaded dataset (gitignored)
  traces/        generated outputs, JSONL (committed)
  labels/        hand labels (committed — these are the expensive artifact)
src/
  schema.py      dataset loading + DDL extraction
  sample.py      stratified sampling
  generate.py    candidate SQL generation with cost/latency instrumentation
```

`execute.py`, `grade_exec.py`, `judge.py`, `stats.py`, the annotation app, and
the notebooks arrive with their respective phases.

## Notes on method

- **Binary judgments, not Likert scales.** Rating scales produce inconsistent
  labels across annotators and runs, invite fake precision, and make the
  boundary between a 3 and a 4 unmanageable. Binary forces the standard to be
  defined.
- **The taxonomy comes from reading outputs, not from imagination.** Phase 1 is
  open coding with no categories decided in advance — writing the taxonomy first
  just confirms your priors.
- **Self-agreement is the ceiling.** Re-labelling the same 100 traces against
  the finalized taxonomy measures how often I disagree with myself. No automated
  judge can beat the consistency of the human defining the standard.
